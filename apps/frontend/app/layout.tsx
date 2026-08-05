import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "The Playbook",
  description: "AI-powered sports betting operating system",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
