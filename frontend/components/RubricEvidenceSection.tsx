"use client";

/**
 * [C-11]/[R-02] 공통 "루브릭 항목별 평가" 섹션 (v15, 03-system-design v4 §4.6 (5),
 * 04-ux-design.md [C-11]/[R-02] 공통 추가 명세, unit-37, REQ-010/012).
 *
 * 렌더링 보안(REQ-036): 이 컴포넌트는 `dangerouslySetInnerHTML`을 쓰지 않고 JSX
 * 텍스트 보간만 사용한다 — report/page.tsx 상단 주석과 동일한 원칙.
 */
import { useState } from "react";
import type { RubricReportOut } from "@/lib/api";

function AnswerChip({ no, excerpt }: { no: number; excerpt: string | undefined }) {
  const [open, setOpen] = useState(false);
  if (!excerpt) {
    return (
      <span className="status-badge" style={{ opacity: 0.6 }} title="원문이 삭제됨">
        답변 #{no} (삭제됨)
      </span>
    );
  }
  return (
    <div style={{ display: "inline-block" }}>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="status-badge"
        style={{ cursor: "pointer", border: "none" }}
      >
        답변 #{no}
      </button>
      {open && (
        <div
          style={{
            marginTop: 4,
            padding: "8px 10px",
            background: "var(--color-surface-secondary, #f5f5f5)",
            borderRadius: 6,
            fontSize: 13,
            maxWidth: 480,
          }}
        >
          {excerpt}
        </div>
      )}
    </div>
  );
}

export default function RubricEvidenceSection({ rubric }: { rubric: RubricReportOut | null }) {
  if (!rubric || rubric.criteria.length === 0) {
    return (
      <section style={{ marginBottom: 20 }}>
        <h2 style={{ fontSize: 16 }}>루브릭 항목별 평가</h2>
        <p style={{ color: "var(--color-text-secondary)", fontSize: 13 }}>
          세부 근거 없음 — 이 리포트는 항목별 평가 없이 생성되었습니다.
        </p>
      </section>
    );
  }

  const excerptByNo = new Map(rubric.answers.map((a) => [a.no, a.excerpt]));

  return (
    <section style={{ marginBottom: 20 }}>
      <h2 style={{ fontSize: 16, marginBottom: 2 }}>루브릭 항목별 평가</h2>
      <p style={{ fontSize: 12, color: "var(--color-text-secondary)", marginTop: 0, marginBottom: 12 }}>
        {rubric.name}
      </p>
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        {rubric.criteria.map((c) => (
          <div
            key={c.name}
            style={{ borderBottom: "1px solid var(--color-border, #e5e5e5)", paddingBottom: 12 }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8 }}>
              <strong>
                {c.name} <span style={{ fontWeight: 400, fontSize: 12 }}>(가중치 {c.weight}%)</span>
              </strong>
              <span>{c.score !== null ? `${c.score} / 5` : "-"}</span>
            </div>
            {c.description && (
              <p style={{ fontSize: 12, color: "var(--color-text-secondary)", margin: "2px 0" }}>
                {c.description}
              </p>
            )}
            <p style={{ fontSize: 13, margin: "4px 0" }}>{c.evidence}</p>
            {c.answer_refs.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 4 }}>
                {c.answer_refs.map((no) => (
                  <AnswerChip key={no} no={no} excerpt={excerptByNo.get(no)} />
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
