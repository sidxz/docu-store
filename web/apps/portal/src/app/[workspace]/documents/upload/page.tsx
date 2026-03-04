"use client";

import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "primereact/button";
import { Dropdown } from "primereact/dropdown";
import { FileUpload, type FileUploadHandlerEvent } from "primereact/fileupload";
import { InputText } from "primereact/inputtext";
import { Message } from "primereact/message";

import { useUploadArtifact } from "@/hooks/use-artifacts";

const ARTIFACT_TYPES = [
  { label: "Research Article", value: "RESEARCH_ARTICLE" },
  { label: "Scientific Document", value: "SCIENTIFIC_DOCUMENT" },
  { label: "Scientific Presentation", value: "SCIENTIFIC_PRESENTATION" },
  { label: "Generic Presentation", value: "GENERIC_PRESENTATION" },
  { label: "Disclosure Document", value: "DISCLOSURE_DOCUMENT" },
  { label: "Minutes of Meeting", value: "MINUTE_OF_MEETING" },
  { label: "Unclassified", value: "UNCLASSIFIED" },
];

export default function UploadPage() {
  const { workspace } = useParams<{ workspace: string }>();
  const router = useRouter();
  const uploadMutation = useUploadArtifact();

  const [artifactType, setArtifactType] = useState("RESEARCH_ARTICLE");
  const [sourceUri, setSourceUri] = useState("");

  const handleUpload = async (event: FileUploadHandlerEvent) => {
    const file = event.files[0];
    if (!file) return;

    try {
      await uploadMutation.mutateAsync({
        file,
        artifactType,
        sourceUri: sourceUri || undefined,
      });
      router.push(`/${workspace}/documents`);
    } catch {
      // Error is available via uploadMutation.error
    }
  };

  return (
    <div className="p-6">
      <h1 className="mb-6 text-2xl font-semibold text-gray-900">
        Upload Document
      </h1>

      <div className="max-w-xl space-y-6">
        <div>
          <label className="mb-2 block text-sm font-medium text-gray-700">
            Document Type
          </label>
          <Dropdown
            value={artifactType}
            options={ARTIFACT_TYPES}
            onChange={(e) => setArtifactType(e.value)}
            className="w-full"
          />
        </div>

        <div>
          <label className="mb-2 block text-sm font-medium text-gray-700">
            Source URI (optional)
          </label>
          <InputText
            value={sourceUri}
            onChange={(e) => setSourceUri(e.target.value)}
            placeholder="https://..."
            className="w-full"
          />
        </div>

        <div>
          <label className="mb-2 block text-sm font-medium text-gray-700">
            File
          </label>
          <FileUpload
            name="file"
            accept=".pdf,.pptx,.ppt,.doc,.docx"
            maxFileSize={100_000_000}
            customUpload
            uploadHandler={handleUpload}
            auto={false}
            chooseLabel="Select File"
            uploadLabel="Upload"
            cancelLabel="Cancel"
            emptyTemplate={
              <p className="py-4 text-center text-gray-500">
                Drag and drop a file here, or click to select.
              </p>
            }
          />
        </div>

        {uploadMutation.isPending && (
          <Message severity="info" text="Uploading..." />
        )}

        {uploadMutation.isError && (
          <Message
            severity="error"
            text={uploadMutation.error?.message ?? "Upload failed"}
          />
        )}

        {uploadMutation.isSuccess && (
          <Message severity="success" text="Upload successful! Redirecting..." />
        )}

        <div>
          <Button
            label="Back to Documents"
            icon="pi pi-arrow-left"
            severity="secondary"
            text
            onClick={() => router.push(`/${workspace}/documents`)}
          />
        </div>
      </div>
    </div>
  );
}
