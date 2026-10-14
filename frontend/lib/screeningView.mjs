// AI 이력서 판정 화면용 순수 함수 (React 비의존). 채용담당자 전용 화면에서 사용.
export const CRITERIA_MAX_LENGTH = 4000;
export const THRESHOLD_MIN = 1;
export const THRESHOLD_MAX = 100;
export const THRESHOLD_DEFAULT = 70;
export const AI_ADVISORY_NOTICE = "AI 판정은 참고용이며 최종 합격 여부는 면접담당자가 결정합니다.";

/**
 * 기준이 한 번도 등록되지 않았을 때 입력창에 채워 주는 기본 예시(저장 전 초안 — 담당자가 확인·수정 후 "등록").
 * 2026-10 기준 AI·IT 개발자(경력 5년 이상, 바이브코딩 가능자 포함) 서류 선별용.
 * AI는 이력서에 적힌 내용만 근거로 항목별 점수를 매기므로, 항목·배점·감점 조건을 구체적으로 적었다.
 */
export const DEFAULT_CRITERIA_TEMPLATE = `[채용 포지션] AI·IT 개발자 (실무 경력 5년 이상) - 2026년 10월 기준
[평가 방식] 아래 항목별로 이력서에 적힌 내용만 근거로 점수를 매기고(총 100점), 이력서에 없는 내용은 추정하거나 지어내지 않는다.

1. 개발 경력 (20점)
- IT 개발 실무 경력 합계가 5년 이상이면 만점, 3~5년은 절반, 3년 미만은 낮게 평가
- 경력 기간이 명시되지 않았거나 기간이 모호하면 낮게 평가

2. 핵심 개발 역량 (25점)
- 서버/백엔드 개발 언어와 프레임워크 실무 경험 (Python·FastAPI·Django, Java·Spring, Node.js, Go 등)
- 데이터베이스(PostgreSQL, MySQL 등) 설계·튜닝, REST API 설계, 테스트 코드 작성 경험
- 프로젝트에서 맡은 역할과 구체적인 성과(수치·결과)가 적혀 있는지

3. AI 활용·개발 역량 (25점)
- 생성형 AI(LLM) 기반 서비스 개발 경험: 프롬프트 설계, RAG(검색 증강 생성), 벡터DB, LangChain/LangGraph, 에이전트, 모델 서빙
- 머신러닝·딥러닝 프로젝트 또는 MLOps(배포·모니터링) 경험
- AI 서비스의 정확도·비용·보안(개인정보 보호, 프롬프트 인젝션 대응)을 고려한 경험은 가점

4. 바이브코딩(AI 코딩 도구 활용) 역량 (15점)
- Claude Code, Cursor, GitHub Copilot, ChatGPT 등 AI 코딩 도구로 개발 생산성을 높인 구체적 경험
- AI가 만든 코드를 직접 검토·테스트·보완한 경험 (검증 없이 AI에만 의존한 경우는 감점)
- 요구사항 정리, 설계, 작업 분할, 프롬프트 지시, 결과 검증의 흐름으로 개발한 사례는 가점

5. 인프라·운영 및 협업 (10점)
- Docker, Kubernetes, AWS/GCP/Azure, CI/CD, 모니터링·장애 대응 경험
- Git 협업, 코드 리뷰, 기술 문서화, 기획·디자인 등 타 직군과의 협업 경험

6. 성장성·태도 (5점)
- 신기술 학습 사례, 오픈소스 기여, 기술 블로그, 사이드 프로젝트, 관련 자격증

[필수 조건] 아래를 충족하지 못하면 총점을 50점 이하로 평가한다.
- 실무 개발 경력 5년 이상
- 서버/백엔드 개발 프로젝트 경험 1건 이상

[감점 요인]
- 기술 이름만 나열하고 구체적인 프로젝트·역할·성과가 없는 경우
- 재직 기간이 겹치거나 직무가 불분명한 경우
- AI 관련 기술을 '관심', '학습 중' 수준으로만 적은 경우 AI 역량 점수를 낮게 평가

[참고] 서류 단계는 면접 대상자를 가려내는 과정이다. 실제 역량은 면접에서 다시 확인하므로, 근거가 부족하면 단정하지 말고 우려 사항으로 적는다.`;

/**
 * 면접기준 불러오기 실패 시 담당자에게 보여줄 안내문.
 * @param {number | undefined} status HTTP 상태(없으면 네트워크 오류)
 * @param {string | undefined} message 서버가 준 메시지
 */
export function describeCriteriaLoadError(status, message) {
  if (status === 404) {
    return "서버가 면접기준 기능이 없는 이전 버전으로 실행 중이에요. 백엔드를 재시작(start-local.ps1)한 뒤 '다시 불러오기'를 눌러 주세요.";
  }
  if (status === 403) return "면접기준은 채용담당자 계정으로만 볼 수 있어요.";
  if (status === undefined) return "서버에 연결하지 못했어요. 백엔드(8001)가 켜져 있는지 확인한 뒤 '다시 불러오기'를 눌러 주세요.";
  return message || "면접기준을 불러오지 못했어요.";
}

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
