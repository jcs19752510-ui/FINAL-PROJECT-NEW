"""STT 벤더 어댑터 — Deepgram Nova-2 (원안 §5.2.1, 2026-09-22 사용자 승인, unit-32).

2026-09-23 사용자 제공 키로 실제 호출 검증 완료(unit-32-test.md 후속 TC-002/003).
2026-09-23(DEC-063, unit-32 재후속): `app/services/stt_router.py`를 통해 실제
음성 제출 경로(`app/api/v1/interviews.py`)에 배선 완료 — 더 이상 미검증·미배선
코드가 아니다.

이번 구현은 **배치 호출**(전체 오디오를 한 번에 업로드, 원안의 스트리밍
"<300ms" 목표는 미달성)만 구현했다 — `app/services/stt_engine.transcribe_audio()`
와 동일한 함수 시그니처(오디오 바이트 → 텍스트)를 맞춰, 팩토리에서 교체만
하면 되도록 설계했다. 진짜 스트리밍(청크 단위 실시간)은 WebSocket 기반 별도
구현이 필요하며 ③ 매트릭스의 "STT 실시간 스트리밍 전환" 항목(별도 unit-36)과
얽혀 있다.
"""
import json
import logging
import urllib.error
import urllib.request

from app.services.stt_engine import SttTranscriptionError

logger = logging.getLogger(__name__)

_API_URL = "https://api.deepgram.com/v1/listen"
_TIMEOUT_SECONDS = 10
_QUERY_PARAMS = "?model=nova-2&language=ko&smart_format=true"


def transcribe_audio_deepgram(audio_bytes: bytes, api_key: str, content_type: str = "audio/wav") -> str:
    """`stt_engine.transcribe_audio(audio_bytes)`와 동일한 시그니처(키·content_type
    인자만 추가) — `stt_router.transcribe_audio_smart()`가 이 함수를 호출한다.

    `content_type`은 호출부(`interviews.py`)가 받은 멀티파트 업로드 파일의 실제
    MIME 타입을 그대로 전달해야 한다(Deepgram은 Content-Type으로 오디오 포맷을
    추론). 값이 없으면 기본값 `audio/wav`로 폴백한다.
    """
    request = urllib.request.Request(
        _API_URL + _QUERY_PARAMS,
        data=audio_bytes,
        headers={
            "Authorization": f"Token {api_key}",
            "Content-Type": content_type or "audio/wav",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SttTranscriptionError("Deepgram 음성 인식 요청에 실패했습니다(미검증 어댑터).") from exc
    except json.JSONDecodeError as exc:
        raise SttTranscriptionError("Deepgram 응답을 파싱할 수 없습니다(미검증 어댑터).") from exc

    try:
        # Deepgram 응답 스키마(공식 문서 기준, 실측 미확인):
        # results.channels[0].alternatives[0].transcript
        return body["results"]["channels"][0]["alternatives"][0]["transcript"].strip()
    except (KeyError, IndexError) as exc:
        raise SttTranscriptionError("Deepgram 응답 스키마가 예상과 다릅니다(미검증 어댑터).") from exc
