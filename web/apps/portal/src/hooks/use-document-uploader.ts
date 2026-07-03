"use client";

import { useState } from "react";
import Uppy from "@uppy/core";
import XHRUpload from "@uppy/xhr-upload";
import { API_URL } from "@/lib/constants";
import { getAuthzClient } from "@/lib/authz-client";

export const UPLOAD_CONCURRENCY = 4;
export const MAX_FILE_SIZE = 100_000_000;
export const ALLOWED_EXTENSIONS = [".pdf", ".pptx", ".ppt", ".doc", ".docx"];

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
    }),
  );

  const addFiles = (files: File[]) => {
    for (const file of files) {
      try {
        uppy.addFile({
          name: file.name,
          type: file.type,
          data: file,
          // react-dropzone sets `.path` (relative folder path) on folder drops;
          // stash it for display + dedup across same-named files in subfolders.
          meta: { relativePath: (file as File & { path?: string }).path ?? file.name },
        });
      } catch {
        // Duplicate / restriction — Uppy emits an event the UI already surfaces.
      }
    }
  };

  return { uppy, addFiles };
}
