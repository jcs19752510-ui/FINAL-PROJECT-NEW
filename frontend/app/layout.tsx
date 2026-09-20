import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI 모의면접 플랫폼",
  description: "웹 기반 AI 모의면접 플랫폼",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
