"use client";

import { useEffect, useState } from "react";
import Uppy from "@uppy/core";
import XHRUpload from "@uppy/xhr-upload";
import { API_URL } from "@/lib/constants";
import { getAuthzClient } from "@/lib/authz-client";

const UPLOAD_CONCURRENCY = 4;

/** Single source of truth for the upload accept/size policy — the dropzone and
 *  the page's folder-pick filter both derive from these. */
export const ACCEPT: Record<string, string[]> = {
  "application/pdf": [".pdf"],
  "application/vnd.openxmlformats-officedocument.presentationml.presentation": [".pptx"],
  "application/vnd.ms-powerpoint": [".ppt"],
  "application/msword": [".doc"],
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
};
export const MAX_FILE_SIZE = 100_000_000;
export const ALLOWED_EXTENSIONS = Object.values(ACCEPT).flat();

/** Uppy engine for document uploads — headless (no Dashboard). The page renders
 *  the UI from `uppy` state via @uppy/react hooks; `addFiles` ingests the
 *  File[] that react-dropzone hands us (already accept/size-filtered). */
export function useDocumentUploader() {
  const [uppy] = useState(() =>
    new Uppy({
      autoProceed: false,
      restrictions: {
        maxFileSize: MAX_FILE_SIZE,
        allowedFileTypes: ALLOWED_EXTENSIONS,
      },
    }).use(XHRUpload, {
      endpoint: `${API_URL}/artifacts/upload`,
      method: "POST",
      fieldName: "file",
      formData: true,
      limit: UPLOAD_CONCURRENCY,
      timeout: 120_000,
      allowedMetaFields: ["artifact_type", "visibility", "source_uri"],
      headers: () => getAuthzClient().getHeaders(),
      // 4xx is deterministic — retrying it 3x just delays the error. Only retry
      // network failures (status 0) and 5xx.
      shouldRetry: (xhr) => xhr.status === 0 || xhr.status >= 500,
      // Surface the FastAPI error `detail` instead of Uppy's generic
      // "looks like a network error" copy — the thrown Error becomes file.error.
      onAfterResponse: (xhr) => {
        if (xhr.status >= 400) {
          let detail: unknown;
          try {
            detail = (JSON.parse(xhr.responseText) as { detail?: unknown }).detail;
          } catch {
            // non-JSON body — fall through to the generic message
          }
          throw new Error(typeof detail === "string" ? detail : `Upload failed (${xhr.status})`);
        }
      },
    }),
  );

  // Abort in-flight XHRs when the page unmounts — otherwise navigation
  // mid-batch leaves headless uploads running while the remount shows an
  // empty queue (user re-adds → duplicate artifacts).
  // ponytail: cancelAll, not destroy() — destroy breaks React StrictMode's
  // dev double-mount (state survives, instance wouldn't); the instance is
  // unreachable after unmount anyway.
  useEffect(() => () => {
    uppy.cancelAll();
  }, [uppy]);

  const addFiles = (files: File[]) => {
    for (const file of files) {
      try {
        uppy.addFile({
          name: file.name,
          type: file.type,
          data: file,
          // Folder picks set the standard `webkitRelativePath`; react-dropzone
          // sets `.path` on drag-drops. Stash it for display + dedup across
          // same-named files in subfolders.
          meta: {
            relativePath:
              file.webkitRelativePath || (file as File & { path?: string }).path || file.name,
          },
        });
      } catch {
        // Duplicate / restriction — the page counts these via 'restriction-failed'.
      }
    }
  };

  return { uppy, addFiles };
}
