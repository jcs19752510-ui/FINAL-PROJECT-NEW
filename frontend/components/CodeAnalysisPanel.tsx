"use client";

/**
 * 라이브 코딩 AI 분석 결과 패널 (REQ-F-004).
 *
 * 면접 화면(CodeEditorPanel)과 채용담당자 리포트(recruiter/[id])에서 공통으로 쓰도록
 * props 는 `CodeAnalysis` 하나만 받는다. 표시용 문구·계산은 lib/codeAnalysisView.ts 에 있다.
 *
 * 렌더링 보안(REQ-036): `dangerouslySetInnerHTML`을 쓰지 않고 JSX 텍스트 보간만 사용한다 —
 * 지원자 코드가 섞인 입력/출력/린트 메시지가 그대로 오기 때문이다.
 */
import type { CodeAnalysis } from "@/lib/api";
import {
  complexityText,
  formatCommentRatio,
  formatPassCount,
  formatPassRate,
  scoreToGrade,
  topViolations,
} from "@/lib/codeAnalysisView";

const SECTION_STYLE = { marginBottom: 16 } as const;
const HEADING_STYLE = { fontSize: 15, margin: "0 0 6px" } as const;
const MUTED_STYLE = { color: "var(--color-text-secondary)", fontSize: 13 } as const;
const MONO_STYLE = {
  fontFamily: "ui-monospace, monospace",
  fontSize: 12.5,
  whiteSpace: "pre-wrap",
  margin: 0,
} as const;

export default function CodeAnalysisPanel({ analysis }: { analysis: CodeAnalysis }) {
  const { correctness, complexity, style, comments, disclaimer } = analysis;
  const violations = topViolations(style.items, 5);

  return (
    <section aria-label="코드 분석 결과" data-testid="code-analysis-panel">
      <h2 style={{ fontSize: 16, margin: "0 0 12px" }}>코드 분석 결과</h2>

      <div style={SECTION_STYLE}>
        <h3 style={HEADING_STYLE}>정답 여부</h3>
        {correctness === null ? (
          <p style={MUTED_STYLE}>문제를 선택하지 않아 정답 채점은 하지 않았습니다.</p>
        ) : (
          <>
            <p style={{ margin: 0 }}>
              <strong>{formatPassCount(correctness.passed, correctness.total)}</strong>
              {correctness.total > 0 && ` (${formatPassRate(correctness.pass_rate)})`}
            </p>
            {correctness.failures.length > 0 && (
              <ul style={{ margin: "8px 0 0", paddingLeft: 18 }}>
                {correctness.failures.map((f) => (
                  <li key={f.index} style={{ marginBottom: 8 }}>
                    <div style={{ fontSize: 13 }}>
                      케이스 #{f.index + 1}
                      {f.timed_out && " (시간 초과)"}
                    </div>
                    <div style={MUTED_STYLE}>입력</div>
                    <pre style={MONO_STYLE}>{f.input}</pre>
                    <div style={MUTED_STYLE}>기대 출력</div>
                    <pre style={MONO_STYLE}>{f.expected}</pre>
                    <div style={MUTED_STYLE}>실제 출력</div>
                    <pre style={MONO_STYLE}>{f.actual === "" ? "(출력 없음)" : f.actual}</pre>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>

      <div style={SECTION_STYLE}>
        <h3 style={HEADING_STYLE}>
          시간복잡도{" "}
          <span className="status-badge" title="정적 분석으로 추정한 값이라 실제와 다를 수 있습니다.">
            근사치
          </span>
        </h3>
        <p style={{ margin: 0 }}>
          <strong>{complexityText(complexity.estimate, complexity.confidence)}</strong>
        </p>
        {complexity.basis.length > 0 && (
          <ul style={{ margin: "6px 0 0", paddingLeft: 18, fontSize: 13 }}>
            {complexity.basis.map((b, i) => (
              <li key={i}>{b}</li>
            ))}
          </ul>
        )}
      </div>

      <div style={SECTION_STYLE}>
        <h3 style={HEADING_STYLE}>코드 스타일</h3>
        <p style={{ margin: 0 }}>
          <strong>
            {Math.round(style.score)}점 ({scoreToGrade(style.score)})
          </strong>{" "}
          <span style={MUTED_STYLE}>
            {style.tool} · 위반 {style.violations}건
          </span>
        </p>
        {violations.shown.length > 0 && (
          <ul style={{ margin: "6px 0 0", paddingLeft: 18, fontSize: 13 }}>
            {violations.shown.map((v, i) => (
              <li key={`${v.line}-${v.code}-${i}`}>
                {v.line}행 <code>{v.code}</code> {v.message}
              </li>
            ))}
          </ul>
        )}
        {violations.hidden > 0 && <p style={MUTED_STYLE}>그 외 {violations.hidden}건은 표시하지 않았습니다.</p>}
      </div>

      <div style={SECTION_STYLE}>
        <h3 style={HEADING_STYLE}>주석</h3>
        <p style={{ margin: 0 }}>
          주석 비율 <strong>{formatCommentRatio(comments.ratio)}</strong> (주석 {comments.comment_lines}줄 / 코드{" "}
          {comments.code_lines}줄) · docstring {comments.has_docstring ? "있음" : "없음"}
        </p>
        {comments.note && <p style={MUTED_STYLE}>{comments.note}</p>}
      </div>

      <p style={{ ...MUTED_STYLE, borderTop: "1px solid var(--color-border)", paddingTop: 8, margin: 0 }}>
        {disclaimer}
      </p>
    </section>
  );
}
