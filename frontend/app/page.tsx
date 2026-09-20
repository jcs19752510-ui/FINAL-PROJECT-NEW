"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import CandidateHome from "@/components/CandidateHome";
import { clearAccessToken, getMe, readAccessToken, type UserOut } from "@/lib/api";

const subscribeNever = () => () => {};

export default function HomePage() {
  // 토큰은 sessionStorage에만 있어 서버 렌더에서는 알 수 없다. 서버 HTML(토큰 없음 → 랜딩)과
  // 하이드레이션 첫 렌더가 달라 React #418이 나던 문제를 피하려고, 마운트 전에는 서버와
  // 동일한 "불러오는 중"만 그린다.
  const mounted = useSyncExternalStore(subscribeNever, () => true, () => false);
  const [token] = useState(() => readAccessToken());
  const [user, setUser] = useState<UserOut | null>(null);
  const [settled, setSettled] = useState(false);

  useEffect(() => {
    if (!token) return;
    getMe(token)
      .then(setUser)
      .catch(() => clearAccessToken())
      .finally(() => setSettled(true));
  }, [token]);

  const loading = !mounted || (token !== null && !settled);

  const handleLogout = useCallback(() => {
    clearAccessToken();
    setUser(null);
  }, []);

  if (loading) {
    return (
      <div className="auth-page">
        <div className="auth-card">불러오는 중...</div>
      </div>
    );
  }

  // [C-03] 지원자 홈(unit-19). 면접 목록/세션 시작 동선은 candidate 전용이다.
  if (user && token && user.role === "candidate") {
    return <CandidateHome user={user} accessToken={token} onLogout={handleLogout} onSessionExpired={handleLogout} />;
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
          {user.role === "recruiter" && (
            <p>
              <Link href="/recruiter">지원자 리포트 목록으로 이동</Link>
            </p>
          )}
          <button type="button" className="submit-button" onClick={handleLogout}>
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
          로그인하면 지원자 홈에서 새 면접을 시작하고 지난 면접을 확인할 수 있습니다.
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
