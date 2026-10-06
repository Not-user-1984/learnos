import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "LearnOS — база знаний",
  description: "Персональная система обучения с ИИ: блоки знаний рождаются через сессии",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru" className="h-full antialiased">
      <body className="min-h-full bg-zinc-950 text-zinc-100">{children}</body>
    </html>
  );
}
