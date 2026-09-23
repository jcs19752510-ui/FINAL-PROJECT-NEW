"""STT 벤더 어댑터 — Deepgram Nova-2 (원안 §5.2.1, 2026-09-22 사용자 승인, unit-32).

**미검증 코드임을 명시**(`tts_adapter_elevenlabs.py`와 동일 원칙 — 이 파일
docstring 반복 대신 그쪽을 참고). Deepgram API 키가 없어 실제 호출 검증 못함.

이번 구현은 **배치 호출**(전체 오디오를 한 번에 업로드, 원안의 스트리밍
"<300ms" 목표는 미달성)만 구현했다 — `app/services/stt_engine.transcribe_audio()`
와 동일한 함수 시그니처(오디오 바이트 → 텍스트)를 맞춰, 팩토리에서 교체만
하면 되도록 설계했다. 진짜 스트리밍(청크 단위 실시간)은 WebSocket 기반 별도
구현이 필요하며 ③ 매트릭스의 "STT 실시간 스트리밍 전환" 항목(보류 중)과
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


def transcribe_audio_deepgram(audio_bytes: bytes, api_key: str) -> str:
    """`stt_engine.transcribe_audio(audio_bytes)`와 동일한 시그니처(키 인자만
    추가) — 팩토리 교체 시 이 함수로 바꾸기만 하면 호출부(`interviews.py`)는
    수정할 필요가 최소화되도록 설계.
    """
    request = urllib.request.Request(
        _API_URL + _QUERY_PARAMS,
        data=audio_bytes,
        headers={
            "Authorization": f"Token {api_key}",
            # 업로드 포맷은 클라이언트가 보내는 실제 코덱에 맞춰야 한다(webm/wav 등) —
            # Deepgram은 Content-Type으로 포맷을 추론하므로, 실제 연결 시
            # `interviews.py`가 받는 멀티파트 파일의 content_type을 그대로 전달해야
            # 한다(현재는 미검증 상태라 고정값을 쓰지 않고 이 자리에 표시만 해둠).
            "Content-Type": "audio/wav",  # 실제 연결 시 업로드 파일의 실제 MIME 타입으로 교체 필요
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
