import type { Metadata } from "next";
import type { ReactNode } from "react";

import { QueryProvider } from "@/lib/query";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Competitor Scout",
    template: "%s | Competitor Scout",
  },
  description: "Evidence-backed competitor intelligence for B2B SaaS teams.",
};

type RootLayoutProps = Readonly<{
  children: ReactNode;
}>;

export default function RootLayout({ children }: RootLayoutProps) {
  return (
    <html lang="en">
      <body>
        <QueryProvider>{children}</QueryProvider>
      </body>
    </html>
  );
}
