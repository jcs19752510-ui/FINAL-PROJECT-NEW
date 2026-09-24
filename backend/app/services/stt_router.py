"""STT 벤더 선택 — Deepgram(키 설정 시) 우선 시도, 미설정·실패 시 faster-whisper로
자동 폴백 (unit-32 후속, DEC-063).

운영 기본값은 여전히 무료 로컬 faster-whisper다(DEC-005 유지) — `DEEPGRAM_API_KEY`가
`.env`에 설정된 경우에만 Deepgram을 먼저 시도하고, 네트워크 오류·크레딧 소진 등으로
실패하면 조용히 faster-whisper로 넘어간다(사용자 턴 제출을 벤더 장애로 막지 않기
위한 그레이스풀 디그레이드 — `whiteboard_vision.py`의 GPU→CPU 폴백과 동일 원칙).
"""
import logging

from app.core.config import settings
from app.services.stt_adapter_deepgram import transcribe_audio_deepgram
from app.services.stt_engine import SttTranscriptionError, transcribe_audio

logger = logging.getLogger(__name__)


def transcribe_audio_smart(audio_bytes: bytes, content_type: str | None) -> str:
    if settings.deepgram_api_key:
        try:
            return transcribe_audio_deepgram(audio_bytes, settings.deepgram_api_key, content_type or "audio/wav")
        except SttTranscriptionError:
            logger.warning("Deepgram STT 실패 — faster-whisper로 폴백", exc_info=True)
    return transcribe_audio(audio_bytes)
