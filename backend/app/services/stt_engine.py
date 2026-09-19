"""ISTTEngine 어댑터 구현체 — faster-whisper `small`(CPU, int8) (03-system-design.md
§2.3 실측 근거, §4.5 어댑터 인터페이스 원칙).

REQ-004/REQ-005: 음성 턴 제출 시 실제로 동작하는 STT 변환. 이 모듈은 unit-4의
job_queue.py 스텁과 달리 **스텁이 아니다** — faster-whisper를 실제로 로드하고
오디오를 텍스트로 변환한다.

모델 로드는 수 초~수십 초가 걸리므로(03-design §2.3 실측: 17.78초, 본 유닛
재실측: 약 2~3초 — 실행 환경/캐시 상태에 따라 편차 있음) 프로세스당 1회만
로드하는 모듈 전역 싱글턴으로 관리한다. 매 요청마다 재로드하면 응답성이 무너진다.

**음성 원본 파일을 디스크에 쓰지 않는다**(03-design §6.2 최소수집 원칙) — 업로드된
바이트를 메모리 내 `BytesIO`로만 다루고 STT 변환이 끝나면 그대로 버려진다.
"""
import io
import logging
import threading

from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

_MODEL_LOCK = threading.Lock()
_model: WhisperModel | None = None

# 03-design §2.3 실측 선정값 그대로: small, CPU, int8.
_MODEL_SIZE = "small"
_DEVICE = "cpu"
_COMPUTE_TYPE = "int8"

# 이 플랫폼은 한국어 채용시장 대상(02-planning §2, DEC-011)이므로 언어를 한국어로
# 고정해 언어 자동감지 오버헤드를 없애고 정확도를 높인다(구현 세부값, 비가역성 낮음
# — 다국어 지원이 필요해지면 이 상수만 제거하고 자동감지로 되돌리면 됨).
_LANGUAGE = "ko"


class SttTranscriptionError(Exception):
    """오디오 디코딩 실패 등 STT 처리 중 발생한 모든 예외를 단일 계약으로 승격한다.

    호출부(app/api/v1/interviews.py)는 이 예외를 03-design §5.4의 `AI_SERVICE_TIMEOUT`
    (504)으로 매핑한다.
    """


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        with _MODEL_LOCK:
            if _model is None:
                logger.info(
                    "faster-whisper 모델 로딩 시작 (size=%s, device=%s, compute_type=%s)",
                    _MODEL_SIZE,
                    _DEVICE,
                    _COMPUTE_TYPE,
                )
                _model = WhisperModel(_MODEL_SIZE, device=_DEVICE, compute_type=_COMPUTE_TYPE)
                logger.info("faster-whisper 모델 로딩 완료")
    return _model


def transcribe_audio(audio_bytes: bytes) -> str:
    """업로드된 오디오 바이트를 텍스트로 변환한다.

    faster-whisper(PyAV 기반)는 파일 경로뿐 아니라 파일류 객체(BinaryIO)도 직접
    디코딩할 수 있어, 디스크에 임시파일을 쓰지 않고 메모리에서 바로 처리한다.
    """
    model = _get_model()
    try:
        segments, _info = model.transcribe(io.BytesIO(audio_bytes), language=_LANGUAGE)
        return "".join(segment.text for segment in segments).strip()
    except Exception as exc:  # noqa: BLE001 — 디코딩 실패 등 다양한 하위 예외를 단일 계약으로 승격
        raise SttTranscriptionError("음성 인식 처리에 실패했습니다.") from exc
