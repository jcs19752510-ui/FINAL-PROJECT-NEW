"""화이트보드 AI 비전 분석 (원안 REQ-021, 2026-09-23 사용자 승인, unit-35).

**2단계로 나눠서 구현했고, 검증 상태가 서로 다르다**:

1. **렌더링(좌표 → PNG 이미지)** — `render_strokes_to_png()`. 외부 API가 전혀
   필요 없어 **실제로 구현·테스트했다**(unit-35-test.md 참고). `whiteboard.py`
   가 저장하는 것은 원시 좌표(`WhiteboardStroke` — points/color/width)이지
   이미지가 아니므로, 비전 모델에 넣기 전에 이 렌더링이 반드시 선행돼야 한다.
2. **비전 모델 호출**(GPT-4V) — `analyze_diagram_with_vision()`. 다른 벤더
   어댑터(unit-32)와 동일한 이유로 **API 키가 없어 미검증**이다.

DEC-008(03-system-design.md)이 "AI가 화이트보드를 시각적으로 분석하는 기능은
Out-of-Scope(REQ-021)"라고 명시한 결정을 이 유닛이 뒤집는다 — 사용자가 이를
인지한 상태에서 승인해 진행한다.
"""
import base64
import io
import json
import logging
import urllib.error
import urllib.request

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
