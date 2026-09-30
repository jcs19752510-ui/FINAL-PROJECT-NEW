"use client";

/**
 * [신규] 채용담당자용 제출 절차 안내 — 2026-09-30(사용자 지시): 기존에 별도
 * 외부 Claude Artifact(https://claude.ai/artifact/9WauvNaQgxA57HLeNfH925)로만
 * 제공되던 절차 설명을 실제 앱 화면으로 옮겼다 — 로그인 이후 채용 관리
 * 메뉴("제출 절차 안내")로 확인 가능. 원본 mermaid 다이어그램은 차트
 * 라이브러리 추가 없이 기존 스타일 그대로 번호 단계 카드로 표현했다.
 * "채용담당자가 직접 메일 발송"이라던 원본 문구는 DEC-116(자동 발송 전환)
 * 이후 실제 동작에 맞게 고쳐 썼다.
 */
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, type UserOut, clearAccessToken, getMe, readAccessToken } from "@/lib/api";
import HomeLink from "@/components/HomeLink";
import RecruiterListTabs from "@/components/RecruiterListTabs";
import styles from "../recruiter.module.css";

const CANDIDATE_STEPS = [
  { title: "회원가입", desc: "지원자가 채용 지원 사이트(3002번 포트)에서 이메일·비밀번호로 가입해요." },
  { title: "이력서 제출", desc: "이력서 PDF를 올려요. 이 계정은 나중에 모의면접 사이트에서도 그대로 쓰여요." },
  { title: "서류 심사(채용담당자)", desc: "여기(이력서 검토 화면)에서 이력서를 열람하고 합격/불합격을 정해요." },
  { title: "안내 메일 자동 발송", desc: "합격/불합격을 저장하면 시스템이 즉시 지원자에게 안내 메일을 보내요. 실패하면 이 화면에서 직접 보낼 수 있는 대체 수단도 남아있어요." },
  { title: "지원자 모의면접 진행", desc: "합격한 지원자는 같은 계정으로 모의면접 사이트에 로그인해 AI 면접관과 면접을 봐요." },
] as const;

export default function RecruiterProcessGuidePage() {
  const router = useRouter();
  const [accessToken] = useState<string | null>(() => readAccessToken());
  const [user, setUser] = useState<UserOut | null>(null);
  const [authLoading, setAuthLoading] = useState(true);

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
          <p style={{ color: "var(--color-text-secondary)" }}>이 화면은 채용담당자 계정으로만 볼 수 있어요.</p>
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
        <h1 style={{ margin: 0 }}>이력서 제출부터 모의면접까지</h1>
      </div>
      <p className={styles.subtitle}>지원자가 이력서를 내고 모의면접을 시작하기까지, 채용담당자가 관여하는 지점을 순서대로 정리했어요.</p>

      <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 20, maxWidth: 640 }}>
        {CANDIDATE_STEPS.map((step, i) => (
          <div key={step.title} className="guide-step">
            <div className="guide-step__num">{i + 1}</div>
            <div className="guide-step__txt">
              <b>{step.title}</b>
              <span>{step.desc}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="guide-note" style={{ maxWidth: 640, marginBottom: 20 }}>
        💡 <strong>참고</strong>: 이력서 검토·합격/불합격 결정은{" "}
        <Link href="/recruiter/resumes">이력서 검토</Link> 메뉴에서 진행해요.
      </div>

      <div>
        <Link href="/recruiter">채용 관리 홈으로 돌아가기</Link>
      </div>
    </div>
  );
}
