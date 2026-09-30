"use client";

/**
 * [Feature J] 이력서 제출/상태 확인 — 이력서제출_합격통보_신규기능_요청프롬프트.md
 * §4-1. 로그인한 candidate가 PDF 이력서를 제출하고, 제출 후에는 현재 심사
 * 상태(pending/accepted/rejected)를 확인한다. 재제출은 언제든 가능하며
 * (백엔드가 상태를 pending으로 되돌림), 이 화면은 그 정책을 그대로 반영해
 * 재업로드 폼을 항상 노출한다.
 */
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  ApiError,
  type MyResumeStatusOut,
  type UserOut,
  clearAccessToken,
  createConsent,
  getMe,
  getMyResumeStatus,
  readAccessToken,
  submitResume,
} from "@/lib/api";
import HomeLink from "@/components/HomeLink";

const STATUS_LABEL: Record<MyResumeStatusOut["status"], string> = {
  pending: "심사 중",
  accepted: "합격",
  rejected: "불합격",
};

function formatDateTime(iso: string | null): string {
  if (!iso) return "-";
  return new Date(iso).toLocaleString("ko-KR");
}

export default function ApplyResumePage() {
  const router = useRouter();
  const [accessToken] = useState<string | null>(() => readAccessToken());
  const [user, setUser] = useState<UserOut | null>(null);
  const [authLoading, setAuthLoading] = useState(true);

  const [status, setStatus] = useState<MyResumeStatusOut | null | "loading">("loading");
  const [file, setFile] = useState<File | null>(null);
  const [agreed, setAgreed] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
    if (!accessToken || !user || user.role !== "candidate") return;
    getMyResumeStatus(accessToken)
      .then(setStatus)
      .catch(() => setStatus(null));
  }, [accessToken, user]);

  async function handleSubmit() {
    if (!accessToken || !file || !agreed || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await createConsent(accessToken, "resume_submission");
      const result = await submitResume(accessToken, file);
      setStatus(result);
      setFile(null);
      setAgreed(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "네트워크 오류예요. 잠시 후 다시 시도해주세요.");
    } finally {
      setSubmitting(false);
    }
  }

  if (authLoading) {
    return (
      <div className="auth-page">
        <div className="auth-card">불러오는 중...</div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h1>로그인이 필요합니다</h1>
          <a href="/login" className="submit-button" style={{ textAlign: "center", textDecoration: "none" }}>
            로그인하러 가기
          </a>
        </div>
      </div>
    );
  }

  if (user.role !== "candidate") {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h1>권한이 없습니다</h1>
          <p style={{ color: "var(--color-text-secondary)" }}>이력서 제출은 지원자 계정으로만 할 수 있어요.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-page">
      <div className="auth-card" style={{ maxWidth: 480 }}>
        <HomeLink />
        <h1>이력서 제출</h1>
        <p style={{ color: "var(--color-text-secondary)", marginBottom: 20 }}>{user.name}님, 안녕하세요.</p>

        {status !== "loading" && status !== null && (
          <div
            className="field"
            style={{
              background: "var(--color-surface-secondary, #f3f4f6)",
              borderRadius: 8,
              padding: 14,
              marginBottom: 20,
            }}
          >
            <strong>현재 상태: {STATUS_LABEL[status.status]}</strong>
            <div style={{ fontSize: 13, color: "var(--color-text-secondary)", marginTop: 6 }}>
              제출한 파일: {status.original_filename} · 제출일시: {formatDateTime(status.submitted_at)}
            </div>
            {status.reviewed_at && (
              <div style={{ fontSize: 13, color: "var(--color-text-secondary)", marginTop: 2 }}>
                심사일시: {formatDateTime(status.reviewed_at)}
              </div>
            )}
            {status.status === "accepted" && (
              <div style={{ marginTop: 10 }}>
                <p>서류 전형에 합격했어요! 모의면접 사이트에 이 계정으로 로그인해서 모의면접을 진행해주세요.</p>
                {status.interview_schedule_note && <p><strong>면접 일정:</strong> {status.interview_schedule_note}</p>}
              </div>
            )}
            {status.status === "rejected" && status.decision_note && (
              <p style={{ marginTop: 10 }}>{status.decision_note}</p>
            )}
            {status.status === "pending" && <p style={{ marginTop: 10 }}>서류를 심사하고 있어요. 결과가 나오면 등록한 이메일로 알려드릴게요.</p>}
          </div>
        )}

        {error && <div className="banner-error">{error}</div>}

        <div
          className="field"
          style={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: 8, padding: 12 }}
        >
          <p style={{ margin: "0 0 8px", fontSize: 13, color: "var(--color-text-secondary)" }}>
            이력서를 어떻게 써야 할지 모르겠다면? 샘플 양식(PDF)을 내려받아 참고해보세요.
          </p>
          <a href="/sample-resume.pdf" download="이력서_샘플_양식.pdf" className="submit-button" style={{ display: "inline-block", textAlign: "center", textDecoration: "none" }}>
            이력서 샘플 양식 다운로드
          </a>
        </div>

        <div className="field">
          <label htmlFor="resume-file">{status && status !== "loading" ? "이력서 다시 제출(PDF)" : "이력서 제출(PDF)"}</label>
          <input
            id="resume-file"
            type="file"
            accept="application/pdf"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </div>

        <div className="field">
          <label style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
            <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} required />
            <span>이력서에 있는 개인정보를 수집·이용하는 데 동의합니다.</span>
          </label>
        </div>

        <button
          type="button"
          className="submit-button"
          disabled={!file || !agreed || submitting}
          onClick={handleSubmit}
        >
          {submitting ? "제출 중..." : "제출하기"}
        </button>
      </div>
    </div>
  );
}
