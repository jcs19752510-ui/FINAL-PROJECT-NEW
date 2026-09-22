/** @type {import('next').NextConfig} */
const nextConfig = {
  // 사용자 요청(2026-09-22): 개발 모드 전용 "N" 디버그 표시(하이드레이션 경고 등)를
  // 화면에서 숨김. 프로덕션 빌드에는 원래도 나오지 않던 개발자용 오버레이라
  // 기능/데이터에는 영향이 없다.
  devIndicators: false,
};

export default nextConfig;
