"use client";

import "./globals.css";

import { CopilotKit } from "@copilotkit/react-core/v2";
import { Fraunces } from "next/font/google";
import { ThemeProvider } from "@/hooks/use-theme";

// One refined editorial display face for headings only — body stays on the
// existing Plus Jakarta Sans stack (see globals.css). Exposed as a CSS variable
// so it's opt-in per element via `font-[family-name:var(--font-display)]`.
const fraunces = Fraunces({
  subsets: ["latin"],
  display: "swap",
  weight: ["400", "500", "600"],
  variable: "--font-display",
});

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={fraunces.variable}>
      <head>
        <title>Socratic</title>
        <link
          rel="icon"
          type="image/svg+xml"
          href="/copilotkit-logo-mark.svg"
        />
      </head>
      <body className={`antialiased`}>
        <ThemeProvider>
          {/* Minimal CopilotKit provider: we drive the lesson via useAgent +
              useInterrupt only (no CopilotChat, no generative UI). */}
          <CopilotKit runtimeUrl="/api/copilotkit" useSingleEndpoint={false}>
            {children}
          </CopilotKit>
        </ThemeProvider>
      </body>
    </html>
  );
}
