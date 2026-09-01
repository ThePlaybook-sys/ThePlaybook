import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

// Inter: chosen for real tabular-figure support (--text-data-* tokens
// rely on it) and because it reads as a serious data/intelligence
// product rather than a consumer-app novelty typeface — Volume 5 v5.0
// §4's "avoid AI-generated-looking UI clichés" instruction, and the
// existing performance note (no external font CDN calls at runtime).
const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "MANSA",
  description: "AI-powered sports betting operating system",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={inter.variable} data-theme="dark">
      <body>{children}</body>
    </html>
  );
}
