"use client";

import { trackEvent } from "@/lib/analytics";

export function useAnalytics() {
  return { trackEvent };
}
