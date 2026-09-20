"use client";

/**
 * [C-06] 면접장의 보조 패널 컨테이너 (unit-20, 04-ux-design.md [C-06]/[C-07]/[C-08]/§6).
 *
 * 코드 에디터([C-07])와 화이트보드([C-08])를 한 자리에 담는다. 레이아웃은 CSS가 정한다:
 * ≥768px는 채팅 옆 분할 뷰, <768px는 전체화면 모달(§6). 이 컴포넌트는 그중 모달일 때만
 * 필요한 dialog 시맨틱과 포커스 이동을 책임진다.
 *
 * 한 번 열린 패널은 닫아도 unmount하지 않고 `hidden`으로만 숨긴다 — 그래야 제출/저장 전의
 * 로컬 편집 내용(에디터 본문, 그리다 만 캔버스)이 탭 전환/모달 닫기로 유실되지 않는다
 * ([C-07] "코드 내용은 로컬에 보존해 유실 방지"). 복원 GET은 각 패널이 첫 마운트 때 스스로 한다.
 */
import { useEffect, useId, useRef, type KeyboardEvent } from "react";
import CodeEditorPanel from "./CodeEditorPanel";
import WhiteboardCanvas from "./WhiteboardCanvas";

export type SidePanelId = "code" | "whiteboard";

export const SIDE_PANEL_LABEL: Record<SidePanelId, string> = {
  code: "코드 에디터",
  whiteboard: "화이트보드",
};

interface InterviewSidePanelProps {
  domId: string;
  interviewId: string;
  accessToken: string | null;
  active: SidePanelId | null;
  mounted: Record<SidePanelId, boolean>;
  modal: boolean;
  onClose: () => void;
}

export default function InterviewSidePanel({
  domId,
  interviewId,
  accessToken,
  active,
  mounted,
  modal,
  onClose,
}: InterviewSidePanelProps) {
  const headingId = useId();
  const headingRef = useRef<HTMLHeadingElement | null>(null);

  useEffect(() => {
    if (modal && active) headingRef.current?.focus();
  }, [modal, active]);

  function handleKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (!modal || event.key !== "Escape") return;
    // Monaco는 Esc를 자체 위젯(자동완성 등) 닫기에 쓴다. 그 경우 패널까지 닫히면 안 된다.
    if ((event.target as HTMLElement).closest(".monaco-editor")) return;
    event.stopPropagation();
    onClose();
  }

  return (
    <aside
      id={domId}
      className="interview-room__subpanel"
      hidden={active === null}
      role={modal ? "dialog" : undefined}
      aria-modal={modal ? true : undefined}
      aria-labelledby={headingId}
      onKeyDown={handleKeyDown}
    >
      <div className="interview-room__subpanel-header">
        <h2 id={headingId} ref={headingRef} tabIndex={-1}>
          {active ? SIDE_PANEL_LABEL[active] : "보조 패널"}
        </h2>
        <button type="button" className="ghost-button" onClick={onClose}>
          채팅으로 돌아가기
        </button>
      </div>

      {mounted.code && (
        <div hidden={active !== "code"}>
          <CodeEditorPanel interviewId={interviewId} accessToken={accessToken} />
        </div>
      )}
      {mounted.whiteboard && (
        <div hidden={active !== "whiteboard"}>
          <WhiteboardCanvas interviewId={interviewId} accessToken={accessToken ?? undefined} />
        </div>
      )}
    </aside>
  );
}
