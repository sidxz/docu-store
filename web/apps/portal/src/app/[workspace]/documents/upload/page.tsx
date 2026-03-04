"use client";

import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { Dropdown } from "primereact/dropdown";
import { FileUpload, type FileUploadHandlerEvent } from "primereact/fileupload";
import { InputText } from "primereact/inputtext";
import { Upload, ArrowLeft, AlertCircle, CheckCircle2, Loader2 } from "lucide-react";

import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
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
    <div>
      {/* Back link */}
      <button
        className="mb-4 flex items-center gap-1.5 text-sm text-text-secondary hover:text-text-primary transition-colors"
        onClick={() => router.push(`/${workspace}/documents`)}
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Documents
      </button>

      <PageHeader
        icon={Upload}
        title="Upload Document"
        subtitle="Upload a document for automated analysis and extraction"
      />

      <Card className="max-w-2xl">
        <div className="space-y-6">
          <div>
            <label className="mb-2 block text-sm font-medium text-text-primary">
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
            <label className="mb-2 block text-sm font-medium text-text-primary">
              Source URI
              <span className="ml-1 text-text-muted font-normal">(optional)</span>
            </label>
            <InputText
              value={sourceUri}
              onChange={(e) => setSourceUri(e.target.value)}
              placeholder="https://..."
              className="w-full"
            />
          </div>

          <div>
            <label className="mb-2 block text-sm font-medium text-text-primary">
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
                <div className="flex flex-col items-center py-8 text-center">
                  <Upload className="mb-3 h-10 w-10 text-text-muted" />
                  <p className="text-sm font-medium text-text-secondary">
                    Drag and drop a file here
                  </p>
                  <p className="mt-1 text-xs text-text-muted">
                    PDF, PPTX, DOC, DOCX up to 100MB
                  </p>
                </div>
              }
            />
          </div>

          {/* Status messages */}
          {uploadMutation.isPending && (
            <div className="flex items-center gap-2 rounded-lg border border-accent/20 bg-accent-light p-3 text-sm text-accent-text">
              <Loader2 className="h-4 w-4 animate-spin" />
              Uploading...
            </div>
          )}

          {uploadMutation.isError && (
            <div className="flex items-center gap-2 rounded-lg border border-ds-error/20 bg-ds-error/5 p-3 text-sm text-ds-error">
              <AlertCircle className="h-4 w-4" />
              {uploadMutation.error?.message ?? "Upload failed"}
            </div>
          )}

          {uploadMutation.isSuccess && (
            <div className="flex items-center gap-2 rounded-lg border border-ds-success/20 bg-ds-success/5 p-3 text-sm text-ds-success">
              <CheckCircle2 className="h-4 w-4" />
              Upload successful! Redirecting...
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
