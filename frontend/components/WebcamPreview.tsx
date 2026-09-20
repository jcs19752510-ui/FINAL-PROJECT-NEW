"use client";

// REQ-015 (04-ux-design.md [C-05]/[C-06], WebcamPreviewTile 컴포넌트 명세 §4):
// 순수 클라이언트 전용 웹캠 "미리보기"다. `getUserMedia`로 받은 스트림은 이 컴포넌트
// 밖으로 절대 나가지 않는다 — fetch/WebSocket 전송, recording, 캡처는 범위 밖이며
// DEC-008(표정/감정 분석 Out-of-Scope)과 직결된 제약이다. 서버 API 호출 없음.

import { useEffect, useRef, useState, type CSSProperties } from "react";

export type WebcamPreviewStatus =
  | "off"
  | "requesting"
  | "active"
  | "permission-denied"
  | "unsupported"
  | "error";

export interface WebcamPreviewProps {
  /** true면 마운트 시 바로 권한 요청을 시작한다. [C-05] 장치 테스트 화면용. 기본값 false([C-06] 소형 타일은 사용자가 켬). */
  autoStart?: boolean;
  /** "panel": [C-05] 큰 미리보기. "tile": [C-06] 채팅 화면의 소형 타일(기본 최소화, 04-ux-design.md §6 모바일 규칙). */
  variant?: "panel" | "tile";
  className?: string;
}

function isGetUserMediaSupported(): boolean {
  return (
    typeof navigator !== "undefined" &&
    typeof navigator.mediaDevices !== "undefined" &&
    typeof navigator.mediaDevices.getUserMedia === "function"
  );
}

export default function WebcamPreview({
  autoStart = false,
  variant = "panel",
  className,
}: WebcamPreviewProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  // 초기 상태는 서버/클라이언트에서 항상 같은 값이어야 한다(DEF-001, unit-16-test.md §6).
  // 예전에는 여기서 isGetUserMediaSupported()를 호출해 SSR은 "unsupported", 브라우저 첫
  // 렌더는 "requesting"이 되어 hydration mismatch 소지가 있었다. 지원 여부는 마운트 후
  // effect에서만 판정한다.
  const [status, setStatus] = useState<WebcamPreviewStatus>(autoStart ? "requesting" : "off");

  function stopStream() {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
  }

  // 동기적으로 setState하는 분기가 없어야 useEffect에서 직접 호출해도 lint 규칙에
  // 걸리지 않는다 — 지원 여부 판단은 이 함수를 호출하기 전에 끝내둔다.
  async function acquireStream(cancelledRef?: { current: boolean }) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: true,
        audio: false,
      });
      if (cancelledRef?.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
      setStatus("active");
    } catch (err) {
      if (cancelledRef?.current) return;
      if (err instanceof DOMException) {
        if (err.name === "NotAllowedError" || err.name === "SecurityError") {
          setStatus("permission-denied");
          return;
        }
        if (err.name === "NotFoundError" || err.name === "OverconstrainedError") {
          setStatus("unsupported");
          return;
        }
      }
      setStatus("error");
    }
  }

  function startPreview() {
    if (!isGetUserMediaSupported()) {
      setStatus("unsupported");
      return;
    }
    setStatus("requesting");
    void acquireStream();
  }

  function turnOff() {
    stopStream();
    setStatus("off");
  }

  useEffect(() => {
    const cancelledRef = { current: false };
    if (autoStart) {
      // 외부 시스템(브라우저 카메라 장치)과의 동기화이지 파생 상태 계산이 아니다.
      // 브라우저 지원 여부는 서버에서 알 수 없어 마운트 후에야 확정할 수 있다.
      if (isGetUserMediaSupported()) {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        void acquireStream(cancelledRef);
      } else {
        setStatus("unsupported");
      }
    }
    return () => {
      cancelledRef.current = true;
      stopStream();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const showVideo = status === "active" || status === "requesting";
  const wrapperSize =
    variant === "tile"
      ? { width: 160, height: 120 }
      : { width: "100%", maxWidth: 480, aspectRatio: "4 / 3" };

  return (
    <div
      className={className}
      style={{
        ...wrapperSize,
        position: "relative",
        borderRadius: variant === "tile" ? 8 : 12,
        overflow: "hidden",
        background: "#1a1d24",
        border: "1px solid rgba(255,255,255,0.12)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      {/* 04-ux-design.md §5-5: 웹캠 프리뷰는 장식적 요소 — 정보 전달 목적이 아니므로 스크린리더에는 숨김 */}
      <video
        ref={videoRef}
        aria-hidden="true"
        autoPlay
        playsInline
        muted
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          display: showVideo ? "block" : "none",
          transform: "scaleX(-1)",
        }}
      />

      {status === "off" && (
        <div style={emptyStateStyle}>
          <span>웹캠이 꺼져 있습니다</span>
          <button type="button" onClick={startPreview} style={buttonStyle}>
            웹캠 미리보기 켜기
          </button>
        </div>
      )}

      {status === "requesting" && (
        <div style={emptyStateStyle} aria-live="polite">
          <span>카메라 권한 요청 중...</span>
        </div>
      )}

      {status === "permission-denied" && (
        <div style={errorStateStyle} role="alert">
          <span>카메라 권한이 거부되었습니다.</span>
          <span style={{ fontSize: 12, opacity: 0.85 }}>
            웹캠 없이 텍스트로 계속 진행할 수 있습니다.
          </span>
          <button type="button" onClick={startPreview} style={buttonStyle}>
            다시 시도
          </button>
        </div>
      )}

      {status === "unsupported" && (
        <div style={errorStateStyle} role="alert">
          <span>이 브라우저 또는 장치에서 웹캠을 사용할 수 없습니다.</span>
          <span style={{ fontSize: 12, opacity: 0.85 }}>
            웹캠 없이 텍스트로 계속 진행할 수 있습니다.
          </span>
        </div>
      )}

      {status === "error" && (
        <div style={errorStateStyle} role="alert">
          <span>웹캠 미리보기를 불러오지 못했습니다.</span>
          <button type="button" onClick={startPreview} style={buttonStyle}>
            다시 시도
          </button>
        </div>
      )}

      {status === "active" && (
        <button
          type="button"
          onClick={turnOff}
          aria-label="웹캠 미리보기 끄기"
          style={{
            ...buttonStyle,
            position: "absolute",
            bottom: 8,
            right: 8,
          }}
        >
          끄기
        </button>
      )}
    </div>
  );
}

const emptyStateStyle: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  gap: 8,
  color: "#e5e7eb",
  fontSize: 13,
  textAlign: "center",
  padding: 12,
};

const errorStateStyle: CSSProperties = {
  ...emptyStateStyle,
  color: "#fca5a5",
};

const buttonStyle: React.CSSProperties = {
  fontSize: 12,
  padding: "6px 10px",
  borderRadius: 6,
  border: "1px solid rgba(255,255,255,0.24)",
  background: "rgba(255,255,255,0.08)",
  color: "inherit",
  cursor: "pointer",
};
