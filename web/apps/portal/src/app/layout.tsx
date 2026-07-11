import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans, Inter } from "next/font/google";
import type { ReactNode } from "react";

import { Providers } from "@/components/providers/Providers";

import "./globals.css";

const plexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  variable: "--font-plex-sans",
  weight: ["400", "500", "600", "700"],
  display: "swap",
});
const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  variable: "--font-plex-mono",
  weight: ["400", "500", "600"],
  display: "swap",
});
const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "DAIKON DocuStore",
  description: "Document intelligence for drug discovery",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html
      lang="en"
      className={`${plexSans.variable} ${plexMono.variable} ${inter.variable}`}
      suppressHydrationWarning
    >
      <head>
        {/* Inline script prevents flash of wrong theme/font on load */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=JSON.parse(localStorage.getItem('ds-theme')||'{}');var v=t.state&&t.state.theme;if(!v){v=matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light'}document.documentElement.setAttribute('data-theme',v)}catch(e){}try{var f=JSON.parse(localStorage.getItem('ds-font-scale')||'{}');var s=f.state&&f.state.scale;if(s){document.documentElement.style.fontSize=s+'%'}}catch(e){}try{var g=JSON.parse(localStorage.getItem('ds-font')||'{}');document.documentElement.setAttribute('data-font',(g.state&&g.state.font)||'plex')}catch(e){document.documentElement.setAttribute('data-font','plex')}})()`,
          }}
        />
      </head>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
