"use client";

// REQ-017 (Feature H, unit-17, 04-ux-design.md [C-08] 화이트보드 캔버스 패널).
// DEC-008: AI가 화이트보드를 시각적으로 분석하는 기능은 Out-of-Scope(REQ-021)다.
// 이 컴포넌트는 순수 드로잉 캔버스 + 스트로크 좌표 데이터의 저장/조회만 다루고,
// 이미지 인식/비전 분석 코드는 포함하지 않는다.
//
// 오케스트레이터 지시 범위: "마우스/터치로 그리기, 지우기, 저장 버튼"만 구현한다.
// 04-ux-design.md [C-08]의 도구바 전체 항목(펜/도형/텍스트/지우기/색상) 중
// 도형/텍스트 도구는 이번 유닛 범위에서 제외했다 — pen(자유선) + 색상 선택 +
// 지우기 + 저장만으로 REQ-017 "시스템 설계를 그림으로 표현"이라는 목적을 충족하며,
// 도형/텍스트 도구 추가는 별도 두 갈래 해석 없이 순수 확장(additive)이라 후속
// 유닛/이터레이션에서 얼마든지 더할 수 있다(unit-17-note.md §2 참고).
//
// 이 파일은 면접장 메인 레이아웃(app/interviews/[id]/page.tsx, 다른 유닛 소유)에
// 아직 삽입(wiring)되지 않은 독립 컴포넌트다 — 오케스트레이터 지시대로 wiring은
// 이번 유닛 범위 밖이다.

import { useEffect, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent } from "react";
import { getWhiteboard, saveWhiteboard, type WhiteboardStroke } from "@/lib/api";

export type WhiteboardCanvasStatus = "loading" | "ready" | "saving" | "saved" | "error";

export interface WhiteboardCanvasProps {
  /** 저장/조회 API 호출에 필요한 면접 세션 id. 없으면 로컬 드로잉만 가능(저장 비활성). */
  interviewId?: string;
  /** 저장/조회 API 호출에 필요한 액세스 토큰. */
  accessToken?: string;
  width?: number;
  height?: number;
  className?: string;
}

const COLOR_PRESETS = ["#1f2937", "#ef4444", "#3b82f6", "#22c55e", "#f59e0b"];
const DEFAULT_WIDTH = 3;

export default function WhiteboardCanvas({
  interviewId,
  accessToken,
  width = 640,
  height = 400,
  className,
}: WhiteboardCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const strokesRef = useRef<WhiteboardStroke[]>([]);
  const drawingRef = useRef<WhiteboardStroke | null>(null);

  const [color, setColor] = useState(COLOR_PRESETS[0]);
  const [lineWidth, setLineWidth] = useState(DEFAULT_WIDTH);
  // interviewId+accessToken이 모두 있으면 서버의 최신 스냅샷을 불러오는 것으로
  // 시작한다([C-08] "로딩" 상태). 둘 중 하나라도 없으면 저장 대상이 없는 로컬
  // 전용 모드이므로 바로 "ready"(빈 캔버스)에서 시작한다.
  const [status, setStatus] = useState<WhiteboardCanvasStatus>(
    interviewId && accessToken ? "loading" : "ready",
  );
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  function redraw() {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    for (const stroke of strokesRef.current) {
      if (stroke.points.length === 0) continue;
      ctx.strokeStyle = stroke.color;
      ctx.lineWidth = stroke.width;
      ctx.beginPath();
      ctx.moveTo(stroke.points[0].x, stroke.points[0].y);
      for (const point of stroke.points.slice(1)) {
        ctx.lineTo(point.x, point.y);
      }
      ctx.stroke();
    }
  }

  useEffect(() => {
    // 초기 status는 이미 lazy-init(useState 초기값)에서 interviewId/accessToken
    // 유무에 따라 "loading" 또는 "ready"로 결정되어 있으므로, 이 effect 본문에서는
    // setState를 동기 호출하지 않고 비동기 fetch 완료 후 콜백에서만 호출한다
    // (react-hooks/set-state-in-effect 대응, WebcamPreview.tsx의 동일 패턴 참고).
    if (!interviewId || !accessToken) return;
    const cancelledRef = { current: false };
    getWhiteboard(accessToken, interviewId)
      .then((snapshot) => {
        if (cancelledRef.current) return;
        strokesRef.current = snapshot?.strokes ?? [];
        redraw();
        setStatus("ready");
      })
      .catch(() => {
        if (cancelledRef.current) return;
        // [C-08] 에러 상태: GET 실패 시 "이전 캔버스를 불러오지 못했습니다" 안내로
        // 대체하고, 빈 캔버스로 계속 그릴 수 있게 한다(그레이스풀 디그레이드).
        setErrorMessage("이전 캔버스를 불러오지 못했습니다.");
        setStatus("ready");
      });
    return () => {
      cancelledRef.current = true;
    };
  }, [interviewId, accessToken]);

  function getCanvasPoint(event: ReactPointerEvent<HTMLCanvasElement>): { x: number; y: number } {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    return {
      x: ((event.clientX - rect.left) / rect.width) * canvas.width,
      y: ((event.clientY - rect.top) / rect.height) * canvas.height,
    };
  }

  function handlePointerDown(event: ReactPointerEvent<HTMLCanvasElement>) {
    if (status === "loading") return;
    event.currentTarget.setPointerCapture(event.pointerId);
    const point = getCanvasPoint(event);
    drawingRef.current = { points: [point], color, width: lineWidth };
  }

  function handlePointerMove(event: ReactPointerEvent<HTMLCanvasElement>) {
    const current = drawingRef.current;
    if (!current) return;
    const point = getCanvasPoint(event);
    current.points.push(point);
    redraw();
    // 진행 중인 stroke도 즉시 화면에 반영되도록 임시로 이어 그린다.
    const ctx = canvasRef.current?.getContext("2d");
    if (ctx && current.points.length > 1) {
      ctx.strokeStyle = current.color;
      ctx.lineWidth = current.width;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.beginPath();
      const prev = current.points[current.points.length - 2];
      ctx.moveTo(prev.x, prev.y);
      ctx.lineTo(point.x, point.y);
      ctx.stroke();
    }
  }

  function handlePointerUp() {
    const current = drawingRef.current;
    drawingRef.current = null;
    if (!current || current.points.length < 2) return;
    strokesRef.current = [...strokesRef.current, current];
    if (status === "saved" || status === "error") {
      setStatus("ready");
      setErrorMessage(null);
    }
  }

  function handleClear() {
    strokesRef.current = [];
    redraw();
    if (status === "saved" || status === "error") {
      setStatus("ready");
      setErrorMessage(null);
    }
  }

  async function handleSave() {
    if (!interviewId || !accessToken) return;
    setStatus("saving");
    setErrorMessage(null);
    try {
      await saveWhiteboard(accessToken, interviewId, strokesRef.current);
      setStatus("saved");
    } catch {
      setErrorMessage("저장되지 않았습니다.");
      setStatus("error");
    }
  }

  const canSave = Boolean(interviewId && accessToken);

  return (
    <div className={className} style={wrapperStyle}>
      <div style={toolbarStyle}>
        {COLOR_PRESETS.map((preset) => (
          <button
            key={preset}
            type="button"
            aria-label={`색상 ${preset}`}
            aria-pressed={color === preset}
            onClick={() => setColor(preset)}
            style={{
              ...colorSwatchStyle,
              background: preset,
              outline: color === preset ? "2px solid #ffffff" : "1px solid rgba(255,255,255,0.3)",
            }}
          />
        ))}
        <label style={widthLabelStyle}>
          굵기
          <input
            type="range"
            min={1}
            max={12}
            value={lineWidth}
            onChange={(event) => setLineWidth(Number(event.target.value))}
          />
        </label>
        <button type="button" onClick={handleClear} style={buttonStyle}>
          지우기
        </button>
        <button
          type="button"
          onClick={() => void handleSave()}
          disabled={!canSave || status === "saving" || status === "loading"}
          style={buttonStyle}
        >
          {status === "saving" ? "저장 중..." : "저장"}
        </button>
        <span aria-live="polite" style={statusTextStyle}>
          {status === "saved" && "저장됨"}
          {status === "error" && (errorMessage ?? "오류가 발생했습니다.")}
          {status === "loading" && "불러오는 중..."}
        </span>
      </div>

      <div style={{ position: "relative", width, height }}>
        <canvas
          ref={canvasRef}
          width={width}
          height={height}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerLeave={handlePointerUp}
          style={{
            ...canvasStyle,
            touchAction: "none",
            cursor: status === "loading" ? "wait" : "crosshair",
          }}
        />
        {status === "loading" && (
          <div style={overlayStyle} aria-live="polite">
            캔버스를 불러오는 중...
          </div>
        )}
      </div>
    </div>
  );
}

const wrapperStyle: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 8,
};

const toolbarStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 8,
  flexWrap: "wrap",
};

const colorSwatchStyle: CSSProperties = {
  width: 24,
  height: 24,
  borderRadius: "50%",
  border: "none",
  cursor: "pointer",
  padding: 0,
};

const widthLabelStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 6,
  fontSize: 12,
  color: "inherit",
};

const buttonStyle: CSSProperties = {
  fontSize: 12,
  padding: "6px 12px",
  borderRadius: 6,
  border: "1px solid rgba(255,255,255,0.24)",
  background: "rgba(255,255,255,0.08)",
  color: "inherit",
  cursor: "pointer",
};

const statusTextStyle: CSSProperties = {
  fontSize: 12,
  opacity: 0.85,
};

const canvasStyle: CSSProperties = {
  width: "100%",
  height: "100%",
  borderRadius: 8,
  border: "1px solid rgba(255,255,255,0.16)",
  background: "#ffffff",
  display: "block",
};

const overlayStyle: CSSProperties = {
  position: "absolute",
  inset: 0,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  fontSize: 13,
  color: "#1f2937",
  background: "rgba(255,255,255,0.6)",
  borderRadius: 8,
};
