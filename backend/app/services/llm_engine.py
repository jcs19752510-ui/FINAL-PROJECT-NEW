"""ILLMEngine 어댑터 구현체 — Qwen2.5-1.5B-Instruct GGUF via llama.cpp `llama-server`
(03-system-design.md §2.4 실측/선정 근거, DEC-025 — 1.5B Apache-2.0 확정, §4.4 구조화
출력 계약, §4.5 어댑터 인터페이스 원칙).

**실제 동작 방식(unit-7이 실측으로 확정)**: 이 프로세스(Celery AI Worker)에
`llama-cpp-python`을 파이썬 패키지로 import하지 않는다 — 3단계(DEC-016)와 동일하게
이 환경(Python 3.13, Windows)에서 `pip install llama-cpp-python`을 재시도한 결과도
동일한 두 실패(Windows MAX_PATH 260자 제한으로 소스빌드 실패, Python 3.13용 PyPI
프리빌드 휠 부재)를 다시 확인했다(unit-7-note.md §6 재현 로그). 그 대신 **llama.cpp
공식 GitHub Release의 미리 컴파일된 `llama-server.exe` 실행파일**을 서브프로세스로
기동하고 OpenAI 호환 HTTP API(`/v1/chat/completions`)로 통신하는 방식(오케스트레이터
지시의 방법 (b))을 사용한다 — Python 패키지 빌드 자체가 필요 없어 Windows 긴경로
문제를 원천 회피한다.

**GPU 가속 실측**: `llama-b11050-bin-win-vulkan-x64.zip`(Vulkan 백엔드, CUDA 툴킷
설치 없이도 GPU 드라이버만으로 동작)로 `-ngl 99`(전체 레이어 GPU 오프로드) 실행 시
`nvidia-smi` VRAM 사용량이 598MiB → 1717MiB로 실측 증가해 실제로 GPU에 모델이
상주함을 확인했다(가용 3387MiB 예산 안에 여유 있게 들어옴, DEC-025 1.5B 선택과
정합). 응답 지연도 실측으로 확인(아래 `generate_turn_response` 호출 시 약 2~3초,
unit-7-note.md §6). 이 바이너리가 어떤 이유로든 기동에 실패하면(Vulkan 드라이버
부재 등) `llama-b11050-bin-win-cpu-x64.zip`(CPU 전용)으로 자동 폴백해 "최소한 실제로
텍스트가 생성되는" 상태를 항상 보장한다(오케스트레이터 지시 — 완전 스텁 금지).
"""
import atexit
import json
import logging
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
_LLM_ROOT = _BACKEND_ROOT / "var" / "llm"
_MODEL_PATH = _LLM_ROOT / "models" / "qwen2.5-1.5b-instruct-q4_k_m.gguf"
_BIN_VULKAN = _LLM_ROOT / "bin_vulkan" / "llama-server.exe"
_BIN_CPU = _LLM_ROOT / "bin_cpu" / "llama-server.exe"

# 03-design §5.4: LLM 단계 타임아웃 25초. 서버 기동/헬스체크는 별도 예산(모델 로드
# 1회성, §5.3과 동일 원칙 — 워커 상시 기동으로 상쇄).
_SERVER_PORT = 8091
_SERVER_STARTUP_TIMEOUT_SECONDS = 60
_GENERATION_TIMEOUT_SECONDS = 25
_CONTEXT_SIZE = 4096


class LlmGenerationError(Exception):
    """서버 기동 실패, HTTP 호출 실패/타임아웃, 구조화 출력 파싱 재시도 소진 등
    LLM 처리 중 발생한 모든 예외를 단일 계약으로 승격한다(stt_engine.py/
    tts_engine.py와 동일 원칙). 호출부는 03-design §4.4 "안전 기본값 폴백" 또는
    §5.4 `AI_SERVICE_TIMEOUT`으로 매핑한다.
    """


class TurnLLMOutput(BaseModel):
    """03-system-design.md §4.4 턴 처리 구조화 출력 계약 그대로.

    `control`을 Literal enum으로 선언해 화이트리스트 외 값은 pydantic이 자동으로
    거부하게 한다(REQ-037 방향과 정합 — 이 유닛은 그 자체를 "구현"하지는 않으나,
    구조화 출력을 강제하는 이 설계가 그 전제를 만족시킨다).
    """

    speak_text: str = Field(min_length=1)
    control: Literal["next_question", "end_interview", "switch_to_coding", "none"] = "none"
    technical_accuracy: int | None = Field(default=None, ge=1, le=5)
    communication_clarity: int | None = Field(default=None, ge=1, le=5)
    key_observations: list[str] = Field(default_factory=list)
    rubric_match: dict = Field(default_factory=dict)


_process: subprocess.Popen | None = None
_process_lock = threading.Lock()
_active_binary: Path | None = None


def _health_check(timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{_SERVER_PORT}/health", timeout=timeout) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


def _wait_for_health(proc: subprocess.Popen, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return False
        if _health_check():
            return True
        time.sleep(0.5)
    return False


def _launch(binary: Path, n_gpu_layers: int) -> subprocess.Popen | None:
    if not binary.exists():
        return None
    proc = subprocess.Popen(
        [
            str(binary),
            "-m", str(_MODEL_PATH),
            "--port", str(_SERVER_PORT),
            "-c", str(_CONTEXT_SIZE),
            "-ngl", str(n_gpu_layers),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=str(binary.parent),
    )
    if _wait_for_health(proc, _SERVER_STARTUP_TIMEOUT_SECONDS):
        return proc
    proc.terminate()
    return None


def _ensure_server_running() -> None:
    """§4.5 어댑터 원칙: llama-server 서브프로세스를 이 워커 프로세스 수명 동안
    1회만 기동해 재사용한다(모델 로드는 STT/TTS와 마찬가지로 1회성 비용).

    Vulkan(GPU) 빌드를 먼저 시도하고, 어떤 이유로든 기동에 실패하면(드라이버 부재,
    바이너리 손상 등) CPU 전용 빌드로 자동 폴백한다 — "느려도 실제로 동작하는 것"을
    항상 보장한다(오케스트레이터 지시).
    """
    global _process, _active_binary
    if _process is not None and _process.poll() is None and _health_check():
        return

    with _process_lock:
        if _process is not None and _process.poll() is None and _health_check():
            return

        if not _MODEL_PATH.exists():
            raise LlmGenerationError(f"LLM 모델 파일을 찾을 수 없습니다: {_MODEL_PATH}")

        logger.info("llama-server(GPU/Vulkan) 기동 시도")
        proc = _launch(_BIN_VULKAN, n_gpu_layers=99)
        active = _BIN_VULKAN
        if proc is None:
            logger.warning("llama-server(GPU/Vulkan) 기동 실패 — CPU 전용 빌드로 폴백")
            proc = _launch(_BIN_CPU, n_gpu_layers=0)
            active = _BIN_CPU
        if proc is None:
            raise LlmGenerationError("llama-server를 GPU/CPU 어느 쪽으로도 기동할 수 없습니다.")

        _process = proc
        _active_binary = active
        atexit.register(_shutdown)
        logger.info("llama-server 기동 완료 (binary=%s)", active.parent.name)


def _shutdown() -> None:
    global _process
    if _process is not None and _process.poll() is None:
        _process.terminate()
        try:
            _process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _process.kill()
    _process = None


def _call_chat_completions(system_prompt: str, user_message: str) -> str:
    """llama-server의 `/v1/chat/completions`(OpenAI 호환 API)를 호출한다.

    **역할 분리(03-design §6.3 프롬프트 인젝션 방어 — 이 유닛이 최소한으로 갖추는
    구조)**: 시스템 프롬프트와 사용자 입력을 chat template의 `system`/`user` role
    필드로 분리해 전달한다. 문자열 concat으로 하나의 프롬프트를 직접 조립하지
    않는다 — llama.cpp가 모델의 chat template(Qwen2.5 ChatML)에 따라 각 role을
    구분된 스페셜 토큰으로 렌더링하므로, 사용자 입력이 시스템 지시를 문자열
    수준에서 덮어쓸 수 없다. (완전한 인젝션 방어는 아니며, 그 전체 구현은
    REQ-035/unit-8 범위다 — 03-design §6.3 "잔여 리스크" 그대로.)
    """
    _ensure_server_running()

    payload = json.dumps(
        {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": 300,
            "temperature": 0.6,
            "response_format": {"type": "json_object"},
        },
        ensure_ascii=False,
    ).encode("utf-8")

    request = urllib.request.Request(
        f"http://127.0.0.1:{_SERVER_PORT}/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_GENERATION_TIMEOUT_SECONDS) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise LlmGenerationError("LLM 서버 호출에 실패했습니다.") from exc

    try:
        return body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LlmGenerationError("LLM 응답 형식이 올바르지 않습니다.") from exc


def generate_turn_response(system_prompt: str, user_message: str) -> TurnLLMOutput:
    """03-design §4.4: 파싱 실패 시 최대 1회 재시도, 그래도 실패하면 호출부가
    안전 기본값으로 폴백한다(이 함수는 재시도까지만 책임지고, 최종 실패는
    `LlmGenerationError`로 알려 호출부(worker/tasks.py)가 폴백을 적용하게 한다).
    """
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            raw = _call_chat_completions(system_prompt, user_message)
            return TurnLLMOutput.model_validate_json(raw)
        except (ValidationError, json.JSONDecodeError) as exc:
            last_error = exc
            logger.warning("LLM 구조화 출력 파싱 실패(시도 %d/2): %s", attempt + 1, exc)
            continue
    raise LlmGenerationError("LLM이 유효한 구조화 출력을 생성하지 못했습니다.") from last_error
