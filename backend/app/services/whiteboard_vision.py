"""화이트보드 AI 비전 분석 (원안 REQ-021, 2026-09-23 사용자 승인, unit-35).

**3단계로 나눠서 구현했고, 검증 상태가 서로 다르다**:

1. **렌더링(좌표 → PNG 이미지)** — `render_strokes_to_png()`. 외부 API가 전혀
   필요 없어 **실제로 구현·테스트했다**(unit-35-test.md 참고). `whiteboard.py`
   가 저장하는 것은 원시 좌표(`WhiteboardStroke` — points/color/width)이지
   이미지가 아니므로, 비전 모델에 넣기 전에 이 렌더링이 반드시 선행돼야 한다.
2. **비전 모델 호출(유료, GPT-4V)** — `analyze_diagram_with_vision()`. 다른
   벤더 어댑터(unit-32)와 동일한 이유로 **API 키가 없어 미검증**이며, 프로젝트의
   "유료 항목은 진행하지 않는다" 방침(2026-09-23 사용자 확인)에 따라 이후에도
   실제로 연결하지 않는다 — 코드만 참고용으로 남겨둔다.
3. **비전 모델 호출(무료, 로컬 SmolVLM)** — `analyze_diagram_local()`. llama.cpp
   `llama-server`의 멀티모달(`--mmproj`) 지원으로 SmolVLM-500M-Instruct를
   로컬 서브프로세스로 구동해 실제로 호출한다(llm_engine.py의 Qwen 서브프로세스
   패턴을 그대로 따름). **실측 결과 이 모델의 한국어 다이어그램 설명 품질은
   낮다**(한 단어/단편적 답변, 지시사항을 온전히 따르지 못함 — 이전 세션의
   `.harness-tmp/test_smolvlm500_probe.py` 실측 로그 근거). 사용자가 "낮은
   품질이라도 그대로 연결"하기로 명시적으로 결정했으므로(품질 개선 조건 없이
   진행), `_LOW_CONFIDENCE_DISCLAIMER`를 모든 응답에 항상 동봉해 사용자가
   결과를 맹신하지 않도록 한다.

DEC-008(03-system-design.md)이 "AI가 화이트보드를 시각적으로 분석하는 기능은
Out-of-Scope(REQ-021)"라고 명시한 결정을 이 유닛이 뒤집는다 — 사용자가 이를
인지한 상태에서 승인해 진행한다.
"""
import base64
import io
import json
import logging
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

_CANVAS_SIZE = (1200, 800)  # 04-ux-design 캔버스 좌표계 기준(스트로크 좌표가 이 범위라고 가정)
_BACKGROUND = "white"


class WhiteboardRenderError(Exception):
    pass


class VisionAnalysisError(Exception):
    pass


def render_strokes_to_png(strokes: list[dict]) -> bytes:
    """`WhiteboardStroke` 리스트(각 {"points":[{"x","y"},...],"color","width"})를
    실제 PNG 이미지 바이트로 래스터라이즈한다. 외부 의존성 없음(Pillow만 사용) —
    이 함수는 실제로 실행·검증됨(unit-35-test.md).
    """
    try:
        img = Image.new("RGB", _CANVAS_SIZE, _BACKGROUND)
        draw = ImageDraw.Draw(img)
        for stroke in strokes:
            points = [(p["x"], p["y"]) for p in stroke["points"]]
            if len(points) == 0:
                # 실측 결함(2026-09-23): PIL의 `draw.line([], ...)`는 예외 없이
                # 조용히 아무것도 그리지 않는다 — 빈 stroke를 소리 없이 무시하는
                # 대신 명시적으로 거부한다(스키마 계약상 도달하면 안 되는 상태,
                # `schemas/whiteboard.py`의 `_points_bounds`가 API 경계에서 이미
                # 막지만 이 함수 자체의 방어도 필요).
                raise WhiteboardRenderError("빈 stroke(points 없음)는 렌더링할 수 없습니다.")
            if len(points) == 1:
                x, y = points[0]
                r = max(stroke["width"] / 2, 1)
                draw.ellipse([x - r, y - r, x + r, y + r], fill=stroke["color"])
            else:
                draw.line(points, fill=stroke["color"], width=max(int(stroke["width"]), 1), joint="curve")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except (KeyError, TypeError, ValueError) as exc:
        raise WhiteboardRenderError("스트로크 데이터를 렌더링할 수 없습니다.") from exc


# --- 아래부터 미검증(API 키 없음, tts_adapter_elevenlabs.py 등과 동일 원칙) --------

_API_URL = "https://api.openai.com/v1/chat/completions"
_TIMEOUT_SECONDS = 20
_VISION_PROMPT = (
    "이 이미지는 기술 면접 지원자가 화이트보드에 그린 시스템 설계 다이어그램입니다. "
    "다이어그램에 나타난 아키텍처의 타당성을 한국어로 간단히 평가하세요. "
    "구성 요소, 데이터 흐름, 잠재적 병목/단일 장애점을 언급하세요."
)


def analyze_diagram_with_vision(png_bytes: bytes, api_key: str) -> str:
    """OpenAI GPT-4V(`gpt-4o` 등 비전 지원 모델) Chat Completions API를 호출한다.
    **미검증** — API 키가 없어 실제로 호출해본 적 없음(모듈 docstring 참고).
    """
    image_b64 = base64.b64encode(png_bytes).decode("ascii")
    payload = json.dumps(
        {
            "model": "gpt-4o",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _VISION_PROMPT},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                    ],
                }
            ],
            "max_tokens": 500,
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        _API_URL,
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return body["choices"][0]["message"]["content"].strip()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise VisionAnalysisError("GPT-4V 요청에 실패했습니다(미검증 어댑터).") from exc
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        raise VisionAnalysisError("GPT-4V 응답 스키마가 예상과 다릅니다(미검증 어댑터).") from exc


# --- 아래부터 실제 연결(로컬 SmolVLM, 무료) ----------------------------------
# llm_engine.py와 동일한 llama-server 서브프로세스 패턴이지만, 포트를 분리해
# Qwen(8091)과 동시에 떠 있을 수 있게 한다. 모델이 작아(500M) 같은 CPU에서도
# 감당 가능한 크기다.

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
_LLM_ROOT = _BACKEND_ROOT / "var" / "llm"
_VLM_MODEL_PATH = _LLM_ROOT / "models" / "smolvlm-500m-instruct-q8.gguf"
_VLM_MMPROJ_PATH = _LLM_ROOT / "models" / "smolvlm-mmproj-f16.gguf"
_VLM_BIN_VULKAN = _LLM_ROOT / "bin_vulkan" / "llama-server.exe"
_VLM_BIN_CPU = _LLM_ROOT / "bin_cpu" / "llama-server.exe"
_VLM_SERVER_PORT = 8093
_VLM_STARTUP_TIMEOUT_SECONDS = 60
_VLM_GENERATION_TIMEOUT_SECONDS = 30

# 실측 근거: 이전 세션 `.harness-tmp/test_smolvlm500_probe.py`로 캡션/OCR성/도형개수/
# 색상질문/다이어그램설명 5개 프롬프트를 테스트한 결과, SmolVLM-500M-Instruct는
# 한두 단어 또는 부정확한 단편 답변을 반환했다(예: 박스 개수를 묻는 질문에 틀린
# 숫자, 다이어그램 설명 요청에 "Client, Server, Database"처럼 라벨만 나열). 이
# 문구는 정확도 개선과 무관하게 응답마다 항상 동봉한다(사용자 2026-09-23 결정).
LOW_CONFIDENCE_DISCLAIMER = (
    "⚠️ AI 참고용 — 이 분석은 저사양 로컬 모델(SmolVLM-500M, 500M 파라미터)이 "
    "생성했으며 정확도가 낮습니다. 다이어그램 요소를 놓치거나 잘못 설명할 수 있으니 "
    "참고용으로만 사용하고, 실제 평가·채점의 근거로 단독 사용하지 마세요."
)

_vlm_process: subprocess.Popen | None = None
_vlm_process_lock = threading.Lock()


def _vlm_health_check(timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{_VLM_SERVER_PORT}/health", timeout=timeout) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


def _vlm_wait_for_health(proc: subprocess.Popen, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return False
        if _vlm_health_check():
            return True
        time.sleep(0.5)
    return False


def _vlm_launch(binary: Path, n_gpu_layers: int) -> subprocess.Popen | None:
    if not binary.exists():
        return None
    proc = subprocess.Popen(
        [
            str(binary),
            "-m", str(_VLM_MODEL_PATH),
            "--mmproj", str(_VLM_MMPROJ_PATH),
            "--port", str(_VLM_SERVER_PORT),
            "-c", "4096",
            "-ngl", str(n_gpu_layers),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=str(binary.parent),
    )
    if _vlm_wait_for_health(proc, _VLM_STARTUP_TIMEOUT_SECONDS):
        return proc
    proc.terminate()
    return None


def _ensure_vlm_server_running() -> None:
    """llm_engine.py `_ensure_server_running()`과 동일 원칙(1회만 기동, GPU 실패
    시 CPU 폴백) — 다만 이 서버는 8093 포트를 써서 8091(Qwen)과 공존한다."""
    global _vlm_process
    if _vlm_process is not None and _vlm_process.poll() is None and _vlm_health_check():
        return

    with _vlm_process_lock:
        if _vlm_process is not None and _vlm_process.poll() is None and _vlm_health_check():
            return
        if _vlm_health_check():
            logger.warning("포트 %d에 이미 응답하는 SmolVLM 서버가 있어 재사용합니다.", _VLM_SERVER_PORT)
            return
        if not _VLM_MODEL_PATH.exists() or not _VLM_MMPROJ_PATH.exists():
            raise VisionAnalysisError(f"SmolVLM 모델 파일을 찾을 수 없습니다: {_VLM_MODEL_PATH}")

        logger.info("SmolVLM llama-server(GPU/Vulkan) 기동 시도")
        proc = _vlm_launch(_VLM_BIN_VULKAN, n_gpu_layers=99)
        if proc is None:
            logger.warning("SmolVLM llama-server(GPU/Vulkan) 기동 실패 — CPU 전용 빌드로 폴백")
            proc = _vlm_launch(_VLM_BIN_CPU, n_gpu_layers=0)
        if proc is None:
            raise VisionAnalysisError("SmolVLM llama-server를 GPU/CPU 어느 쪽으로도 기동할 수 없습니다.")
        _vlm_process = proc
        logger.info("SmolVLM llama-server 기동 완료")


_LOCAL_VISION_PROMPT = "Describe the boxes and their labels in this diagram."


def analyze_diagram_local(png_bytes: bytes) -> str:
    """로컬 SmolVLM-500M-Instruct(무료, GPU/CPU 자동 폴백)로 다이어그램을 설명한다.

    호출부(`app/api/v1/whiteboard.py`)는 이 함수의 반환값에 항상
    `LOW_CONFIDENCE_DISCLAIMER`를 동봉해 응답한다 — 이 함수 자체는 원문 설명만
    반환한다(disclaimer 조립은 API 계층 책임, 다른 어댑터와 동일한 관심사 분리).
    """
    _ensure_vlm_server_running()
    image_b64 = base64.b64encode(png_bytes).decode("ascii")
    payload = json.dumps(
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _LOCAL_VISION_PROMPT},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                    ],
                }
            ],
            "max_tokens": 200,
            "temperature": 0.0,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{_VLM_SERVER_PORT}/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_VLM_GENERATION_TIMEOUT_SECONDS) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return body["choices"][0]["message"]["content"].strip()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise VisionAnalysisError("로컬 비전 모델 요청에 실패했습니다.") from exc
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        raise VisionAnalysisError("로컬 비전 모델 응답 형식이 올바르지 않습니다.") from exc
