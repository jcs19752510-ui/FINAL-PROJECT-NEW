"use client";

/**
 * [C-07] 코드 에디터 패널 (라이브 코딩, REQ-008, Feature D, unit-9).
 *
 * 04-ux-design.md [C-07] / 03-system-design.md §4.2("/interviews/{id}/code-submissions"
 * POST+GET) §3.1(CODE_SUBMISSIONS ERD) 명세를 그대로 구현한다. DEC-008에 따라 코드
 * "실행" 기능은 전혀 포함하지 않는다(제출/저장만).
 *
 * **독립 컴포넌트 경계(오케스트레이터 지시)**: 이 파일은 unit-4가 소유한
 * `frontend/app/interviews/[id]/page.tsx`, `frontend/lib/api.ts`를 전혀 import하지
 *않는다 — API 호출(fetch)과 타입을 이 파일 안에 자체적으로 갖춰 독립적으로 완결시켰다.
 * 이 패널을 실제 면접장 화면에 삽입(탭 전환 등)하는 배선(wiring) 작업은 이번 유닛의
 * 책임이 아니며, 추후 통합 작업에서 `page.tsx`가 이 컴포넌트를 import해 사용하면 된다.
 * 스타일도 `globals.css`를 건드리지 않기 위해 이미 존재가 확인된 공통 클래스
 * (`banner-error`, `submit-button`)만 재사용하고, 레이아웃은 인라인 스타일로 완결했다.
 */
import { useEffect, useRef, useState } from "react";
import Editor from "@monaco-editor/react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

// 03-system-design.md §3.1 CODE_SUBMISSIONS.language / backend `app/schemas/code_submission.py`의
// `ALLOWED_LANGUAGES` 화이트리스트와 반드시 동일하게 유지해야 한다(값이 어긋나면 드롭다운에서
// 고른 언어가 서버에서 422로 거부된다). 두 목록 모두 Monaco 내장 언어 id를 그대로 값으로 쓴다.
const LANGUAGE_OPTIONS = [
  { value: "python", label: "Python" },
  { value: "javascript", label: "JavaScript" },
  { value: "typescript", label: "TypeScript" },
  { value: "java", label: "Java" },
  { value: "c", label: "C" },
  { value: "cpp", label: "C++" },
  { value: "csharp", label: "C#" },
  { value: "go", label: "Go" },
  { value: "rust", label: "Rust" },
  { value: "sql", label: "SQL" },
  { value: "plaintext", label: "Plain Text" },
] as const;

type LanguageValue = (typeof LANGUAGE_OPTIONS)[number]["value"];

const DEFAULT_TEMPLATES: Record<LanguageValue, string> = {
  python: "# 여기에 코드를 작성하세요\n",
  javascript: "// 여기에 코드를 작성하세요\n",
  typescript: "// 여기에 코드를 작성하세요\n",
  java: "// 여기에 코드를 작성하세요\n",
  c: "// 여기에 코드를 작성하세요\n",
  cpp: "// 여기에 코드를 작성하세요\n",
  csharp: "// 여기에 코드를 작성하세요\n",
  go: "// 여기에 코드를 작성하세요\n",
  rust: "// 여기에 코드를 작성하세요\n",
  sql: "-- 여기에 코드를 작성하세요\n",
  plaintext: "여기에 내용을 작성하세요\n",
};

interface CodeSubmissionOut {
  id: string;
  interview_id: string;
  language: string;
  content: string;
  submitted_at: string;
}

type SaveStatus = "saved" | "saving" | "unsaved" | "error";

const SAVE_STATUS_LABEL: Record<SaveStatus, string> = {
  saved: "저장됨",
  saving: "저장 중...",
  unsaved: "미저장",
  error: "저장 실패",
};

const SAVE_STATUS_COLOR: Record<SaveStatus, string> = {
  saved: "#2f9e44",
  saving: "#868e96",
  unsaved: "#e8590c",
  error: "#e03131",
};

export interface CodeEditorPanelProps {
  interviewId: string;
  accessToken: string | null;
  /** 제공되면 "채팅으로 돌아가기" 버튼을 노출한다(탭 전환 배선은 호출부 책임). */
  onBackToChat?: () => void;
}

export default function CodeEditorPanel({ interviewId, accessToken, onBackToChat }: CodeEditorPanelProps) {
  const [language, setLanguage] = useState<LanguageValue>("python");
  const [content, setContent] = useState<string>(DEFAULT_TEMPLATES.python);
  const [editorMounting, setEditorMounting] = useState(true);
  const [restoreLoading, setRestoreLoading] = useState(true);
  const [restoreError, setRestoreError] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("saved");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const lastSavedContentRef = useRef<string>("");

  // [C-07]: 언어를 바꿀 때마다 해당 언어의 최신 제출본을 불러와 에디터를 복원한다
  // (04-ux-design.md [C-07] GET 신규 용도). `cancelled` 플래그로 언어를 빠르게 여러 번
  // 바꿨을 때 늦게 도착한 이전 요청이 최신 상태를 덮어쓰지 않게 한다(unit-4
  // `page.tsx`의 로딩 이펙트와 동일한 패턴).
  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;

    async function load() {
      setRestoreLoading(true);
      setRestoreError(null);
      try {
        const res = await fetch(
          `${API_BASE_URL}/interviews/${interviewId}/code-submissions?language=${encodeURIComponent(language)}`,
          { headers: { Authorization: `Bearer ${accessToken}` } },
        );
        if (!res.ok) {
          throw new Error(`GET code-submissions failed: ${res.status}`);
        }
        const list: CodeSubmissionOut[] = await res.json();
        if (cancelled) return;
        const latest = list[0];
        const restored = latest ? latest.content : DEFAULT_TEMPLATES[language];
        setContent(restored);
        lastSavedContentRef.current = latest ? latest.content : "";
        setSaveStatus("saved");
      } catch {
        if (cancelled) return;
        // 04-ux-design.md [C-07]: GET 실패 시에만 "이전 세션의 코드를 불러오지
        // 못했습니다" 안내로 대체하고, 빈 템플릿으로 편집을 계속할 수 있게 한다.
        setRestoreError("이전 세션의 코드를 불러오지 못했습니다.");
        setContent(DEFAULT_TEMPLATES[language]);
        lastSavedContentRef.current = "";
        setSaveStatus("unsaved");
      } finally {
        if (!cancelled) setRestoreLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [accessToken, interviewId, language]);

  function handleEditorChange(value: string | undefined) {
    const next = value ?? "";
    setContent(next);
    setSaveStatus(next === lastSavedContentRef.current ? "saved" : "unsaved");
  }

  async function handleSubmit() {
    if (!accessToken) return;
    setSaveStatus("saving");
    setSubmitError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/interviews/${interviewId}/code-submissions`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ language, content }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail ?? `제출 실패 (status ${res.status})`);
      }
      // 에러(제출 실패) 상태여도 코드 내용은 로컬 state에 계속 보존되어 유실되지
      // 않는다([C-07] 에러 상태 명세) — 재시도는 이 버튼을 다시 누르는 것으로 충분하다.
      lastSavedContentRef.current = content;
      setSaveStatus("saved");
    } catch (err) {
      setSaveStatus("error");
      setSubmitError(err instanceof Error ? err.message : "코드 제출 중 오류가 발생했습니다.");
    }
  }

  const showSkeleton = editorMounting || restoreLoading;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <header style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
        <select
          value={language}
          onChange={(e) => setLanguage(e.target.value as LanguageValue)}
          disabled={restoreLoading}
          aria-label="프로그래밍 언어 선택"
        >
          {LANGUAGE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <span style={{ color: SAVE_STATUS_COLOR[saveStatus], fontSize: "0.875rem" }}>
          {SAVE_STATUS_LABEL[saveStatus]}
        </span>
        {onBackToChat && (
          <button type="button" onClick={onBackToChat} style={{ marginLeft: "auto" }}>
            채팅으로 돌아가기
          </button>
        )}
      </header>

      {restoreError && <div className="banner-error">{restoreError}</div>}
      {submitError && <div className="banner-error">{submitError}</div>}

      <div style={{ position: "relative", minHeight: "420px" }}>
        {showSkeleton && (
          <div
            style={{
              position: "absolute",
              inset: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: "rgba(0,0,0,0.03)",
              zIndex: 1,
            }}
          >
            에디터를 불러오는 중입니다...
          </div>
        )}
        <Editor
          height="420px"
          language={language}
          value={content}
          theme="vs-dark"
          onMount={() => setEditorMounting(false)}
          onChange={handleEditorChange}
          options={{ minimap: { enabled: false }, fontSize: 14 }}
        />
      </div>

      <footer>
        <button
          type="button"
          className="submit-button"
          onClick={handleSubmit}
          disabled={saveStatus === "saving" || restoreLoading}
        >
          제출
        </button>
      </footer>
    </div>
  );
}
