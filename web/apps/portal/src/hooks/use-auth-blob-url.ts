"use client";

import { useEffect, useState } from "react";
import { getAuthzClient } from "@/lib/authz-client";

/**
 * Fetches a URL with auth headers and returns an object URL for use in
 * <iframe src> / <img src> where the browser can't attach custom headers.
 */
export function useAuthBlobUrl(url: string) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    setBlobUrl(null);
    setError(false);
    if (!url) return;
    const controller = new AbortController();
    let revoke: string | null = null;
    const headers = getAuthzClient().getHeaders();

    fetch(url, { headers, signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error(res.statusText);
        return res.blob();
      })
      .then((blob) => {
        if (controller.signal.aborted) return;
        revoke = URL.createObjectURL(blob);
        setBlobUrl(revoke);
      })
      .catch((err) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setError(true);
      });

    return () => {
      controller.abort();
      if (revoke) URL.revokeObjectURL(revoke);
    };
  }, [url]);

  return { blobUrl, error };
}
