"use client";

import { useState } from "react";
import { useAuthzHasRole } from "@duar-auth/react";

import { useConfirm } from "@/components/providers/ConfirmProvider";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/Card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  LOCAL_EMBEDDING_MODEL,
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
  const isAdmin = useAuthzHasRole("admin");
  const confirm = useConfirm();
  const [choice, setChoice] = useState<string | null>(null);

  if (!data?.enabled) return null;

  const builtIn = `Built-in (${data.server_model}), no key needed`;
  const labelOf = (id: string) =>
    id === LOCAL_EMBEDDING_MODEL ? builtIn : (data.options.find((o) => o.id === id)?.label ?? id);
  const selected = choice ?? data.model;
  const selectedOption = data.options.find((o) => o.id === selected);

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
          <Button size="sm" disabled={selected === data.model || save.isPending} onClick={onSave}>
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
      {save.data && save.data.reembed_workflows > 0 && (
        <p className="mt-2 text-xs text-text-muted">Re-embedding started.</p>
      )}
    </Card>
  );
}
