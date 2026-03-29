"use client";

import Script from "next/script";
import { useCallback, useEffect, useState } from "react";

import { useSession } from "@/lib/auth";
import { useSectionTimer } from "@/hooks/use-section-timer";
import { useWebVitals } from "@/lib/web-vitals";
import { useAppConfig } from "@/lib/app-config";

/**
 * Client component that activates analytics hooks and loads the Umami tracker.
 * Mount once inside the workspace layout.
 */
export function AnalyticsProvider() {
  const { umamiUrl, umamiWebsiteId } = useAppConfig();
  const { user, workspace, isAuthenticated } = useSession();
  const [scriptReady, setScriptReady] = useState(false);

  const handleReady = useCallback(() => setScriptReady(true), []);

  useEffect(() => {
    if (!scriptReady || !isAuthenticated || !user.id || !window.umami) return;
    window.umami.identify(user.id, { workspace_id: workspace.id });
  }, [scriptReady, isAuthenticated, user.id, workspace.id]);

  useSectionTimer();
  useWebVitals();

  if (!umamiWebsiteId) return null;

  return (
    <Script
      src={`${umamiUrl}/ds-analytics`}
      data-website-id={umamiWebsiteId}
      strategy="afterInteractive"
      onReady={handleReady}
    />
  );
}
