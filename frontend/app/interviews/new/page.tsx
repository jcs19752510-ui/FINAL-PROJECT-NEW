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
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, createInterview, readAccessToken } from "@/lib/api";

export default function NewInterviewPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  // 2026-09-24 결함 수정(내부테스트 결과서 unit-15 후속, DEF-002/DEF-003).
  //
  // DEF-002(1차 수정): React(개발 모드) Strict Mode는 effect를 마운트→클린업→
  // 재마운트로 두 번 실행한다. 기존 `cancelled` 플래그는 "먼저 시작된 호출의
  // *결과 사용*"만 막을 뿐 `createInterview()` 자체의 실행은 막지 못해, 재실행마다
  // 실제 면접 세션이 하나씩 더 생성됐다("새 면접 시작"을 누를 때마다 지원자 홈
  // 목록이 1~2건씩 늘어나던 원인) — 이건 ref로 실제 호출을 1회로 제한해 해결했다.
  //
  // DEF-003(자체 회귀, 같은 날 재검증 중 발견): 위 1차 수정이 `cancelled` 클린업
  // 로직을 그대로 둔 채 ref만 추가해서 새로운 문제를 만들었다. Strict Mode 순서는
  // "1차 마운트(effect 실행) → 1차 클린업(cancelled=true) → 2차 마운트(effect
  // 실행)"인데, 실제 `createInterview()` 호출은 **1차 마운트**에서 나가고, 그
  // 클린업이 **곧바로** `cancelled=true`를 세팅해버린다. 2차 마운트는 ref 가드로
  // 아예 호출을 건너뛰므로, 결과적으로 유일하게 살아있는 요청(1차 마운트의
  // 요청)이 항상 `cancelled=true`인 채로 응답을 받아 `.then`/`.catch` 모두 조용히
  // 아무 일도 하지 않았다 — 서버에는 세션이 정상 생성되는데도(실측: 200/201
  // 응답 확인) 화면은 "새 면접 세션을 만드는 중입니다..."에서 영원히 멈춰 있었다.
  // 수정: ref가 이미 "실제 호출은 프로세스당 1회"를 보장하므로, 더 이상 별도의
  // `cancelled` 클린업이 필요 없다 — 제거하고 그 유일한 호출의 결과를 그대로 쓴다.
  const startedRef = useRef(false);

  useEffect(() => {
    const token = readAccessToken();
    if (!token) {
      router.push("/login");
      return;
    }
    if (startedRef.current) return;
    startedRef.current = true;

    createInterview(token)
      .then((interview) => {
        router.replace(`/interviews/${interview.id}/consent`);
      })
      .catch((err) => {
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
