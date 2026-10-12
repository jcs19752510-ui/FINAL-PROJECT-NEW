"""STT 벤더 선택 — 기본은 로컬 faster-whisper. `ONPREM_MODE=false`이고 Deepgram 키가 설정된
경우에만 Deepgram을 먼저 시도하고, 실패하면 faster-whisper로 자동 폴백한다(unit-32 후속, DEC-063).

운영 기본값은 로컬 faster-whisper다(DEC-005) — 2026-10-12(사용자 지시) 이후에는 `ONPREM_MODE`
(기본 True)가 켜져 있으면 `DEEPGRAM_API_KEY`가 `.env`/환경변수에 남아 있어도 **Deepgram을 절대
호출하지 않는다**(지원자 음성이 외부로 나가지 않도록 코드로 차단). 사용자 턴 제출을 벤더 장애로
막지 않기 위한 그레이스풀 디그레이드(Deepgram 실패 → 로컬 폴백)는 온프리미스 모드를 끈 경우에
그대로 유지된다.
"""
import logging

from app.core.config import settings
from app.services.stt_adapter_deepgram import transcribe_audio_deepgram
from app.services.stt_engine import SttTranscriptionError, transcribe_audio

logger = logging.getLogger(__name__)

_blocked_key_warned = False


def _warn_blocked_key_once() -> None:
    """키가 남아 있는데 차단된 상태를 운영자가 알 수 있도록 프로세스당 한 번만 경고한다."""
    global _blocked_key_warned
    if not _blocked_key_warned:
        _blocked_key_warned = True
        logger.warning(
            "DEEPGRAM_API_KEY가 설정돼 있으나 ONPREM_MODE로 차단됨 — 로컬 faster-whisper로 처리합니다. "
            "키를 .env/환경변수에서 제거하고 Deepgram 콘솔에서 폐기하는 것을 권장합니다."
        )


def transcribe_audio_smart(audio_bytes: bytes, content_type: str | None) -> str:
    if settings.deepgram_api_key:
        if settings.onprem_mode:
            _warn_blocked_key_once()
        else:
            try:
                return transcribe_audio_deepgram(audio_bytes, settings.deepgram_api_key, content_type or "audio/wav")
            except SttTranscriptionError:
                logger.warning("Deepgram STT 실패 — faster-whisper로 폴백", exc_info=True)
    return transcribe_audio(audio_bytes)
