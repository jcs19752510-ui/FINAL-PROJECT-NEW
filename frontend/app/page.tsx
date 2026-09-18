"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { clearAccessToken, getMe, readAccessToken, type UserOut } from "@/lib/api";

export default function HomePage() {
  const [token] = useState(() => readAccessToken());
  const [user, setUser] = useState<UserOut | null>(null);
  const [loading, setLoading] = useState(() => Boolean(token));

  useEffect(() => {
    if (!token) return;
    getMe(token)
      .then(setUser)
      .catch(() => clearAccessToken())
      .finally(() => setLoading(false));
  }, [token]);

  if (loading) {
    return (
      <div className="auth-page">
        <div className="auth-card">불러오는 중...</div>
      </div>
    );
  }

  if (user) {
    const roleLabel = user.role === "candidate" ? "지원자" : user.role === "recruiter" ? "채용담당자" : user.role;
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h1>{user.name}님, 환영합니다</h1>
          <p style={{ color: "var(--color-text-secondary)" }}>
            역할: {roleLabel} ({user.email})
          </p>
          <p style={{ color: "var(--color-text-secondary)", fontSize: 13 }}>
            면접 세션 관리 등 이후 기능은 다음 작업 단위(unit-2 이상)에서 추가됩니다.
          </p>
          <button
            type="button"
            className="submit-button"
            onClick={() => {
              clearAccessToken();
              setUser(null);
            }}
          >
            로그아웃
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1>AI 모의면접 플랫폼</h1>
        <p style={{ color: "var(--color-text-secondary)", marginBottom: 24 }}>
          unit-1(인증/사용자관리)까지 구현된 상태입니다. 지원자 홈 대시보드는 이후 작업 단위(unit-2 이상)에서 추가됩니다.
        </p>
        <div style={{ display: "flex", gap: 12 }}>
          <Link href="/login" className="submit-button" style={{ textAlign: "center", textDecoration: "none" }}>
            로그인
          </Link>
          <Link
            href="/register"
            className="submit-button"
            style={{ textAlign: "center", textDecoration: "none", background: "var(--color-text-secondary)" }}
          >
            회원가입
          </Link>
        </div>
      </div>
    </div>
  );
}
