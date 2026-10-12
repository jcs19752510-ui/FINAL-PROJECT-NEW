// 라이브 코딩 AI 분석(REQ-F-004) 결과 패널의 순수 표시 로직 — 화면과 분리해 테스트한다. (2026-10-12)

/** 통과율(0~1)을 "66.7%" 형태로. 범위를 벗어나거나 NaN 이면 0~100 으로 보정한다. */
export function formatPassRate(rate: number): string {
  if (!Number.isFinite(rate)) return "0%";
  const pct = Math.min(1, Math.max(0, rate)) * 100;
  // 정수면 소수점 없이("100%"), 아니면 한 자리까지("66.7%").
  return Number.isInteger(pct) ? `${pct}%` : `${pct.toFixed(1)}%`;
}

/** "통과 2/3" 문구. 전체 0건이면 실행한 케이스가 없다고 안내한다. */
export function formatPassCount(passed: number, total: number): string {
  if (total <= 0) return "실행된 테스트 없음";
  return `통과 ${passed}/${total}`;
}

/** 스타일 점수(0~100) → 등급. 범위 밖은 보정하고 숫자가 아니면 "-". */
export function scoreToGrade(score: number): string {
  if (!Number.isFinite(score)) return "-";
  const s = Math.min(100, Math.max(0, score));
  if (s >= 90) return "A";
  if (s >= 80) return "B";
  if (s >= 70) return "C";
  if (s >= 60) return "D";
  return "F";
}

const CONFIDENCE_LABEL: Record<string, string> = { low: "낮음", medium: "보통" };

/** 복잡도 신뢰도 한글 라벨. 알 수 없는 값은 원문 그대로 보여 준다. */
export function confidenceLabel(confidence: string): string {
  return CONFIDENCE_LABEL[confidence] ?? confidence;
}

/** 시간복잡도 표시 문구: "추정 O(n) · 신뢰도 낮음". 추정값이 비면 "판단 불가". */
export function complexityText(estimate: string, confidence: string): string {
  const est = estimate.trim();
  if (!est) return `판단 불가 · 신뢰도 ${confidenceLabel(confidence)}`;
  return `추정 ${est} · 신뢰도 ${confidenceLabel(confidence)}`;
}

/** 주석 비율(0~1) → "12.5%". */
export function formatCommentRatio(ratio: number): string {
  return formatPassRate(ratio);
}

/** 스타일 위반을 줄 번호 순으로 정렬해 상위 limit 건과 나머지 건수를 돌려준다(원본 불변). */
export function topViolations<T extends { line: number }>(items: T[], limit = 5): { shown: T[]; hidden: number } {
  const sorted = [...items].sort((a, b) => a.line - b.line);
  const n = Math.max(0, limit);
  return { shown: sorted.slice(0, n), hidden: Math.max(0, sorted.length - n) };
}
