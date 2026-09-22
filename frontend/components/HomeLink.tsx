import Link from "next/link";

// 사용자 요청(2026-09-22): 로그인 이후 화면들에서 뒤로가기를 반복해야만 홈으로
// 돌아갈 수 있었던 문제 — 정상 렌더 경로(성공 상태)에는 이 링크가 없던 화면들의
// 상단에 공통으로 배치한다(오류/미인증 상태에는 기존에도 이미 있었음).
export default function HomeLink() {
  return (
    <Link href="/" className="home-link">
      &larr; 홈으로
    </Link>
  );
}
