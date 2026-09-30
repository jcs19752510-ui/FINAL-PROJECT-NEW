"use client";

/**
 * [Feature J] 채용 지원 포털 랜딩 — 이 앱 자체가 3002번 포트로 완전히 분리된
 * 채용 지원 전용 서비스다(2026-09-29, 사용자 지시로 frontend(3001)의 /apply/*
 * 경로에서 이 별도 앱으로 이전). 백엔드(8001)는 모의면접 앱과 공유한다.
 */
import Link from "next/link";

export default function ApplyLandingPage() {
  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1>채용 지원</h1>
        <p style={{ color: "var(--color-text-secondary)", marginBottom: 24 }}>
          회원가입하고 이력서를 제출하면 서류 심사 결과를 이메일로 알려드려요.
          합격하면 모의면접 사이트에 같은 계정으로 로그인해서 모의면접을 진행할 수 있어요.
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
