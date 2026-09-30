"use client";

/**
 * [보안 강화] 채용담당자 추가 — 2026-09-30 사용자 지시.
 * 기존 공개 회원가입(`/register`, 3001)은 완전히 제거했다 — 그 화면이 인증 없이
 * 누구나 role=recruiter로 가입해 모든 지원자 이력서·개인정보에 접근할 수 있는
 * 실제 보안 구멍이었기 때문이다(RegisterRequest.role이 이제 candidate만 허용,
 * backend/app/schemas/user.py). 새 채용담당자 계정은 오직 "이미 로그인한
 * 채용담당자"만, 이 화면(로그인 필수 + recruiter 역할 확인)에서 만들 수 있다.
 */
import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { ApiError, type UserOut, clearAccessToken, createRecruiter, getMe, readAccessToken } from "@/lib/api";
import HomeLink from "@/components/HomeLink";
import RecruiterListTabs from "@/components/RecruiterListTabs";
import styles from "../recruiter.module.css";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function AddRecruiterPage() {
  const router = useRouter();
  const [accessToken] = useState<string | null>(() => readAccessToken());

  const [user, setUser] = useState<UserOut | null>(null);
  const [authLoading, setAuthLoading] = useState(true);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [name, setName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [bannerError, setBannerError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [successEmail, setSuccessEmail] = useState<string | null>(null);

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

  const emailInvalid = email.length > 0 && !EMAIL_PATTERN.test(email);
  const passwordInvalid = password.length > 0 && password.length < 8;
  const passwordMismatch = passwordConfirm.length > 0 && password !== passwordConfirm;

  const canSubmit =
    email.length > 0 &&
    !emailInvalid &&
    password.length >= 8 &&
    !passwordMismatch &&
    name.trim().length > 0 &&
    !submitting;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit || !accessToken) return;

    setSubmitting(true);
    setBannerError(null);
    setFieldErrors({});
    setSuccessEmail(null);

    try {
      const created = await createRecruiter(accessToken, { email, password, name: name.trim() });
      setSuccessEmail(created.email);
      setEmail("");
      setPassword("");
      setPasswordConfirm("");
      setName("");
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          setFieldErrors({ email: "이미 가입된 이메일입니다." });
        } else if (err.status === 422) {
          setFieldErrors({ form: err.message });
        } else if (err.status === 403) {
          setBannerError("채용담당자 계정만 새 채용담당자를 추가할 수 있습니다.");
        } else {
          setBannerError(err.message);
        }
      } else {
        setBannerError("네트워크 오류예요. 잠시 후 다시 시도해주세요.");
      }
    } finally {
      setSubmitting(false);
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
          <a href="/login" className="submit-button" style={{ textAlign: "center", textDecoration: "none" }}>
            로그인하러 가기
          </a>
        </div>
      </div>
    );
  }

  if (user.role !== "recruiter") {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h1>권한이 없습니다</h1>
          <p style={{ color: "var(--color-text-secondary)" }}>채용담당자 추가는 채용담당자 계정으로만 할 수 있어요.</p>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <HomeLink />
      <RecruiterListTabs />
      <div className={styles.detailHeader}>
        <h1 style={{ margin: 0 }}>채용담당자 추가</h1>
      </div>
      <p className={styles.subtitle}>새 채용담당자 계정의 이메일/비밀번호/이름을 등록해주세요.</p>

      {bannerError && (
        <div className="banner-error" role="alert" style={{ marginBottom: 16 }}>
          {bannerError}
        </div>
      )}
      {successEmail && (
        <div className="banner-info" role="status" style={{ marginBottom: 16 }}>
          {successEmail} 계정을 채용담당자로 추가했어요.
        </div>
      )}

      <form onSubmit={handleSubmit} noValidate style={{ maxWidth: 480 }}>
        <div className="field">
          <label htmlFor="email">이메일</label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="off"
            required
          />
          {emailInvalid && <div className="field-error">이메일 형식을 다시 확인해주세요.</div>}
          {fieldErrors.email && <div className="field-error">{fieldErrors.email}</div>}
        </div>

        <div className="field">
          <label htmlFor="password">비밀번호</label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
            required
          />
          {passwordInvalid && <div className="field-error">비밀번호는 8자 이상으로 입력해주세요.</div>}
        </div>

        <div className="field">
          <label htmlFor="passwordConfirm">비밀번호 확인</label>
          <input
            id="passwordConfirm"
            type="password"
            value={passwordConfirm}
            onChange={(e) => setPasswordConfirm(e.target.value)}
            autoComplete="new-password"
            required
          />
          {passwordMismatch && <div className="field-error">비밀번호가 서로 달라요.</div>}
        </div>

        <div className="field">
          <label htmlFor="name">이름</label>
          <input id="name" type="text" value={name} onChange={(e) => setName(e.target.value)} required />
        </div>

        {fieldErrors.form && <div className="field-error">{fieldErrors.form}</div>}

        <button type="submit" className="submit-button" disabled={!canSubmit}>
          {submitting ? "추가하는 중..." : "채용담당자 추가"}
        </button>
      </form>
    </div>
  );
}
