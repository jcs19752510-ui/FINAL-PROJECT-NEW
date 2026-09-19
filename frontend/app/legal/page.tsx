"use client";

/**
 * [C-14] 법률/컴플라이언스 고지 화면 (unit-15, REQ-034, 04-ux-design.md §2 [C-14]).
 *
 * 규칙 I-4 — 이 서비스가 법적 판단을 대신하지 않는다는 점을 명확히 고지한다.
 * 03-system-design.md는 `GET /legal/disclaimer`를 정의했지만 어떤 유닛도 아직
 * 구현하지 않았고, 이번 유닛은 신규 백엔드 엔드포인트를 만들지 않기로 범위가
 * 한정되어(오케스트레이터 지시) 고정 법정 고지문이라는 성격에 맞게 정적 페이지로
 * 구현했다(unit-15-note.md §2 편차 참고). 로그인 여부와 무관하게 항상 열람 가능하다.
 */
import Link from "next/link";
import { LEGAL_DISCLAIMER_TEXT } from "@/lib/complianceContent";
import styles from "./legal.module.css";

export default function LegalDisclaimerPage() {
  return (
    <div className={styles.page}>
      <h1>법률/컴플라이언스 고지</h1>
      <div className={styles.body}>{LEGAL_DISCLAIMER_TEXT}</div>
      <Link href="/" className={styles.back}>
        홈으로 돌아가기
      </Link>
    </div>
  );
}
