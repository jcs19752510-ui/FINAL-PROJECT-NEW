"use client";

/**
 * Google 로그인 결과 페이지 — 백엔드 콜백이 `/login/google?status=ok` 또는 `?error=<코드>` 로 돌려보낸다.
 * 성공이면 기존 `/auth/refresh`(리프레시 쿠키)로 액세스 토큰을 받아 기존 로그인과 같은 방식으로
 * 저장하고 `/resume` 으로 이동한다. 토큰은 URL에 실리지 않는다.
 */
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { refreshAccessToken, storeAccessToken } from "@/lib/api";
import HomeLink from "@/components/HomeLink";

const ERROR_MESSAGES: Record<string, string> = {
  cancelled: "Google 로그인이 취소되었어요.",
  email_exists: "이미 가입된 이메일이에요. 이메일/비밀번호로 로그인해주세요.",
  email_unverified: "인증되지 않은 Google 이메일이에요. Google 계정의 이메일 인증을 확인해주세요.",
  account_disabled: "사용할 수 없는 계정이에요. 문의가 필요하면 담당자에게 연락해주세요.",
  rate_limited: "요청이 너무 많아요. 잠시 후 다시 시도해주세요.",
  unavailable: "Google 로그인을 지금은 사용할 수 없어요. 잠시 후 다시 시도해주세요.",
  invalid_state: "로그인 요청이 만료되었어요. 처음부터 다시 시도해주세요.",
};
const DEFAULT_ERROR = "Google 로그인에 실패했어요. 잠시 후 다시 시도해주세요.";

export default function GoogleLoginResultPage() {
  return (
    <Suspense fallback={null}>
      <GoogleLoginResult />
    </Suspense>
  );
}

function GoogleLoginResult() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const errorCode = searchParams.get("error");
  const ok = searchParams.get("status") === "ok";
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!ok || errorCode) return;
    let cancelled = false;
    refreshAccessToken()
      .then((res) => {
        if (cancelled) return;
        storeAccessToken(res.access_token);
        router.replace("/resume");
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [ok, errorCode, router]);

  const message = errorCode ? (ERROR_MESSAGES[errorCode] ?? DEFAULT_ERROR) : failed || !ok ? DEFAULT_ERROR : null;

  return (
    <div className="auth-page">
      <div className="auth-card">
        <HomeLink />
        <h1>Google 로그인</h1>
        {message ? (
          <>
            <div className="banner-error">{message}</div>
            <div className="auth-footer">
              <Link href="/login">로그인 화면으로 돌아가기</Link>
            </div>
          </>
        ) : (
          <div style={{ color: "var(--color-text-secondary)", fontSize: 14 }}>로그인 처리 중이에요...</div>
        )}
      </div>
    </div>
  );
}
