"""발화 속도 지표 (원본 계획서 REQ-F-006의 '발화 속도' 항목, 2026-10-12).

STT 결과 텍스트와 음성 길이로 분당 어절 수·분당 음절 수를 계산한다. 별도 DB 컬럼 없이 기존
`TRANSCRIPTS.prosody_json`(JSONB)에 함께 저장하고, 리포트 생성 때 사용자 턴 전체를 합산해
`EVALUATION_REPORTS.details_json["speech_rate"]`에 서버가 직접 계산한 값으로 넣는다(LLM이 만든 값이 아님).

한계(해석 시 주의):
- 길이는 **녹음 전체 길이(휴지 포함)** 기준이다(`speech_rate_basis="total_duration"`).
  말하는 구간만 뽑은 조음 속도가 아니다.
- 한국어는 어절(공백 단위)과 한글 음절 수를 센다. 영문·숫자 토큰은 어절에만 포함되고 음절 수에는 포함되지 않는다.
- 1초 미만 녹음은 신뢰할 수 없어 계산하지 않는다.
- 이 값은 참고 지표이며 합격/불합격 판단 근거로 쓰지 않는다(REQ-031 "AI는 보조 도구").
"""

import re
from typing import Any

_MIN_DURATION_SEC = 1.0
_HANGUL_SYLLABLE = re.compile(r"[가-힣]")
_WORD_CHAR = re.compile(r"[0-9A-Za-z가-힣]")


def count_words(text: str) -> int:
    """공백으로 나눈 토큰 중 글자/숫자가 하나라도 있는 것의 수(어절)."""
    return sum(1 for token in text.split() if _WORD_CHAR.search(token))


def count_syllables(text: str) -> int:
    """한글 음절(가-힣) 수."""
    return len(_HANGUL_SYLLABLE.findall(text))


def compute_speech_rate(text: Any, duration_sec: Any) -> dict | None:
    """계산할 수 없으면(텍스트 없음, 길이 부적합/1초 미만, 어절 0개) None."""
    if not isinstance(text, str) or isinstance(duration_sec, bool) or not isinstance(duration_sec, (int, float)):
        return None
    if not (duration_sec >= _MIN_DURATION_SEC):  # NaN도 여기서 걸러진다
        return None
    words = count_words(text)
    if words == 0:
        return None
    syllables = count_syllables(text)
    minutes = duration_sec / 60.0
    return {
        "word_count": words,
        "syllable_count": syllables,
        "words_per_minute": round(words / minutes, 1),
        "syllables_per_minute": round(syllables / minutes, 1),
        "speech_rate_basis": "total_duration",
    }


def attach_speech_rate(prosody: dict | None, text: Any) -> dict | None:
    """prosody 분석 결과에 발화 속도를 합쳐 새 dict로 돌려준다(원본 불변). 어떤 경우에도 예외를 내지 않는다
    — 부가 지표 실패가 턴 저장을 막으면 안 된다."""
    if prosody is None:
        return None
    try:
        rate = compute_speech_rate(text, prosody.get("duration_sec"))
    except Exception:  # noqa: BLE001 — 부가 지표 계산 실패는 삼키고 원본을 그대로 쓴다
        return prosody
    return {**prosody, **rate} if rate else prosody


def summarize_speech_rate(prosody_list: list[Any]) -> dict | None:
    """사용자 턴들의 prosody_json을 길이 가중으로 합산한다. 발화 속도가 계산된 턴이 없으면 None."""
    total_words = total_syllables = 0
    total_sec = 0.0
    per_turn_wpm: list[float] = []
    for p in prosody_list:
        if not isinstance(p, dict):
            continue
        words, syllables, duration = p.get("word_count"), p.get("syllable_count"), p.get("duration_sec")
        wpm = p.get("words_per_minute")
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (words, syllables, duration, wpm)):
            continue
        if duration <= 0:
            continue
        total_words += words
        total_syllables += syllables
        total_sec += duration
        per_turn_wpm.append(float(wpm))
    if not per_turn_wpm or total_sec <= 0:
        return None
    minutes = total_sec / 60.0
    return {
        "turns_measured": len(per_turn_wpm),
        "avg_words_per_minute": round(total_words / minutes, 1),
        "avg_syllables_per_minute": round(total_syllables / minutes, 1),
        "min_words_per_minute": round(min(per_turn_wpm), 1),
        "max_words_per_minute": round(max(per_turn_wpm), 1),
        "basis": "duration_weighted_total_duration",
    }
