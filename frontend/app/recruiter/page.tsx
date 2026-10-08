"use client";

/**
 * [R-01] 리포트 목록 대시보드 (Recruiter, 최소 뷰어) — unit-12, Feature F, REQ-011.
 *
 * 04-ux-design.md v2 §2 [R-01] 명세: `GET /recruiter/reports` 하나로 지원자/면접
 * 목록을 표시한다. 정렬/페이지네이션 쿼리 파라미터는 §7에서 "경미(블로킹 아님)"로
 * 표시된 미확정 항목이라 이번 유닛에서는 서버가 이미 정렬해 내려주는 목록을
 * 그대로 렌더링하고, 클라이언트 정렬/페이지네이션은 범위에 포함하지 않는다.
 */
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ApiError,
  type RecruiterInterviewListItemOut,
  type UserOut,
  clearAccessToken,
  getMe,
  getRecruiterReports,
  readAccessToken,
} from "@/lib/api";
import HomeLink from "@/components/HomeLink";
import RecruiterListTabs from "@/components/RecruiterListTabs";
import styles from "./recruiter.module.css";

const STATUS_LABEL: Record<RecruiterInterviewListItemOut["status"], string> = {
  scheduled: "예정",
  live: "진행 중",
  paused: "일시중지",
  completed: "완료",
  expired: "만료",
};

const REPORT_STATUS_LABEL: Record<RecruiterInterviewListItemOut["report_status"], string> = {
  none: "미요청",
  queued: "생성 중",
  ready: "준비됨",
  failed: "실패",
};

type StatusFilter = "all" | RecruiterInterviewListItemOut["status"];

// "전체"를 맨 앞에 두고 면접 상태(STATUS_LABEL)를 진행 순서대로 나열한다.
const STATUS_FILTER_OPTIONS: StatusFilter[] = ["all", "scheduled", "live", "paused", "completed", "expired"];

function formatDateTime(iso: string | null): string {
  if (!iso) return "-";
  return new Date(iso).toLocaleString("ko-KR");
}

export default function RecruiterDashboardPage() {
  const router = useRouter();
  const [accessToken] = useState<string | null>(() => readAccessToken());

  const [user, setUser] = useState<UserOut | null>(null);
  const [authLoading, setAuthLoading] = useState(true);

  const [reports, setReports] = useState<RecruiterInterviewListItemOut[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");

  useEffect(() => {
    if (!accessToken) {
      router.push("/login");
      return;
    }
    getMe(accessToken)
      .then(setUser)
      .catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 401) {
          clearAccessToken();
          router.push("/login");
          return;
        }
        setUser(null);
      })
      .finally(() => setAuthLoading(false));
  }, [accessToken, router]);

  useEffect(() => {
    if (!accessToken || !user || user.role !== "recruiter") return;
    getRecruiterReports(accessToken)
      .then(setReports)
      .catch((err: unknown) => {
        setLoadError(err instanceof ApiError ? err.message : "네트워크 오류로 목록을 불러오지 못했습니다.");
      });
  }, [accessToken, user]);

  if (authLoading) {
    return (
      <div className={styles.page}>
        <div className={styles.skeleton}>불러오는 중...</div>
      </div>
    );
  }

  if (!user) {
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

  if (user.role !== "recruiter") {
    // 04-ux-design.md [G-02]: 역할 불일치 시 안내 + 홈으로.
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h1>권한이 없습니다</h1>
          <p style={{ color: "var(--color-text-secondary)" }}>
            채용담당자 대시보드는 채용담당자 계정으로만 볼 수 있어요.
          </p>
          <Link href="/" className="submit-button" style={{ textAlign: "center", textDecoration: "none" }}>
            홈으로
          </Link>
        </div>
      </div>
    );
  }

  // 서버가 내려준 목록을 그대로 두고 화면에서만 거른다(추가 API 호출 없음).
  const filteredReports =
    reports === null || statusFilter === "all" ? reports : reports.filter((r) => r.status === statusFilter);

  return (
    <div className={styles.page}>
      <HomeLink />
      <RecruiterListTabs />
      <div className={styles.detailHeader}>
        <h1 style={{ margin: 0 }}>지원자 리포트 목록</h1>
      </div>
      <p className={styles.subtitle}>우리 조직의 모든 지원자 면접 내역을 볼 수 있어요.</p>

      <div className={styles.filterRow}>
        <label htmlFor="status-filter" className={styles.filterLabel}>
          면접 상태
        </label>
        <select
          id="status-filter"
          className={styles.filterSelect}
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
        >
          {STATUS_FILTER_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s === "all" ? "전체" : STATUS_LABEL[s]}
            </option>
          ))}
        </select>
      </div>

      {loadError && (
        <div className="banner-error" role="alert" style={{ marginBottom: 16 }}>
          {loadError}
        </div>
      )}

      {reports === null ? (
        <div className={styles.skeleton} aria-busy="true">
          목록을 불러오는 중입니다...
        </div>
      ) : reports.length === 0 ? (
        <div className={styles.emptyText}>아직 열람 가능한 리포트가 없습니다.</div>
      ) : filteredReports!.length === 0 ? (
        <div className={styles.emptyText}>선택한 면접 상태의 내역이 없습니다.</div>
      ) : (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>지원자</th>
              <th>이메일</th>
              <th>면접 상태</th>
              <th>리포트 상태</th>
              <th>응시 시작</th>
              <th>종합 점수</th>
            </tr>
          </thead>
          <tbody>
            {filteredReports!.map((r) => (
              <tr
                key={r.interview_id}
                className={styles.tableRow}
                onClick={() => router.push(`/recruiter/${r.interview_id}`)}
              >
                <td>{r.candidate_name}</td>
                <td>{r.candidate_email}</td>
                <td>
                  <span className={styles.statusTag}>{STATUS_LABEL[r.status]}</span>
                </td>
                <td>
                  <span className={styles.statusTag}>{REPORT_STATUS_LABEL[r.report_status]}</span>
                </td>
                <td>{formatDateTime(r.started_at)}</td>
                <td>{r.overall_score ?? "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div style={{ marginTop: 32 }}>
        <Link href="/">홈으로 돌아가기</Link>
      </div>
    </div>
  );
}
