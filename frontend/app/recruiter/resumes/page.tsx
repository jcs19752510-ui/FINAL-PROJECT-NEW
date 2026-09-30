"use client";

/**
 * [Feature J] 이력서 검토 목록 — 이력서제출_합격통보_신규기능_요청프롬프트.md §4-2.
 * `frontend/app/recruiter/page.tsx`(리포트 목록)와 동일한 인증/역할체크 패턴을
 * 그대로 따른다.
 */
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ApiError,
  type RecruiterResumeListItemOut,
  type UserOut,
  clearAccessToken,
  getMe,
  listRecruiterResumes,
  readAccessToken,
} from "@/lib/api";
import HomeLink from "@/components/HomeLink";
import RecruiterListTabs from "@/components/RecruiterListTabs";
import styles from "../recruiter.module.css";

const STATUS_LABEL: Record<RecruiterResumeListItemOut["status"], string> = {
  pending: "심사 대기",
  accepted: "합격",
  rejected: "불합격",
};

function formatDateTime(iso: string | null): string {
  if (!iso) return "-";
  return new Date(iso).toLocaleString("ko-KR");
}

export default function RecruiterResumesPage() {
  const router = useRouter();
  const [accessToken] = useState<string | null>(() => readAccessToken());

  const [user, setUser] = useState<UserOut | null>(null);
  const [authLoading, setAuthLoading] = useState(true);

  const [resumes, setResumes] = useState<RecruiterResumeListItemOut[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

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
    listRecruiterResumes(accessToken)
      .then(setResumes)
      .catch((err: unknown) => {
        setLoadError(err instanceof ApiError ? err.message : "네트워크 오류로 목록을 가져오지 못했어요.");
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
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h1>권한이 없습니다</h1>
          <p style={{ color: "var(--color-text-secondary)" }}>이력서 검토는 채용담당자 계정으로만 볼 수 있어요.</p>
          <Link href="/" className="submit-button" style={{ textAlign: "center", textDecoration: "none" }}>
            홈으로
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <HomeLink />
      <RecruiterListTabs />
      <div className={styles.detailHeader}>
        <h1 style={{ margin: 0 }}>이력서 검토</h1>
      </div>
      <p className={styles.subtitle}>
        제출된 이력서를 확인하고 합격/불합격을 정해주세요. 합격/불합격 안내는 이 화면에서 만든 초안을 관리자가 직접 보내는 방식이에요.
      </p>

      {loadError && (
        <div className="banner-error" role="alert" style={{ marginBottom: 16 }}>
          {loadError}
        </div>
      )}

      {resumes === null ? (
        <div className={styles.skeleton} aria-busy="true">
          목록을 불러오는 중이에요...
        </div>
      ) : resumes.length === 0 ? (
        <div className={styles.emptyText}>아직 제출된 이력서가 없어요.</div>
      ) : (
        <table className={styles.table}>
          <thead>
            <tr>
              <th>지원자</th>
              <th>이메일</th>
              <th>상태</th>
              <th>제출일시</th>
              <th>심사일시</th>
              <th>안내</th>
            </tr>
          </thead>
          <tbody>
            {resumes.map((r) => (
              <tr key={r.id} className={styles.tableRow} onClick={() => router.push(`/recruiter/resumes/${r.id}`)}>
                <td>{r.candidate_name}</td>
                <td>{r.candidate_email}</td>
                <td>
                  <span className={styles.statusTag}>{STATUS_LABEL[r.status]}</span>
                </td>
                <td>{formatDateTime(r.submitted_at)}</td>
                <td>{formatDateTime(r.reviewed_at)}</td>
                <td>{r.notified_at ? "완료" : "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
