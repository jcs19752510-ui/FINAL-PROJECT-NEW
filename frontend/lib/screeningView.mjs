// AI 이력서 판정 화면용 순수 함수 (React 비의존). 채용담당자 전용 화면에서 사용.
export const CRITERIA_MAX_LENGTH = 4000;
export const THRESHOLD_MIN = 1;
export const THRESHOLD_MAX = 100;
export const THRESHOLD_DEFAULT = 70;
export const AI_ADVISORY_NOTICE = "AI 판정은 참고용이며 최종 합격 여부는 면접담당자가 결정합니다.";

/**
 * 목록/상세 배지 정보. tone: pass | fail | pending | failed | none
 * @param {string | null | undefined} state ai_state
 * @param {string | null | undefined} verdict ai_verdict
 * @param {boolean} [stale] 이전 결과가 있으나 기준이 바뀐 경우
 * @returns {{label: string, tone: 'pass'|'fail'|'pending'|'failed'|'none'}}
 */
export function aiBadge(state, verdict, stale = false) {
  if (state === "done") {
    if (verdict === "pass") return stale ? { label: "AI 합격 (이전)", tone: "pending" } : { label: "AI 합격", tone: "pass" };
    if (verdict === "fail") return stale ? { label: "AI 불합격 (이전)", tone: "pending" } : { label: "AI 불합격", tone: "fail" };
    return { label: "분석 대기", tone: "pending" };
  }
  if (state === "pending") {
    if (verdict === "pass") return { label: "분석 대기 · AI 합격 (이전)", tone: "pending" };
    if (verdict === "fail") return { label: "분석 대기 · AI 불합격 (이전)", tone: "pending" };
    return { label: "분석 대기", tone: "pending" };
  }
  if (state === "failed") return { label: "분석 실패", tone: "failed" };
  return { label: "기준 미등록", tone: "none" };
}

/** @param {number | null | undefined} score */
export function formatScore(score) {
  if (typeof score !== "number" || !Number.isFinite(score)) return "-";
  return `${Math.round(score)}점`;
}

/**
 * @param {{text: string, threshold: number | string}} input
 * @returns {{ok: boolean, error?: string}}
 */
export function validateCriteriaInput({ text, threshold }) {
  const trimmed = (text ?? "").trim();
  if (!trimmed) return { ok: false, error: "면접기준을 입력해 주세요." };
  if (trimmed.length > CRITERIA_MAX_LENGTH) {
    return { ok: false, error: `면접기준은 ${CRITERIA_MAX_LENGTH}자 이하로 입력해 주세요.` };
  }
  const n = typeof threshold === "string" ? (threshold.trim() === "" ? NaN : Number(threshold)) : threshold;
  if (!Number.isInteger(n) || n < THRESHOLD_MIN || n > THRESHOLD_MAX) {
    return { ok: false, error: `AI 합격선은 ${THRESHOLD_MIN}~${THRESHOLD_MAX} 사이의 정수로 입력해 주세요.` };
  }
  return { ok: true };
}

/**
 * 저장본과 비교해 변경됐는지 (텍스트는 trim 기준).
 * @param {{text: string, threshold: number}} saved
 * @param {{text: string, threshold: number | string}} current
 */
export function isDirty(saved, current) {
  return (saved.text ?? "").trim() !== (current.text ?? "").trim() || Number(saved.threshold) !== Number(current.threshold);
}
