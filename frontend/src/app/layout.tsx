import type { Metadata } from "next";
import "highlight.js/styles/github-dark.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "NexuX｜多模態知識平台",
  description:
    "專屬且安全的多模態 AI 知識工作區，協助你探索文件、整理脈絡並發掘洞見。",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-Hant">
      <body>{children}</body>
    </html>
  );
}
