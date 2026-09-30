"use client";

/**
 * 2026-09-30(사용자 지시) — 로그인 이후 화면에 탭 메뉴 신설, "제출 절차 안내"
 * 화면 추가. `frontend/components/RecruiterListTabs.tsx`와 동일한 패턴(같은
 * CSS 클래스, `usePathname` 기반 active 판정)을 그대로 옮겨왔다.
 */
import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/resume", label: "이력서 제출" },
  { href: "/guide", label: "제출 절차 안내" },
] as const;

export default function ApplyTabs() {
  const pathname = usePathname();

  return (
    <nav className="interview-room__tabs" aria-label="채용 지원 메뉴" style={{ marginBottom: 20 }}>
      {TABS.map((tab) => {
        const active = pathname.startsWith(tab.href);
        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={`room-tab${active ? " room-tab--active" : ""}`}
            aria-current={active ? "page" : undefined}
            style={{ textDecoration: "none" }}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
