"use client";

import { useEffect } from "react";
import { trackEvent } from "@/lib/analytics";

/**
 * Reports Core Web Vitals (CLS, FCP, LCP, TTFB) as Umami custom events.
 * Uses the web-vitals library. Call once in root layout.
 */
export function useWebVitals() {
  useEffect(() => {
    import("web-vitals").then(({ onCLS, onFCP, onLCP, onTTFB }) => {
      const report = (metric: { name: string; value: number; rating: string }) => {
        trackEvent("web_vital", {
          metric: metric.name,
          value: Math.round(metric.value),
          rating: metric.rating,
        });
      };

      onCLS(report);
      onFCP(report);
      onLCP(report);
      onTTFB(report);
    });
  }, []);
}
