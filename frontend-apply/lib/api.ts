// frontend/lib/api.ts(모의면접 앱)와 백엔드 계약은 100% 동일 — 이 앱은 같은
// 백엔드(8001)를 그대로 쓴다(요청 프롬프트 §2 결정#1/#2, 계정 공유 전제).
// 이 파일은 채용 지원 포털이 실제로 쓰는 부분만 가져온 축소판이다(2026-09-29,
// 포트 3002 분리 시 신설 — 두 프런트가 서로 import할 수 없는 별개 앱이라 부득이
// 하게 필요한 함수만 복제했다. 백엔드 스키마가 바뀌면 양쪽 다 수동 동기화 필요
// — 이 트레이드오프는 "포트 분리"를 선택한 데 따른 자연스러운 결과다).

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001/api/v1";

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
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  if (!res.ok) {
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

export type ConsentType = "ai_interview_notice" | "biometric_voice" | "resume_submission";

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

// Feature J(REQ-040/041) — 이력서제출_합격통보_신규기능_요청프롬프트.md §4-4.
export type ResumeApplicationStatus = "pending" | "accepted" | "rejected";

export interface MyResumeStatusOut {
  id: string;
  status: ResumeApplicationStatus;
  original_filename: string;
  decision_note: string | null;
  interview_schedule_note: string | null;
  submitted_at: string;
  reviewed_at: string | null;
}

export function getMyResumeStatus(accessToken: string): Promise<MyResumeStatusOut | null> {
  return request<MyResumeStatusOut | null>("/users/me/resume-status", {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

export async function submitResume(accessToken: string, file: File): Promise<MyResumeStatusOut> {
  const formData = new FormData();
  formData.append("file", file, file.name);

  const res = await fetch(`${API_BASE_URL}/resumes`, {
    method: "POST",
    credentials: "include",
    headers: { Authorization: `Bearer ${accessToken}` },
    body: formData,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(res.status, body?.code ?? "UNKNOWN_ERROR", body?.detail ?? "요청 처리 중 오류가 발생했습니다.");
  }
  return res.json() as Promise<MyResumeStatusOut>;
}
