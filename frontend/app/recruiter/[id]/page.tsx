"use client";

/**
 * [R-02] 리포트 상세(열람 전용) — unit-12, Feature F, REQ-011.
 *
 * 04-ux-design.md v2 §2 [R-02] 명세와 편차: 캐노니컬 엔드포인트는
 * `GET /interviews/{id}/report`이나, 이 유닛은 병렬 개발 파일 충돌 회피를 위해
 * `GET /recruiter/reports/{interview_id}`(backend/app/api/v1/recruiter.py)를
 * 전용으로 사용한다(백엔드 모듈 docstring 참고). Feature E(리포트 생성) 미구현으로
 * 점수 게이지/STAR 피드백/근거 아코디언 등 리포트 본문은 아직 없으며, 이 화면은
 * `report_available=false`일 때 상태 안내만 정직하게 표시한다(가짜 데이터 금지).
 * REQ-034 법률자문 고지 배너는 리포트 본문 유무와 무관하게 항상 노출한다.
 */
import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ApiError,
  type RecruiterReportDetailOut,
  type UserOut,
  clearAccessToken,
  getMe,
  getRecruiterReportDetail,
  readAccessToken,
} from "@/lib/api";
import styles from "../recruiter.module.css";

const STATUS_LABEL: Record<RecruiterReportDetailOut["status"], string> = {
  scheduled: "예정",
  live: "진행 중",
  paused: "일시중지",
  completed: "완료",
  expired: "만료",
};

function formatDateTime(iso: string | null): string {
  if (!iso) return "-";
  return new Date(iso).toLocaleString("ko-KR");
}

export default function RecruiterReportDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [accessToken] = useState<string | null>(() => readAccessToken());

  const [user, setUser] = useState<UserOut | null>(null);
  const [authLoading, setAuthLoading] = useState(true);

  const [detail, setDetail] = useState<RecruiterReportDetailOut | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

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
    if (!accessToken || !user || user.role !== "recruiter" || !params.id) return;
    getRecruiterReportDetail(accessToken, params.id)
      .then(setDetail)
      .catch((err: unknown) => {
        setLoadError(
          err instanceof ApiError ? err.message : "네트워크 오류로 리포트를 불러오지 못했습니다.",
        );
      })
      .finally(() => setLoading(false));
  }, [accessToken, user, params.id]);

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
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h1>권한이 없습니다</h1>
          <p style={{ color: "var(--color-text-secondary)" }}>
            리포트 상세 화면은 채용담당자(recruiter) 계정만 접근할 수 있습니다.
          </p>
          <Link href="/" className="submit-button" style={{ textAlign: "center", textDecoration: "none" }}>
            홈으로
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <Link href="/recruiter" className={styles.backLink}>
        &larr; 목록으로
      </Link>

      {loading ? (
        <div className={styles.skeleton} aria-busy="true">
          리포트를 불러오는 중입니다...
        </div>
      ) : loadError || !detail ? (
        <div className="banner-error" role="alert">
          {loadError ?? "리포트를 찾을 수 없습니다."}
        </div>
      ) : (
        <div className={styles.detailCard}>
          <div className={styles.detailHeader}>
            <h2>{detail.candidate_name}</h2>
            <span className={styles.statusTag}>{STATUS_LABEL[detail.status]}</span>
          </div>
          <div className={styles.metaRow}>
            <span>이메일: {detail.candidate_email}</span>
            <span>응시 시작: {formatDateTime(detail.started_at)}</span>
            <span>응시 종료: {formatDateTime(detail.ended_at)}</span>
            <span>종합 점수: {detail.overall_score ?? "-"}</span>
          </div>

          <div className={styles.reportBody}>
            {detail.report_available ? (
              <p>{detail.message}</p>
            ) : (
              <div className={styles.emptyText}>{detail.message}</div>
            )}
          </div>
        </div>
      )}

      <div className={styles.disclaimerBanner}>
        본 리포트/평가는 참고용이며 법적 효력이 없습니다. 채용 의사결정에 대한 법률적 판단은
        본 서비스가 대신하지 않습니다.
      </div>
    </div>
  );
}
