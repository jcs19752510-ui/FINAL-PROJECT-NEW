"use client";

/**
 * 면접기준(AI 이력서 판정 기준) 등록/수정 화면 — 채용담당자 전용.
 * 인증/역할체크는 app/recruiter/resumes/page.tsx 패턴을 따른다.
 */
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ApiError,
  type ScreeningCriteriaOut,
  type UserOut,
  clearAccessToken,
  getMe,
  getScreeningCriteria,
  readAccessToken,
  saveScreeningCriteria,
} from "@/lib/api";
import HomeLink from "@/components/HomeLink";
import RecruiterListTabs from "@/components/RecruiterListTabs";
import {
  AI_ADVISORY_NOTICE,
  CRITERIA_MAX_LENGTH,
  THRESHOLD_DEFAULT,
  isDirty,
  validateCriteriaInput,
} from "@/lib/screeningView.mjs";
import styles from "../recruiter.module.css";

const PLACEHOLDER = "필수: Java/Spring 3년 이상 경력\n우대: AWS, Kubernetes 경험\n결격: 직무 관련 경력 없음";

function formatDateTime(iso: string | null): string {
  if (!iso) return "-";
  return new Date(iso).toLocaleString("ko-KR");
}

export default function RecruiterCriteriaPage() {
  const router = useRouter();
  const [accessToken] = useState<string | null>(() => readAccessToken());

  const [user, setUser] = useState<UserOut | null>(null);
  const [authLoading, setAuthLoading] = useState(true);

  const [saved, setSaved] = useState<ScreeningCriteriaOut | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [text, setText] = useState("");
  const [threshold, setThreshold] = useState(String(THRESHOLD_DEFAULT));
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

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

  function applySaved(c: ScreeningCriteriaOut) {
    setSaved(c);
    setText(c.criteria_text);
    setThreshold(String(c.version === 0 ? THRESHOLD_DEFAULT : c.pass_threshold));
  }

  useEffect(() => {
    if (!accessToken || !user || user.role !== "recruiter") return;
    getScreeningCriteria(accessToken)
      .then(applySaved)
      .catch((err: unknown) => {
        setLoadError(err instanceof ApiError ? err.message : "네트워크 오류로 면접기준을 가져오지 못했어요.");
      });
  }, [accessToken, user]);

  const registered = !!saved && saved.version > 0;
  const validation = validateCriteriaInput({ text, threshold });
  const dirty = saved
    ? isDirty({ text: saved.criteria_text, threshold: registered ? saved.pass_threshold : THRESHOLD_DEFAULT }, { text, threshold })
    : false;
  const saveDisabled = saving || !saved || !text.trim() || !dirty || !validation.ok;

  async function handleSave() {
    if (!accessToken || saveDisabled) return;
    const v = validateCriteriaInput({ text, threshold });
    if (!v.ok) {
      setSaveError(v.error ?? "입력값을 확인해 주세요.");
      return;
    }
    setSaving(true);
    setSaveError(null);
    setSuccessMessage(null);
    try {
      const updated = await saveScreeningCriteria(accessToken, {
        criteria_text: text.trim(),
        pass_threshold: Number(threshold),
      });
      applySaved(updated);
      setSuccessMessage(`저장했어요. 기준 버전 v${updated.version}으로 이력서를 다시 분석합니다.`);
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : "저장 중 오류가 발생했습니다.");
    } finally {
      setSaving(false);
    }
  }

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
          <p style={{ color: "var(--color-text-secondary)" }}>면접기준은 채용담당자 계정으로만 볼 수 있어요.</p>
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
        <h1 style={{ margin: 0 }}>면접기준</h1>
      </div>
      <p className={styles.subtitle}>
        이 기준으로 AI가 제출된 이력서를 분석해 합격/불합격을 판단합니다. 기준을 수정하면 제출된 모든 이력서가 다시 분석됩니다.
        <br />
        {AI_ADVISORY_NOTICE}
      </p>

      {loadError && (
        <div className="banner-error" role="alert" style={{ marginBottom: 16 }}>
          {loadError}
        </div>
      )}

      {!saved && !loadError ? (
        <div className={styles.skeleton} aria-busy="true">
          면접기준을 불러오는 중이에요...
        </div>
      ) : saved ? (
        <>
          <p style={{ fontSize: 13, color: "var(--color-text-secondary)" }}>
            {registered
              ? `현재 기준 v${saved.version} · 마지막 수정 ${formatDateTime(saved.updated_at)} ${saved.updated_by_name ?? ""}`.trim()
              : "아직 등록된 면접기준이 없어요."}
          </p>

          {saveError && (
            <div className="banner-error" role="alert" style={{ marginBottom: 16 }}>
              {saveError}
            </div>
          )}
          {successMessage && (
            <div className="banner-info" role="status">
              {successMessage}
            </div>
          )}

          <label className={styles.formLabel} htmlFor="criteria-text">
            면접기준
            <textarea
              id="criteria-text"
              className={styles.textarea}
              rows={14}
              maxLength={CRITERIA_MAX_LENGTH}
              value={text}
              placeholder={PLACEHOLDER}
              onChange={(e) => setText(e.target.value)}
            />
            <div className={styles.charCounter} aria-live="off">
              {text.length} / {CRITERIA_MAX_LENGTH}
            </div>
          </label>

          <label className={styles.formLabel} htmlFor="criteria-threshold">
            AI 합격선(점)
            <input
              id="criteria-threshold"
              type="number"
              className={styles.formInputSmall}
              min={1}
              max={100}
              step={1}
              value={threshold}
              onChange={(e) => setThreshold(e.target.value)}
            />
          </label>

          {text.trim() && !validation.ok && dirty && <div className="field-error">{validation.error}</div>}

          <button type="button" className="submit-button" disabled={saveDisabled} onClick={handleSave}>
            {saving ? "저장 중..." : registered ? "수정" : "등록"}
          </button>
        </>
      ) : null}
    </div>
  );
}
