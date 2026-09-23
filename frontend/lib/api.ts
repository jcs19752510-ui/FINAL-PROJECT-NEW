const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    credentials: "include", // refresh_token httpOnly 쿠키 송수신 (03-system-design.md §6.1)
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  if (!res.ok) {
    // RFC 7807 Problem Details (03-system-design.md §4.1)
    const body = await res.json().catch(() => null);
    throw new ApiError(
      res.status,
      body?.code ?? "UNKNOWN_ERROR",
      body?.detail ?? "요청 처리 중 오류가 발생했습니다.",
    );
  }

  return res.json() as Promise<T>;
}

export type UserRole = "candidate" | "recruiter";

export interface UserOut {
  id: string;
  email: string;
  name: string;
  role: string;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
  user: UserOut;
}

export function registerUser(input: {
  email: string;
  password: string;
  name: string;
  role: UserRole;
}): Promise<UserOut> {
  return request<UserOut>("/auth/register", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function loginUser(input: { email: string; password: string }): Promise<TokenResponse> {
  return request<TokenResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function getMe(accessToken: string): Promise<UserOut> {
  return request<UserOut>("/auth/me", {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

export interface InterviewOut {
  id: string;
  candidate_id: string;
  recruiter_id: string | null;
  rubric_template_id: string | null;
  status: "scheduled" | "live" | "paused" | "completed" | "expired";
  report_status: "none" | "queued" | "ready" | "failed";
  started_at: string | null;
  ended_at: string | null;
  overall_score: string | null;
  created_at: string;
}

export interface InterviewDetailOut extends InterviewOut {
  resumable: boolean;
}

export interface TranscriptOut {
  id: string;
  interview_id: string;
  question_id: string | null;
  turn_index: number;
  speaker: "ai" | "user";
  input_mode: "text" | "voice";
  content_text: string;
  audio_ref: string | null;
  created_at: string;
}

// 03-system-design.md §4.2: POST /interviews/{id}/turns -> 202 {job_id}
export interface TurnAcceptedResponse {
  job_id: string;
}

export function getInterview(accessToken: string, interviewId: string): Promise<InterviewDetailOut> {
  return request<InterviewDetailOut>(`/interviews/${interviewId}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

export function listTranscripts(accessToken: string, interviewId: string): Promise<TranscriptOut[]> {
  return request<TranscriptOut[]>(`/interviews/${interviewId}/transcripts`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

// REQ-003(unit-4): 텍스트 턴만 지원. 음성(multipart) 제출은 unit-5 범위.
export function submitTextTurn(
  accessToken: string,
  interviewId: string,
  text: string,
): Promise<TurnAcceptedResponse> {
  return request<TurnAcceptedResponse>(`/interviews/${interviewId}/turns`, {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
    body: JSON.stringify({ text }),
  });
}

// REQ-004/REQ-005(unit-5): 음성(multipart) 턴 제출. 03-system-design.md §4.2/§4.3 —
// 텍스트와 동일한 `/turns` 경로를 `Content-Type: multipart/form-data`로 호출한다.
// `request()` 공통 헬퍼는 항상 `Content-Type: application/json`을 강제 부착하므로
// (line 19) 이 함수는 그 헬퍼를 쓰지 않고 fetch를 직접 호출해 브라우저가 FormData의
// boundary를 포함한 Content-Type을 스스로 설정하게 한다. DEC-023: `biometric_voice`
// 동의가 없거나 철회된 상태면 서버가 `403 CONSENT_REQUIRED_VOICE`를 반환한다.
export async function submitVoiceTurn(
  accessToken: string,
  interviewId: string,
  audioBlob: Blob,
): Promise<TurnAcceptedResponse> {
  const formData = new FormData();
  formData.append("audio", audioBlob, "answer.webm");

  const res = await fetch(`${API_BASE_URL}/interviews/${interviewId}/turns`, {
    method: "POST",
    credentials: "include",
    headers: { Authorization: `Bearer ${accessToken}` },
    body: formData,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(
      res.status,
      body?.code ?? "UNKNOWN_ERROR",
      body?.detail ?? "요청 처리 중 오류가 발생했습니다.",
    );
  }
  return res.json() as Promise<TurnAcceptedResponse>;
}

// unit-36(STT 실시간 스트리밍 미리보기, 2026-09-23 사용자 승인): 답변을 녹음하는
// "도중"에 짧은 오디오 조각을 보내 인식 텍스트 미리보기만 받는다 — 최종 제출
// (`submitVoiceTurn`)과 별개 엔드포인트라 실패해도 최종 제출에는 영향 없다.
export async function submitVoicePreview(
  accessToken: string,
  interviewId: string,
  audioBlob: Blob,
): Promise<{ text: string }> {
  const formData = new FormData();
  formData.append("audio", audioBlob, "preview.webm");

  const res = await fetch(`${API_BASE_URL}/interviews/${interviewId}/turns/preview`, {
    method: "POST",
    credentials: "include",
    headers: { Authorization: `Bearer ${accessToken}` },
    body: formData,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(
      res.status,
      body?.code ?? "UNKNOWN_ERROR",
      body?.detail ?? "요청 처리 중 오류가 발생했습니다.",
    );
  }
  return res.json() as Promise<{ text: string }>;
}

// 03-system-design.md §4.3: WS는 `/api/v1` 프리픽스 없이 `/ws/interviews/{id}`이며,
// 토큰은 Authorization 헤더 대신 쿼리 파라미터로 전달한다(브라우저 WebSocket API가
// 커스텀 헤더를 지원하지 않음, backend/app/api/v1/ws.py 참고).
export function interviewWsUrl(interviewId: string, accessToken: string): string {
  const httpBase = API_BASE_URL.replace(/\/api\/v1\/?$/, "");
  const wsBase = httpBase.replace(/^http/, "ws");
  return `${wsBase}/ws/interviews/${interviewId}?token=${encodeURIComponent(accessToken)}`;
}

const ACCESS_TOKEN_KEY = "access_token";

export function storeAccessToken(token: string) {
  sessionStorage.setItem(ACCESS_TOKEN_KEY, token);
}

export function readAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem(ACCESS_TOKEN_KEY);
}

export function clearAccessToken() {
  sessionStorage.removeItem(ACCESS_TOKEN_KEY);
}

// REQ-016(unit-18): 03-system-design.md §4.2/§7.2, 04-ux-design.md [O-01].
export interface OpsHealthOut {
  queue_length: number;
  gpu_memory_used_bytes: number;
  error_rate: number;
  active_sessions: number;
  checked_at: string;
  notes: Record<string, string>;
}

export function getOpsHealth(accessToken: string): Promise<OpsHealthOut> {
  return request<OpsHealthOut>("/ops/health", {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

// REQ-011(unit-12): 03-system-design.md §4.2 `/recruiter/reports`, 04-ux-design.md
// [R-01]/[R-02].
export interface RecruiterInterviewListItemOut {
  interview_id: string;
  candidate_name: string;
  candidate_email: string;
  status: "scheduled" | "live" | "paused" | "completed" | "expired";
  report_status: "none" | "queued" | "ready" | "failed";
  started_at: string | null;
  ended_at: string | null;
  overall_score: string | null;
}

// Feature E(REQ-009/010/012): report_available=true일 때만 점수/STAR/추천등급이 채워진다.
export interface StarOut {
  situation: string;
  task: string;
  action: string;
  result: string;
}

export interface RecruiterReportDetailOut extends RecruiterInterviewListItemOut {
  report_available: boolean;
  message: string;
  technical_score: number | null;
  communication_score: number | null;
  cultural_fit_score: number | null;
  overall_recommendation: "recommend" | "neutral" | "not_recommend" | null;
  // 원안(REQ-F-006/007) 복원분(2026-09-22 사용자 명시 승인) — REQ-031과 긴장 관계,
  // 배포 전 법무 검토 필요(backend/app/models/evaluation_report.py 모듈 docstring 참고).
  pass_fail_recommendation: "pass" | "fail" | "borderline" | null;
  star: StarOut | null;
  summary_text: string | null;
  details: Record<string, unknown> | null;
  rubric: RubricReportOut | null;
}

// v15(03-system-design v4 §4.6 (5), unit-37, REQ-010/012): 루브릭 항목별 채점.
// 이 기능 이전 리포트나 템플릿을 찾지 못한 레거시 경로는 `rubric: null`이다.
export interface RubricCriterionScore {
  name: string;
  weight: number;
  description: string;
  score: number | null;
  evidence: string;
  answer_refs: number[];
}

export interface RubricAnswer {
  no: number;
  excerpt: string;
}

export interface RubricReportOut {
  template_id: string;
  name: string;
  criteria: RubricCriterionScore[];
  answers: RubricAnswer[];
}

// 캐노니컬 `GET /interviews/{id}/report`(지원자/채용담당자 공용, 03-design §4.2).
// report_status가 queued면 이 타입이 아니라 {status:"processing"}이 온다 — getReport()가
// 이를 구분해 반환한다.
export interface ReportOut {
  interview_id: string;
  report_status: "ready";
  overall_score: string | null;
  technical_score: number | null;
  communication_score: number | null;
  cultural_fit_score: number | null;
  overall_recommendation: "recommend" | "neutral" | "not_recommend" | null;
  pass_fail_recommendation: "pass" | "fail" | "borderline" | null;
  star: StarOut | null;
  summary_text: string | null;
  details: Record<string, unknown> | null;
  rubric: RubricReportOut | null;
  disclaimer: string;
}

export type ReportResult =
  | { status: "processing" }
  | { status: "ready"; report: ReportOut };

export async function getReport(accessToken: string, interviewId: string): Promise<ReportResult> {
  // 202({status:"processing"})와 200(ReportOut)이 같은 엔드포인트에서 오므로(§4.2),
  // `request<T>`가 상태코드와 무관하게 ok 응답(200~299)을 그대로 통과시키는 동작을
  // 활용해 응답 바디의 모양(`status` 필드 존재 여부)으로만 구분한다.
  const body = await request<{ status?: string } | ReportOut>(`/interviews/${interviewId}/report`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if ("status" in body && body.status === "processing") {
    return { status: "processing" };
  }
  return { status: "ready", report: body as ReportOut };
}

export function regenerateReport(accessToken: string, interviewId: string): Promise<{ job_id: string }> {
  return request<{ job_id: string }>(`/interviews/${interviewId}/report/regenerate`, {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

export function getRecruiterReports(accessToken: string): Promise<RecruiterInterviewListItemOut[]> {
  return request<RecruiterInterviewListItemOut[]>("/recruiter/reports", {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

export function getRecruiterReportDetail(
  accessToken: string,
  interviewId: string,
): Promise<RecruiterReportDetailOut> {
  return request<RecruiterReportDetailOut>(`/recruiter/reports/${interviewId}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

// REQ-002(unit-2)/REQ-031~034(unit-15): 03-system-design.md §4.2 `POST /interviews`,
// `POST /interviews/{id}/start`. [C-04] 사전고지·동의 화면이 세션을 만들고 시작하는 데
// 사용한다. `interviews.py` 자체는 unit-2/3/4 소유라 수정하지 않고, 이 함수는 그 API를
// 그대로 소비만 한다.
export function createInterview(accessToken: string): Promise<InterviewOut> {
  return request<InterviewOut>("/interviews", {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

// REQ-002(unit-19): 03-system-design.md §4.2 `GET /interviews`(내 면접 목록, DEC-024
// 갭1)와 04-ux-design.md [C-03] 지원자 홈이 소비한다. candidate 전용(그 외 역할은 403).
export interface InterviewListItemOut {
  id: string;
  status: InterviewOut["status"];
  report_status: InterviewOut["report_status"];
  started_at: string | null;
  ended_at: string | null;
  overall_score: string | null;
  created_at: string;
  resumable: boolean;
}

export function listMyInterviews(accessToken: string): Promise<InterviewListItemOut[]> {
  return request<InterviewListItemOut[]>("/interviews", {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

export interface InterviewStartResponse {
  job_id: string;
  message: string;
  interview: InterviewOut;
}

export function startInterview(accessToken: string, interviewId: string): Promise<InterviewStartResponse> {
  return request<InterviewStartResponse>(`/interviews/${interviewId}/start`, {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

export interface InterviewEndResponse {
  job_id: string;
  interview: InterviewOut;
}

export function endInterview(accessToken: string, interviewId: string): Promise<InterviewEndResponse> {
  return request<InterviewEndResponse>(`/interviews/${interviewId}/end`, {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

// REQ-029~034(unit-15, Feature G): backend/app/api/v1/consents.py(unit-14)를 그대로
// 소비한다 — 이 파일은 절대 수정하지 않는다. 필드명은 backend/app/schemas/consent.py와
// 1:1 대응.
export type ConsentType = "ai_interview_notice" | "biometric_voice";

export interface ConsentOut {
  id: string;
  consent_type: ConsentType;
  granted_at: string;
  revoked_at: string | null;
}

export function createConsent(accessToken: string, consentType: ConsentType): Promise<ConsentOut> {
  return request<ConsentOut>("/consents", {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
    body: JSON.stringify({ consent_type: consentType }),
  });
}

export function revokeConsent(accessToken: string, consentId: string): Promise<ConsentOut> {
  return request<ConsentOut>(`/consents/${consentId}/revoke`, {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

export function listMyConsents(accessToken: string): Promise<ConsentOut[]> {
  return request<ConsentOut[]>("/users/me/consents", {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

export type DeletionTarget = "biometric_only" | "full_account";
export type DeletionRequestStatus = "pending" | "completed";

export interface DeletionRequestOut {
  id: string;
  target: DeletionTarget;
  status: DeletionRequestStatus;
  requested_at: string;
  completed_at: string | null;
}

export function requestBiometricDataDeletion(accessToken: string): Promise<DeletionRequestOut> {
  return request<DeletionRequestOut>("/users/me/biometric-data", {
    method: "DELETE",
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

export function listMyDeletionRequests(accessToken: string): Promise<DeletionRequestOut[]> {
  return request<DeletionRequestOut[]>("/users/me/deletion-requests", {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

// REQ-017(unit-17): 03-system-design.md v2 §4.2 `PUT`/`GET /interviews/{id}/whiteboard`,
// 04-ux-design.md [C-08]. DEC-008 — AI 자동분석 없는 순수 드로잉 데이터(스트로크
// 좌표 배열)만 다룬다.
export interface WhiteboardPoint {
  x: number;
  y: number;
}

export interface WhiteboardStroke {
  points: WhiteboardPoint[];
  color: string;
  width: number;
}

export interface WhiteboardSnapshotOut {
  id: string;
  interview_id: string;
  strokes: WhiteboardStroke[];
  created_at: string;
}

export function saveWhiteboard(
  accessToken: string,
  interviewId: string,
  strokes: WhiteboardStroke[],
): Promise<WhiteboardSnapshotOut> {
  return request<WhiteboardSnapshotOut>(`/interviews/${interviewId}/whiteboard`, {
    method: "PUT",
    headers: { Authorization: `Bearer ${accessToken}` },
    body: JSON.stringify({ strokes }),
  });
}

export function getWhiteboard(
  accessToken: string,
  interviewId: string,
): Promise<WhiteboardSnapshotOut | null> {
  return request<WhiteboardSnapshotOut | null>(`/interviews/${interviewId}/whiteboard`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

// unit-35(REQ-021 부분 재도입, 2026-09-23): 로컬 SmolVLM(무료) 비전 분석.
// disclaimer는 항상 채워져 내려온다(whiteboard_vision.py LOW_CONFIDENCE_DISCLAIMER) —
// 모델 품질이 낮다는 실측 근거에 따른 필수 고지이므로 화면에서 생략하면 안 된다.
export interface WhiteboardAnalysisOut {
  analysis: string;
  disclaimer: string;
  model: string;
}

export function analyzeWhiteboard(accessToken: string, interviewId: string): Promise<WhiteboardAnalysisOut> {
  return request<WhiteboardAnalysisOut>(`/interviews/${interviewId}/whiteboard/analyze`, {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

// REQ-014(unit-13): 03-system-design.md §3.1(RUBRIC_TEMPLATES)/§4.2
// `/recruiter/rubric-templates`, 04-ux-design.md [R-03]. `recruiter_id`가 null이면
// 시스템 기본 템플릿(모든 recruiter가 조회 가능, 직접 수정은 불가 — 복사해서 새로
// 만들어야 함).
export interface RubricCriterion {
  name: string;
  weight: number;
  description: string;
}

export interface RubricTemplateOut {
  id: string;
  recruiter_id: string | null;
  name: string;
  criteria: RubricCriterion[];
  is_system_default: boolean;
  created_at: string;
}

export function listRubricTemplates(accessToken: string): Promise<RubricTemplateOut[]> {
  return request<RubricTemplateOut[]>("/recruiter/rubric-templates", {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

export function createRubricTemplate(
  accessToken: string,
  input: { name: string; criteria: RubricCriterion[] },
): Promise<RubricTemplateOut> {
  return request<RubricTemplateOut>("/recruiter/rubric-templates", {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
    body: JSON.stringify(input),
  });
}

export function updateRubricTemplate(
  accessToken: string,
  templateId: string,
  input: { name?: string; criteria?: RubricCriterion[] },
): Promise<RubricTemplateOut> {
  return request<RubricTemplateOut>(`/recruiter/rubric-templates/${templateId}`, {
    method: "PATCH",
    headers: { Authorization: `Bearer ${accessToken}` },
    body: JSON.stringify(input),
  });
}

// v15(03-system-design v4 §4.6 (2), unit-37, REQ-010/014, DEC-054/055): 면접에
// 채점용 루브릭 템플릿을 지정/변경한다. `job_id`가 있으면 재채점이 새로 투입된
// 것이다(04-ux-design [R-02] "이 템플릿으로 다시 채점" 처리 참고). 409/503은
// 호출부가 `ApiError.status`로 구분해 처리한다.
export interface RubricTemplateAssignOut {
  interview_id: string;
  rubric_template_id: string;
  job_id: string | null;
}

export function assignRubricTemplate(
  accessToken: string,
  interviewId: string,
  rubricTemplateId: string,
): Promise<RubricTemplateAssignOut> {
  return request<RubricTemplateAssignOut>(`/recruiter/interviews/${interviewId}/rubric-template`, {
    method: "PUT",
    headers: { Authorization: `Bearer ${accessToken}` },
    body: JSON.stringify({ rubric_template_id: rubricTemplateId }),
  });
}
