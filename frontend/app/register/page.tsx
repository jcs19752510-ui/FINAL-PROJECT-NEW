"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import Link from "next/link";
import { ApiError, registerUser, type UserRole } from "@/lib/api";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function RegisterPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<UserRole>("candidate");
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
      await registerUser({ email, password, name: name.trim(), role });
      router.push("/login?registered=1");
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          setFieldErrors({ email: "이미 가입된 이메일입니다." });
        } else if (err.status === 422) {
          setFieldErrors({ form: err.message });
        } else {
          setBannerError(err.message);
        }
      } else {
        setBannerError("네트워크 오류가 발생했습니다. 잠시 후 다시 시도해주세요.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1>회원가입</h1>
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
            {emailInvalid && <div className="field-error">올바른 이메일 형식이 아닙니다.</div>}
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
            {passwordInvalid && <div className="field-error">비밀번호는 8자 이상이어야 합니다.</div>}
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
            {passwordMismatch && <div className="field-error">비밀번호가 일치하지 않습니다.</div>}
          </div>

          <div className="field">
            <label htmlFor="name">이름</label>
            <input id="name" type="text" value={name} onChange={(e) => setName(e.target.value)} required />
          </div>

          <div className="role-group" role="radiogroup" aria-label="역할 선택">
            <label>
              <input
                type="radio"
                name="role"
                value="candidate"
                checked={role === "candidate"}
                onChange={() => setRole("candidate")}
              />
              지원자
            </label>
            <label>
              <input
                type="radio"
                name="role"
                value="recruiter"
                checked={role === "recruiter"}
                onChange={() => setRole("recruiter")}
              />
              채용담당자
            </label>
          </div>

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
            {submitting ? "가입 처리 중..." : "회원가입"}
          </button>
        </form>

        <div className="auth-footer">
          이미 계정이 있으신가요? <Link href="/login">로그인</Link>
        </div>
      </div>
    </div>
  );
}
