"use client";

/**
 * "새 면접 시작" 진입점 (unit-15). 04-ux-design.md §1.1 [C-03]→[C-04] 플로우의
 * "POST /interviews로 세션 생성 → 사전고지·동의 화면으로 이동" 단계를 담당한다.
 *
 * 지원자 홈([C-03], `app/page.tsx`)은 아직 다른 유닛이 만들지 않아 "새 면접 시작"
 * CTA 자체가 없다 — 이 페이지는 그 CTA 없이도 사전고지 화면을 end-to-end로
 * 테스트할 수 있도록 하는 독립적인 신규 진입 경로다(unit-15-note.md §2 편차 참고).
 * `app/page.tsx`는 다른 유닛 소유일 수 있어 수정하지 않았다.
 */
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, createInterview, readAccessToken } from "@/lib/api";

export default function NewInterviewPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = readAccessToken();
    if (!token) {
      router.push("/login");
      return;
    }

    let cancelled = false;
    createInterview(token)
      .then((interview) => {
        if (cancelled) return;
        router.replace(`/interviews/${interview.id}/consent`);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError) {
          if (err.status === 401) {
            router.push("/login");
            return;
          }
          setError(err.message);
        } else {
          setError("네트워크 오류로 면접 세션을 생성하지 못했습니다.");
        }
      });

    return () => {
      cancelled = true;
    };
  }, [router]);

  return (
    <div className="auth-page">
      <div className="auth-card">
        {error ? (
          <>
            <div className="banner-error">{error}</div>
            <a href="/">홈으로 돌아가기</a>
          </>
        ) : (
          "새 면접 세션을 만드는 중입니다..."
        )}
      </div>
    </div>
  );
}
