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
