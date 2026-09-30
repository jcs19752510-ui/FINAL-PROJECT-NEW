"use client";

/**
 * [Feature J] 채용 지원 회원가입 — 모의면접 앱의 회원가입 화면과 동일한 UX,
 * 같은 `POST /auth/register`를 재사용한다(role은 candidate 고정, 계정 공유).
 */
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import Link from "next/link";
import { ApiError, registerUser } from "@/lib/api";
import HomeLink from "@/components/HomeLink";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function ApplyRegisterPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [name, setName] = useState("");
  const [agreedToPolicy, setAgreedToPolicy] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [bannerError, setBannerError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const emailInvalid = email.length > 0 && !EMAIL_PATTERN.test(email);
  const passwordInvalid = password.length > 0 && password.length < 8;
  const passwordMismatch = passwordConfirm.length > 0 && password !== passwordConfirm;

  const canSubmit =
    email.length > 0 &&
    !emailInvalid &&
    password.length >= 8 &&
    !passwordMismatch &&
    name.trim().length > 0 &&
    agreedToPolicy &&
    !submitting;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;

    setSubmitting(true);
    setBannerError(null);
    setFieldErrors({});

    try {
      await registerUser({ email, password, name: name.trim(), role: "candidate" });
      router.push("/login?registered=1");
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          setFieldErrors({ email: "이미 가입한 이메일이에요." });
        } else if (err.status === 422) {
          setFieldErrors({ form: err.message });
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

  return (
    <div className="auth-page">
      <div className="auth-card">
        <HomeLink />
        <h1>채용 지원 회원가입</h1>
        {bannerError && <div className="banner-error">{bannerError}</div>}

        <form onSubmit={handleSubmit} noValidate>
          <div className="field">
            <label htmlFor="email">이메일</label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
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

          <p style={{ fontSize: 13, color: "var(--color-text-secondary)", margin: "4px 0 16px" }}>
            이 계정은 나중에 모의면접 사이트에서도 그대로 쓸 수 있어요.
          </p>

          <div className="field">
            <label style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
              <input
                type="checkbox"
                checked={agreedToPolicy}
                onChange={(e) => setAgreedToPolicy(e.target.checked)}
                required
              />
              <span>개인정보 처리방침에 동의합니다.</span>
            </label>
          </div>

          {fieldErrors.form && <div className="field-error">{fieldErrors.form}</div>}

          <button type="submit" className="submit-button" disabled={!canSubmit}>
            {submitting ? "가입하는 중..." : "회원가입"}
          </button>
        </form>

        <div className="auth-footer">
          계정이 이미 있나요? <Link href="/login">로그인</Link>
        </div>
      </div>
    </div>
  );
}
