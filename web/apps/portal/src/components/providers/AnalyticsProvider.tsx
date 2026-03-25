"use client";

import Script from "next/script";
import { useCallback, useEffect, useState } from "react";

import { useSession } from "@/lib/auth";
import { useSectionTimer } from "@/hooks/use-section-timer";
import { useWebVitals } from "@/lib/web-vitals";

const UMAMI_URL = process.env.NEXT_PUBLIC_UMAMI_URL;
const UMAMI_WEBSITE_ID = process.env.NEXT_PUBLIC_UMAMI_WEBSITE_ID;

/**
 * Client component that activates analytics hooks and loads the Umami tracker.
 * Mount once inside the workspace layout.
 */
export function AnalyticsProvider() {
  const { user, workspace, isAuthenticated } = useSession();
  const [scriptReady, setScriptReady] = useState(false);

  const handleReady = useCallback(() => setScriptReady(true), []);

  useEffect(() => {
    if (!scriptReady || !isAuthenticated || !user.id || !window.umami) return;
    window.umami.identify(user.id, { workspace_id: workspace.id });
  }, [scriptReady, isAuthenticated, user.id, workspace.id]);

  useSectionTimer();
  useWebVitals();

  if (!UMAMI_WEBSITE_ID) return null;

  return (
    <Script
      src={`${UMAMI_URL}/ds-analytics`}
      data-website-id={UMAMI_WEBSITE_ID}
      strategy="afterInteractive"
      onReady={handleReady}
    />
  );
}
