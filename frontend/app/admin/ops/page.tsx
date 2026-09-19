"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ApiError, getMe, getOpsHealth, readAccessToken, type OpsHealthOut, type UserOut } from "@/lib/api";

// REQ-016(unit-18): 04-ux-design.md [O-01] 운영자 모니터링 화면.
// 5~10초 주기 폴링 사양(§2 [O-01])의 중간값으로 7초를 채택.
const POLL_INTERVAL_MS = 7000;

function formatMetric(value: number, unit: string, digits = 0): string {
  return `${value.toFixed(digits)}${unit}`;
}

export default function OpsMonitoringPage() {
  const [token] = useState(() => readAccessToken());
  const [user, setUser] = useState<UserOut | null>(null);
  const [authLoading, setAuthLoading] = useState(() => Boolean(token));

  const [health, setHealth] = useState<OpsHealthOut | null>(null);
  const [healthLoading, setHealthLoading] = useState(true);
  const [healthError, setHealthError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!token) return;
    getMe(token)
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setAuthLoading(false));
  }, [token]);

  useEffect(() => {
    if (!token || !user || user.role !== "admin") return;

    let cancelled = false;

    const poll = () => {
      getOpsHealth(token)
        .then((data) => {
          if (cancelled) return;
          setHealth(data);
          setHealthError(null);
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          // 03-system-design §7.2/04-ux-design [O-01] 에러 상태: 마지막 성공값을
          // 화면에서 지우지 않고 "갱신 실패" 배지만 표시한다.
          const message = err instanceof ApiError ? err.message : "네트워크 오류";
          setHealthError(message);
        })
        .finally(() => setHealthLoading(false));
    };

    poll();
    pollRef.current = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [token, user]);

  if (authLoading) {
    return (
      <div className="auth-page">
        <div className="auth-card">불러오는 중...</div>
      </div>
    );
  }

  if (!token || !user) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h1>로그인이 필요합니다</h1>
          <Link href="/login" className="submit-button" style={{ textAlign: "center", textDecoration: "none" }}>
            로그인하러 가기
          </Link>
        </div>
      </div>
    );
  }

  if (user.role !== "admin") {
    // 04-ux-design.md [G-02]: 역할 불일치 시 안내 + 홈으로.
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h1>권한이 없습니다</h1>
          <p style={{ color: "var(--color-text-secondary)" }}>
            운영자 모니터링 화면은 관리자(admin) 계정만 접근할 수 있습니다.
          </p>
          <Link href="/" className="submit-button" style={{ textAlign: "center", textDecoration: "none" }}>
            홈으로
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="ops-page">
      <header className="ops-page__header">
        <h1>운영자 모니터링</h1>
        {healthError && <span className="ops-badge ops-badge--error">갱신 실패</span>}
      </header>

      {healthLoading ? (
        <div className="ops-metric-grid" aria-busy="true">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="ops-metric-card ops-metric-card--skeleton" />
          ))}
        </div>
      ) : (
        <>
          <div className="ops-metric-grid">
            <MetricCard label="큐 길이" value={health ? formatMetric(health.queue_length, "건") : "-"} />
            <MetricCard
              label="GPU 메모리 사용량"
              value={health ? formatMetric(health.gpu_memory_used_bytes / 1_000_000, "MB") : "-"}
            />
            <MetricCard
              label="에러율"
              value={health ? formatMetric(health.error_rate * 100, "%", 1) : "-"}
            />
            <MetricCard label="활성 세션 수" value={health ? formatMetric(health.active_sessions, "명") : "-"} />
          </div>

          <p className="ops-updated-at">
            {health ? `최근 갱신: ${new Date(health.checked_at).toLocaleString("ko-KR")}` : "갱신 이력 없음"}
          </p>

          {health && (
            <details className="ops-notes">
              <summary>지표 산출 근거 (실측 여부)</summary>
              <ul>
                {Object.entries(health.notes).map(([key, note]) => (
                  <li key={key}>
                    <strong>{key}</strong>: {note}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="ops-metric-card">
      <span className="ops-metric-card__label">{label}</span>
      <span className="ops-metric-card__value">{value}</span>
    </div>
  );
}
