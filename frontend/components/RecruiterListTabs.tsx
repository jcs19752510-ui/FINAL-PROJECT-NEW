"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/recruiter", label: "지원자 리포트" },
  { href: "/recruiter/resumes", label: "이력서 검토" },
  { href: "/recruiter/process-guide", label: "제출 절차 안내" },
  { href: "/recruiter/add-recruiter", label: "채용담당자 추가" },
] as const;

export default function RecruiterListTabs() {
  const pathname = usePathname();

  return (
    <nav className="interview-room__tabs" aria-label="채용 관리 메뉴" style={{ marginBottom: 20 }}>
      {TABS.map((tab) => {
        const active = tab.href === "/recruiter" ? pathname === "/recruiter" : pathname.startsWith(tab.href);
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
