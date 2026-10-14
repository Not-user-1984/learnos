import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { ThemeProvider } from "next-themes";
import { Toaster } from "@/components/ui/sonner";
import { AppShell } from "@/components/app-shell";
import { SwRegister } from "@/components/sw-register";
import "./globals.css";

// Inter/JetBrains Mono вместо Geist: у Geist нет кириллицы, интерфейс русский
const sans = Inter({ variable: "--font-sans", subsets: ["latin", "cyrillic"] });
const mono = JetBrains_Mono({ variable: "--font-geist-mono", subsets: ["latin", "cyrillic"] });

export const metadata: Metadata = {
  title: "LearnOS — персональная система обучения",
  description: "Ресёрч → сессии с агентом → база знаний: блоки рождаются через диалог",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru" className={`${sans.variable} ${mono.variable}`} suppressHydrationWarning>
      <body className="min-h-dvh bg-background font-sans text-foreground antialiased">
        <ThemeProvider attribute="class" defaultTheme="dark" enableSystem={false}>
          <AppShell>{children}</AppShell>
          <Toaster richColors position="bottom-right" />
          <SwRegister />
        </ThemeProvider>
      </body>
    </html>
  );
}
