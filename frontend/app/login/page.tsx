"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";
import Link from "next/link";
import { ApiError, loginUser, storeAccessToken } from "@/lib/api";

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const justRegistered = searchParams.get("registered") === "1";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!email || !password || submitting) return;

    setSubmitting(true);
    setError(null);

    try {
      const result = await loginUser({ email, password });
      storeAccessToken(result.access_token);
      router.push("/");
    } catch (err) {
      if (err instanceof ApiError) {
        setError("이메일 또는 비밀번호가 올바르지 않습니다.");
      } else {
        setError("네트워크 오류가 발생했습니다. 잠시 후 다시 시도해주세요.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1>로그인</h1>
        {justRegistered && (
          <div style={{ color: "var(--color-text-secondary)", fontSize: 13, marginBottom: 16 }}>
            회원가입이 완료되었습니다. 로그인해주세요.
          </div>
        )}
        {error && <div className="banner-error">{error}</div>}

        <form onSubmit={handleSubmit} noValidate>
          <div className="field">
            <label htmlFor="email">이메일</label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              required
            />
          </div>

          <div className="field">
            <label htmlFor="password">비밀번호</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </div>

          <button type="submit" className="submit-button" disabled={submitting || !email || !password}>
            {submitting ? "로그인 중..." : "로그인"}
          </button>
        </form>

        <div className="auth-footer">
          계정이 없으신가요? <Link href="/register">회원가입</Link>
        </div>
      </div>
    </div>
  );
}
