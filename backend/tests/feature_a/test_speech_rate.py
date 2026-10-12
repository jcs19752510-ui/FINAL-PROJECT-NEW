"""발화 속도 지표(app/services/speech_rate.py) 내부 테스트 — 순수 함수라 DB·서버 불필요.
실행: DATABASE_URL, JWT_SECRET_KEY 더미 환경변수 필요(conftest 가 설정 모듈을 불러옴)."""

import math

import pytest

from app.services.speech_rate import (
    attach_speech_rate,
    compute_speech_rate,
    count_syllables,
    count_words,
    summarize_speech_rate,
)


def test_sr01_counts_korean_words_and_syllables():
    assert count_words("저는 백엔드 개발자입니다") == 3
    assert count_syllables("저는 백엔드 개발자입니다") == 11  # 저는(2)+백엔드(3)+개발자입니다(6)


def test_sr02_words_ignore_punctuation_only_tokens_and_extra_spaces():
    assert count_words("  네 ,  그렇습니다 ...  ") == 2
    assert count_words("") == 0 and count_words("... ,,, !!!") == 0


def test_sr03_syllables_exclude_latin_and_digits_but_words_include_them():
    text = "MSA 서비스 3개"
    assert count_words(text) == 3
    assert count_syllables(text) == 4  # 서비스(3) + 개(1)


def test_sr04_compute_rate_values():
    r = compute_speech_rate("하나 둘 셋 넷 다섯 여섯", 6.0)  # 6어절 / 6초 = 60 어절/분
    assert r["word_count"] == 6 and r["words_per_minute"] == 60.0
    assert r["syllable_count"] == 9 and r["syllables_per_minute"] == 90.0  # 하나(2)+둘+셋+넷+다섯(2)+여섯(2)
    assert r["speech_rate_basis"] == "total_duration"


@pytest.mark.parametrize("duration", [0, 0.5, 0.999, -3, float("nan"), None, "6", True])
def test_sr05_unreliable_duration_returns_none(duration):
    assert compute_speech_rate("충분히 긴 문장입니다", duration) is None


def test_sr06_boundary_exactly_one_second_is_computed():
    assert compute_speech_rate("네 알겠습니다", 1.0)["words_per_minute"] == 120.0


@pytest.mark.parametrize("text", [None, 123, "", "   ", "... !!!"])
def test_sr07_empty_or_nontext_returns_none(text):
    assert compute_speech_rate(text, 10.0) is None


def test_sr08_attach_merges_without_mutating_original():
    original = {"duration_sec": 10.0, "pitch_mean_hz": 120.5}
    result = attach_speech_rate(original, "안녕하세요 저는 지원자입니다")
    assert original == {"duration_sec": 10.0, "pitch_mean_hz": 120.5}  # 원본 불변
    assert result["pitch_mean_hz"] == 120.5 and result["words_per_minute"] == 18.0  # 3어절 / 10초


def test_sr09_attach_handles_none_missing_duration_and_bad_input():
    assert attach_speech_rate(None, "텍스트") is None
    p = {"pitch_mean_hz": 100.0}  # duration 없음 → 원본 그대로
    assert attach_speech_rate(p, "텍스트입니다") == p
    assert attach_speech_rate({"duration_sec": 5.0}, None) == {"duration_sec": 5.0}


def test_sr10_attach_never_raises_even_with_weird_prosody_type():
    class Weird(dict):
        def get(self, *a, **k):
            raise RuntimeError("boom")

    weird = Weird(duration_sec=5.0)
    assert attach_speech_rate(weird, "텍스트입니다") is weird  # 예외를 삼키고 원본 반환


def test_sr11_summarize_is_duration_weighted():
    a = attach_speech_rate({"duration_sec": 60.0}, " ".join(["가"] * 60))  # 60어절/분
    b = attach_speech_rate({"duration_sec": 30.0}, " ".join(["나"] * 90))  # 180어절/분
    s = summarize_speech_rate([a, b])
    assert s["turns_measured"] == 2
    assert s["avg_words_per_minute"] == pytest.approx(100.0)  # (60+90 어절)/(1.5분), 단순 평균(120)이 아님
    assert s["min_words_per_minute"] == 60.0 and s["max_words_per_minute"] == 180.0


def test_sr12_summarize_skips_turns_without_rate_and_returns_none_when_empty():
    assert summarize_speech_rate([]) is None
    assert summarize_speech_rate([None, {}, {"duration_sec": 5.0}, "x"]) is None
    good = attach_speech_rate({"duration_sec": 10.0}, "하나 둘 셋")
    s = summarize_speech_rate([None, {"duration_sec": 4.0}, good])
    assert s["turns_measured"] == 1 and s["avg_words_per_minute"] == 18.0


def test_sr13_summarize_ignores_corrupt_numeric_fields():
    bad = {"word_count": "3", "syllable_count": 3, "duration_sec": 6.0, "words_per_minute": 30.0}
    assert summarize_speech_rate([bad]) is None
    zero = {"word_count": 3, "syllable_count": 3, "duration_sec": 0, "words_per_minute": 30.0}
    assert summarize_speech_rate([zero]) is None


def test_sr14_no_nan_or_inf_in_outputs():
    r = compute_speech_rate("하나 둘", 1.0)
    assert all(math.isfinite(v) for v in r.values() if isinstance(v, float))
