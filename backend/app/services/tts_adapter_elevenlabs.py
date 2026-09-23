"""TTS 벤더 어댑터 — ElevenLabs (원안 §5.2.2, 2026-09-22 사용자 승인, unit-32).

**미검증 코드임을 명시**: 이 환경에 ElevenLabs API 키가 없어 **실제로 호출해본
적이 없다.** `app/services/tts_engine.py`의 `ITTSEngine` 인터페이스(`synthesize
(text) -> bytes`)를 그대로 구현해 기존 `get_tts_engine()` 팩토리(그 파일 참고)의
반환값만 이 클래스로 바꾸면 이론적으로는 교체 가능하지만, **API 키를 발급받아
실제로 한 번 호출해 검증하기 전까지는 프로덕션에 연결하지 않는다** — 요청 바디
필드명/응답 스키마가 문서와 실제 동작이 다를 가능성은 항상 있다(이 세션이
겪은 모든 실측 결함이 "코드 리뷰만으로는 안 보이고 실행해야 보였다"는 패턴이었다
— unit-23/24/25/27/28/31 note 전부 참고).

**왜 운영 파이프라인에 연결하지 않았는가**: `tts_engine.py`는 오늘 이미 실제
사고가 있었던 코드 근처(`interviews.py`)와 강하게 결합되어 있고, 이 클래스는
검증되지 않았다 — 검증 안 된 새 코드를 그 위에 얹지 않는다(unit-26/29와 동일
원칙).
"""
import json
import logging
import urllib.error
import urllib.request

from app.services.tts_engine import ITTSEngine, TtsSynthesisError

logger = logging.getLogger(__name__)

_API_BASE = "https://api.elevenlabs.io/v1"
_TIMEOUT_SECONDS = 10  # tts_engine.py의 Piper 타임아웃(§5.4)과 동일 예산으로 맞춤


class ElevenLabsTTSEngine(ITTSEngine):
    """ElevenLabs REST API(`POST /v1/text-to-speech/{voice_id}`)를 감싼다.

    사용법(실제 연결 시 `get_tts_engine()` 팩토리에서 이 클래스를 반환하도록
    교체): `ElevenLabsTTSEngine(api_key=..., voice_id=...)`.
    """

    def __init__(self, api_key: str, voice_id: str) -> None:
        self._api_key = api_key
        self._voice_id = voice_id

    def synthesize(self, text: str) -> bytes:
        payload = json.dumps(
            {
                "text": text,
                "model_id": "eleven_multilingual_v2",  # 한국어 지원 모델(ElevenLabs 문서 기준, 미검증)
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
            }
        ).encode("utf-8")

        request = urllib.request.Request(
            f"{_API_BASE}/text-to-speech/{self._voice_id}",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "xi-api-key": self._api_key,
                "Accept": "audio/mpeg",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as resp:
                return resp.read()  # MP3 바이트 — Piper(WAV)와 포맷이 다름, 호출부가 처리 필요(아래 참고)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise TtsSynthesisError("ElevenLabs 음성 합성 요청에 실패했습니다(미검증 어댑터).") from exc


# 미검증 주의사항(교체 시 반드시 확인):
# ElevenLabs는 MP3를 반환한다 — `tts_engine.py`의 나머지 파이프라인은 WAV를
# 전제한다(`synthesize_speech_file()`이 `.wav` 확장자로 저장). MP3->WAV 변환이
# 필요하거나, 프론트 오디오 플레이어가 MP3도 재생 가능한지 확인해야 한다.
