import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI 모의면접 — 채용 지원",
  description: "이력서 제출하고 서류 심사 결과 확인하기",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
