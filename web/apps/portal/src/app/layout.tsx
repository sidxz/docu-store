import type { Metadata } from "next";
import type { ReactNode } from "react";

import { Providers } from "@/components/providers/Providers";

import "./globals.css";

export const metadata: Metadata = {
  title: "DAIKON DocuStore",
  description: "Document intelligence for drug discovery",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
