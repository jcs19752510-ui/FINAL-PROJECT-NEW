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

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

logger = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
_LLM_ROOT = _BACKEND_ROOT / "var" / "llm"
_MODEL_PATH = _LLM_ROOT / "models" / "qwen2.5-1.5b-instruct-q4_k_m.gguf"
_BIN_VULKAN = _LLM_ROOT / "bin_vulkan" / "llama-server.exe"
_BIN_CPU = _LLM_ROOT / "bin_cpu" / "llama-server.exe"
# DEF-009(unit-7-test.md TC-041): 워커 크래시로 llama-server 자식 프로세스가 고아로
# 남을 수 있다(운영체제가 자식을 자동으로 정리해주지 않음, Windows에서 부모 강제
# 종료 시 특히 그러함). ops가 사후에 수동으로 식별/정리할 수 있도록 PID를 파일로
# 남긴다 — Job 객체 기반의 "부모 종료 시 자식 자동 종료" 보장은 pywin32/ctypes가
# 필요한 별도 구현이라 이번 재작업 범위에서는 다루지 않는다(과설계 방지, 아래
# `_ensure_server_running()`의 이중 기동 방지가 관측된 결함(TC-041)의 핵심 원인은
# 이미 해소한다).
_PID_FILE = _LLM_ROOT / "llama-server.pid"

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

    @field_validator("speak_text")
    @classmethod
    def _speak_text_must_not_be_blank(cls, v: str) -> str:
        # DEF-006(unit-7-test.md TC-039): `min_length=1`은 공백만 있는 문자열도
        # 통과시켜 무음/빈 발화로 이어졌다. strip 후 재검증한다.
        stripped = v.strip()
        if not stripped:
            raise ValueError("speak_text는 공백만으로 구성될 수 없습니다.")
        return stripped


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
        try:
            _PID_FILE.write_text(str(proc.pid), encoding="utf-8")
        except OSError:
            logger.warning("llama-server PID 파일 기록 실패(치명적이지 않음)", exc_info=True)
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

        if _health_check():
            # DEF-009(unit-7-test.md TC-041): 이 프로세스 인스턴스가 아직 서버를
            # 기동한 적이 없는데도(예: 워커 재시작으로 `_process` 전역이 초기화된
            # 새 프로세스) 포트가 이미 응답한다면, 이전 워커 크래시로 남은 고아
            # llama-server이거나 다른 워커가 띄운 서버다. 새로 하나 더 띄우면
            # Windows에서 같은 포트에 이중 바인드되어 VRAM이 중복 소모된다(실측
            # 2,840MiB). 새 프로세스를 기동하지 않고 기존 서버를 그대로 재사용한다
            # (이 인스턴스는 그 서버의 Popen 핸들을 갖지 못하므로 자신의 수명 동안
            # 직접 종료할 수는 없다 — PID 파일(`_PID_FILE`)로 ops가 수동 식별 가능).
            logger.warning(
                "포트 %d에 이미 응답하는 llama-server가 있어 재사용합니다(신규 기동 생략, "
                "PID 파일: %s)",
                _SERVER_PORT,
                _PID_FILE,
            )
            _active_binary = None
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
    try:
        _PID_FILE.unlink(missing_ok=True)
    except OSError:
        pass


class StarOutput(BaseModel):
    """실측 결함(2026-09-21, 사용자 리포트 화면 확인): 1.5B 모델이 `star`를 스키마대로
    4개 필드 객체로 안 주고 하나의 문자열로 뭉쳐서 반환하는 경우가 있었다. 그 결과
    ReportLLMOutput 전체 검증이 실패해 star_json 없이 원본 LLM 응답 JSON 전체가
    `summary_text`(사람이 읽으라고 만든 폴백이 아니라 디버그용 원문)에 그대로
    저장되고, 리포트 화면이 그 raw JSON을 사용자에게 그대로 보여주는 문제로
    이어졌다. `model_validator(mode="before")`로 문자열 응답을 `situation`에 담아
    최소한 사람이 읽을 수 있는 리포트가 나오게 한다(4개 필드 완전 분리는 포기하되
    "리포트 자체가 깨져 보이는" 심각한 문제를 막는 것을 우선).
    """

    situation: str = ""
    task: str = ""
    action: str = ""
    result: str = ""

    @model_validator(mode="before")
    @classmethod
    def _coerce_flat_string(cls, data):
        if isinstance(data, str):
            return {"situation": data, "task": "", "action": "", "result": ""}
        return data


class ReportLLMOutput(BaseModel):
    """03-system-design.md §4.4 리포트 생성(`report_generation` job) 구조화 출력 계약 그대로.

    `overall_recommendation`을 Literal enum으로 선언해(REQ-031) "합격/불합격 확정"류
    값이 화이트리스트를 벗어나면 pydantic이 자동으로 거부한다.
    """

    star: StarOutput
    technical_accuracy: int = Field(ge=1, le=5)
    communication_clarity: int = Field(ge=1, le=5)
    cultural_fit: int = Field(ge=1, le=5)
    overall_recommendation: Literal["recommend", "neutral", "not_recommend"]
    # 원안(REQ-F-006/007) 복원분(2026-09-22 사용자 명시 승인, evaluation_report.py
    # 모듈 docstring 참고). optional + 기본 None — 모델이 생략해도 리포트 자체는
    # 깨지지 않는다(overall_recommendation 3단계가 여전히 1차 방어선).
    pass_fail_recommendation: Literal["pass", "fail", "borderline"] | None = None
    details: dict = Field(default_factory=dict)

    @field_validator("details", mode="before")
    @classmethod
    def _coerce_details(cls, v):
        # StarOutput과 동일한 이유(모델이 스키마를 완전히 지키지 않는 경우 대비) —
        # dict가 아니면 근거 텍스트로 감싸 리포트 자체가 깨지지 않게 한다.
        if not isinstance(v, dict):
            return {"note": str(v)}
        return v


def _call_chat_completions(system_prompt: str, user_message: str, max_tokens: int = 300) -> str:
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
            "max_tokens": max_tokens,
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


class ReportParsingFailed(Exception):
    """03-design §4.4 리포트 파싱 실패 폴백 경로 전용 예외.

    `LlmGenerationError`(서버 호출 자체 실패 — 완전한 job 실패, `report_status=failed`)와
    구분된다: 이 예외는 LLM 호출/응답 수신에는 성공했으나 JSON 스키마 파싱만
    실패한 경우이며, 호출부(worker/tasks.py)가 `raw_text`를 `EVALUATION_REPORTS.
    summary_text`(폴백 필드)에 저장하고 `report_status`는 그대로 `ready`로 표시한다.
    """

    def __init__(self, raw_text: str):
        super().__init__("LLM 리포트 출력 파싱에 실패했습니다.")
        self.raw_text = raw_text


# 03-design §4.4: STAR 4개 필드 + 근거(details)까지 요구해 턴 처리(300 토큰)보다
# 출력이 길다 — 컨텍스트(4096 토큰) 안에서 충분한 여유를 둔 값(실측 근거 없음,
# 이번 유닛의 구현 세부값).
_REPORT_MAX_TOKENS = 700


def generate_report_response(system_prompt: str, user_message: str) -> ReportLLMOutput:
    """03-design §4.4 리포트 생성 구조화 출력. 파싱 실패 시 최대 1회 재시도(턴 처리와
    동일 원칙) 후에도 실패하면 `ReportParsingFailed(raw_text=...)`를 던져 호출부가
    §3.1 `summary_text` 폴백 경로를 적용하게 한다. 서버 호출 자체가 실패하면(타임아웃
    등) `_call_chat_completions`가 던지는 `LlmGenerationError`가 그대로 전파된다 —
    이 경우는 파싱 폴백이 아니라 완전한 job 실패로 다뤄야 한다(호출부 책임).
    """
    raw = ""
    last_error: Exception | None = None
    for attempt in range(2):
        raw = _call_chat_completions(system_prompt, user_message, max_tokens=_REPORT_MAX_TOKENS)
        try:
            return ReportLLMOutput.model_validate_json(raw)
        except (ValidationError, json.JSONDecodeError) as exc:
            last_error = exc
            logger.warning("리포트 구조화 출력 파싱 실패(시도 %d/2): %s", attempt + 1, exc)
            continue
    logger.warning("리포트 파싱 재시도 소진 — summary_text 폴백으로 전환", exc_info=last_error)
    raise ReportParsingFailed(raw_text=raw)
