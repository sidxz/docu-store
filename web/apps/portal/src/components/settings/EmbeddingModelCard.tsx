"use client";

import { useState } from "react";
import { useAuthzHasRole } from "@duar-auth/react";

import { useConfirm } from "@/components/providers/ConfirmProvider";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/Card";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  LOCAL_EMBEDDING_MODEL,
  useResumeReembed,
  useSetWorkspaceEmbedding,
  useWorkspaceEmbedding,
} from "@/hooks/use-workspace-embedding";
import { getErrorMessage } from "@/lib/api-error";

const PROVIDER_LABEL: Record<string, string> = {
  openai: "OpenAI",
  gemini: "Gemini",
  openrouter: "OpenRouter",
};

/** Which model turns this workspace's documents and searches into vectors.
 *  One per workspace: documents and queries must share a vector space. */
export function EmbeddingModelCard() {
  const { data } = useWorkspaceEmbedding();
  const save = useSetWorkspaceEmbedding();
  const resume = useResumeReembed();
  const isAdmin = useAuthzHasRole("admin");
  const confirm = useConfirm();
  const [choice, setChoice] = useState<string | null>(null);

  if (!data?.enabled) return null;

  const builtIn = `Built-in (${data.server_model}), no key needed`;
  const labelOf = (id: string) =>
    id === LOCAL_EMBEDDING_MODEL ? builtIn : (data.options.find((o) => o.id === id)?.label ?? id);
  const selected = choice ?? data.model;
  const selectedOption = data.options.find((o) => o.id === selected);
  const reembed = data.reembed;
  // "unknown" counts as running: the server refuses a model change it can't confirm is safe.
  const running = reembed?.state === "running" || reembed?.state === "unknown";

  const onSave = async () => {
    if (
      data.has_documents &&
      !(await confirm({
        title: "Re-embed every document?",
        description:
          "Searches compare against vectors from one model, so every document in this " +
          "workspace is embedded again with the new one, on this workspace's key. " +
          "Search results are incomplete until that finishes.",
        confirmLabel: "Change and re-embed",
      }))
    ) {
      return;
    }
    save.mutate(
      { model: selected, reembed: data.has_documents },
      { onSuccess: () => setChoice(null) },
    );
  };

  return (
    <Card>
      <CardHeader title="Search embeddings" />
      <p className="text-sm text-text-muted">
        The model that turns this workspace&apos;s documents and searches into vectors, run on
        the keys above.
      </p>

      {isAdmin ? (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Select value={selected} onValueChange={setChoice}>
            <SelectTrigger className="min-w-72">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={LOCAL_EMBEDDING_MODEL}>{builtIn}</SelectItem>
              {data.options.map((o) => (
                <SelectItem key={o.id} value={o.id}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            size="sm"
            disabled={selected === data.model || save.isPending || running}
            onClick={onSave}
          >
            {data.has_documents ? "Save and re-embed" : "Save"}
          </Button>
        </div>
      ) : (
        <p className="mt-3 text-sm text-text-primary">{labelOf(data.model)}</p>
      )}

      {selectedOption && (
        <p className="mt-2 text-xs text-text-muted">
          Needs a key from{" "}
          {selectedOption.providers.map((p) => PROVIDER_LABEL[p] ?? p).join(" or ")} above.
        </p>
      )}
      {!data.usable && data.detail && (
        <Alert variant="warning" className="mt-3">
          <AlertDescription>{data.detail}</AlertDescription>
        </Alert>
      )}
      {save.isError && (
        <Alert variant="destructive" className="mt-3">
          <AlertDescription>{getErrorMessage(save.error)}</AlertDescription>
        </Alert>
      )}
      {running && (
        <div className="mt-3 space-y-1.5">
          <p className="text-xs text-text-muted">
            {reembed.state === "unknown" ? "Can't reach the re-embed service right now. " : "Re-embedding documents: "}
            {reembed.done.toLocaleString()} of {reembed.total.toLocaleString()} vectors done.
            Search covers the finished ones.
          </p>
          <Progress value={reembed.total ? (reembed.done / reembed.total) * 100 : 0} />
        </div>
      )}
      {reembed?.state === "failed" && (
        <Alert variant="destructive" className="mt-3">
          <AlertDescription>
            <p>
              Re-embedding stopped with {(reembed.total - reembed.done).toLocaleString()} of{" "}
              {reembed.total.toLocaleString()} vectors still on a previous model. Search skips
              them until they are re-embedded.
            </p>
            {reembed.error && <p className="mt-1 font-mono text-xs">{reembed.error}</p>}
            {isAdmin ? (
              <Button
                size="sm"
                variant="outline"
                className="mt-2"
                disabled={resume.isPending}
                onClick={() => resume.mutate()}
              >
                Retry
              </Button>
            ) : (
              <p className="mt-1">Ask a workspace admin to retry.</p>
            )}
          </AlertDescription>
        </Alert>
      )}
      {resume.isError && (
        <Alert variant="destructive" className="mt-3">
          <AlertDescription>{getErrorMessage(resume.error)}</AlertDescription>
        </Alert>
      )}
    </Card>
  );
}
