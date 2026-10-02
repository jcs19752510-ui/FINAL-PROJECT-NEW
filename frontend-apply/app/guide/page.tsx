"use client";

/**
 * [신규] 이력서 제출 절차 안내 — 2026-09-30(사용자 지시): 기존에 별도 외부
 * Claude Artifact(https://claude.ai/artifact/9WauvNaQgxA57HLeNfH925)로만
 * 제공되던 "이력서 제출부터 모의면접까지" 절차 설명을 실제 앱 화면으로
 * 옮겼다 — 로그인 이후 탭 메뉴("제출 절차 안내")로 확인 가능. 원본은
 * mermaid 다이어그램이었으나 이 앱에는 차트 라이브러리가 없어(불필요한
 * 의존성 추가 대신) 기존 스타일 그대로 번호 단계 카드로 표현했다. 합격/
 * 불합격 안내 메일이 "관리자가 직접 발송"이라던 원본 문구는 DEC-116(자동
 * 발송 전환) 이후 내용이 달라져 이 화면에서는 실제 동작(자동 발송, 실패
 * 시에만 관리자가 직접 보냄)에 맞게 고쳐 썼다.
 */
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, type UserOut, clearAccessToken, getMe, readAccessToken } from "@/lib/api";
import HomeLink from "@/components/HomeLink";
import ApplyTabs from "@/components/ApplyTabs";

const STEPS = [
  { title: "회원가입", desc: "채용 지원 사이트에서 이메일과 비밀번호로 가입해요." },
  { title: "이력서 올리기", desc: "이력서 PDF 파일을 선택해서 제출해요. 작성이 막막하면 샘플 양식을 내려받아 참고할 수 있어요." },
  { title: "결과 기다리기", desc: "채용담당자가 서류를 심사하는 동안 기다려요. 화면에는 '심사 중'이라고 표시돼요." },
  { title: "메일 확인하기", desc: "합격인지 불합격인지 이메일로 바로 알려드려요. 합격하면 면접 일정 안내도 함께 와요." },
  { title: "모의면접 사이트 로그인", desc: "이력서 낼 때 썼던 계정 그대로, 이번엔 모의면접 사이트에 로그인해요." },
  { title: "AI 모의면접 보기", desc: "합격이 확인되면 '새 면접 시작' 버튼이 나타나요. 눌러서 AI 면접관과 연습해요." },
] as const;

export default function ApplyGuidePage() {
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

  return (
    <div className="auth-page">
      <div className="auth-card" style={{ maxWidth: 560 }}>
        <HomeLink />
        <ApplyTabs />
        <h1>이력서 제출부터 모의면접까지</h1>
        <p style={{ color: "var(--color-text-secondary)", marginTop: -12, marginBottom: 20 }}>
          회원가입부터 AI 모의면접 시작까지, 전체 절차를 순서대로 정리했어요.
        </p>

        <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 20 }}>
          {STEPS.map((step, i) => (
            <div key={step.title} className="guide-step">
              <div className="guide-step__num">{i + 1}</div>
              <div className="guide-step__txt">
                <b>{step.title}</b>
                <span>{step.desc}</span>
              </div>
            </div>
          ))}
        </div>

        <div className="guide-note">
          💡 <strong>참고</strong>: 합격·불합격 안내 메일은 판단 결과가 저장되는 즉시 시스템이 자동으로 보내드려요. 혹시 메일이 도착하지 않으면 채용담당자가 화면에서 확인한 뒤 직접 보내드릴 수도 있어요.
        </div>
      </div>
    </div>
  );
}
