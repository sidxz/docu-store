"use client";

import { useState } from "react";
import { CheckCircle2, KeyRound, XCircle } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import {
  type LlmProviderId,
  type LlmProviderStatus,
  type LlmProviderTestResult,
  useDeleteLlmProvider,
  useLlmProvider,
  useSaveLlmProvider,
  useTestLlmProvider,
} from "@/hooks/use-llm-provider";
import { getErrorMessage } from "@/lib/api-error";
import { startOpenRouterAuth } from "@/lib/openrouter-pkce";

const PROVIDERS: { id: LlmProviderId; label: string; hint: string }[] = [
  {
    id: "openrouter",
    label: "OpenRouter",
    hint: "Sign in with OpenRouter to use hundreds of models with one account. Recommended.",
  },
  { id: "openai", label: "OpenAI", hint: "Paste an API key from platform.openai.com." },
  {
    id: "gemini",
    label: "Google Gemini",
    hint: "Paste a Google AI Studio key. Use a paid plan. The free plan is too limited for document processing.",
  },
];

const LANE_LABEL = { batch: "Ingestion (summaries, entities, metadata)", chat: "Chat" } as const;

function providerLabel(id: LlmProviderId | null): string {
  return PROVIDERS.find((p) => p.id === id)?.label ?? "Unknown";
}

function TestResult({ result }: { result: LlmProviderTestResult }) {
  return (
    <ul className="mt-3 space-y-1 text-sm">
      {(Object.keys(LANE_LABEL) as (keyof typeof LANE_LABEL)[]).map((lane) => {
        const r = result.lanes[lane];
        return (
          <li key={lane} className="flex items-start gap-2">
            {r.ok ? (
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-green-600" />
            ) : (
              <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-500" />
            )}
            <span>
              <span className="text-text-primary">{LANE_LABEL[lane]}</span>
              {r.detail && <span className="block text-xs text-text-muted">{r.detail}</span>}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function ModelInputs({
  model,
  chatModel,
  placeholder,
  onModel,
  onChatModel,
}: {
  model: string;
  chatModel: string;
  placeholder: { model: string; chat_model: string };
  onModel: (v: string) => void;
  onChatModel: (v: string) => void;
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <label className="text-xs text-text-muted">
        Ingestion model
        <Input
          className="mt-1 font-mono text-xs"
          value={model}
          placeholder={placeholder.model}
          onChange={(e) => onModel(e.target.value)}
        />
      </label>
      <label className="text-xs text-text-muted">
        Chat model (needs tools + vision)
        <Input
          className="mt-1 font-mono text-xs"
          value={chatModel}
          placeholder={placeholder.chat_model}
          onChange={(e) => onChatModel(e.target.value)}
        />
      </label>
    </div>
  );
}

/** Connected state: summary + test + edit models + disconnect. */
function ConnectedView({
  status,
  onChange,
  onConfigured,
}: {
  status: LlmProviderStatus;
  onChange: () => void;
  onConfigured?: () => void;
}) {
  const save = useSaveLlmProvider();
  const remove = useDeleteLlmProvider();
  const test = useTestLlmProvider();
  const [model, setModel] = useState(status.model ?? "");
  const [chatModel, setChatModel] = useState(status.chat_model ?? "");
  const provider = status.provider ?? "openai";
  const dirty = model !== (status.model ?? "") || chatModel !== (status.chat_model ?? "");

  const runTest = async () => {
    try {
      const result = await test.mutateAsync();
      if (result.ok) onConfigured?.();
    } catch {
      /* surfaced via test.isError */
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 text-sm">
        <KeyRound className="h-4 w-4 text-text-muted" />
        <span className="font-medium text-text-primary">{providerLabel(status.provider)}</span>
        <span className="font-mono text-xs text-text-muted">key ••••{status.key_last4}</span>
      </div>
      <ModelInputs
        model={model}
        chatModel={chatModel}
        placeholder={status.presets[provider]}
        onModel={setModel}
        onChatModel={setChatModel}
      />
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="outline"
          disabled={!dirty || save.isPending}
          onClick={() =>
            save.mutate({ provider, model: model || undefined, chat_model: chatModel || undefined })
          }
        >
          Save models
        </Button>
        <Button size="sm" disabled={test.isPending} onClick={runTest}>
          {test.isPending ? "Testing…" : "Test connection"}
        </Button>
        <Button size="sm" variant="ghost" onClick={onChange}>
          Change provider
        </Button>
        <Button
          size="sm"
          variant="ghost"
          className="text-red-600"
          disabled={remove.isPending}
          onClick={() => remove.mutate()}
        >
          Disconnect
        </Button>
      </div>
      {(save.isError || remove.isError || test.isError) && (
        <Alert variant="destructive">
          <AlertDescription>
            {getErrorMessage(save.error ?? remove.error ?? test.error)}
          </AlertDescription>
        </Alert>
      )}
      {test.data && <TestResult result={test.data} />}
    </div>
  );
}

/** Setup state: pick a provider, connect (OpenRouter) or paste a key. */
function SetupView({
  status,
  onSaved,
  onCancel,
}: {
  status: LlmProviderStatus;
  onSaved: () => void;
  onCancel?: () => void;
}) {
  const save = useSaveLlmProvider();
  const [provider, setProvider] = useState<LlmProviderId>("openrouter");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [chatModel, setChatModel] = useState("");
  const [connecting, setConnecting] = useState(false);
  const [connectError, setConnectError] = useState<string | null>(null);
  const preset = status.presets[provider];

  const pick = (id: LlmProviderId) => {
    setProvider(id);
    setApiKey("");
    setModel("");
    setChatModel("");
  };

  const submit = async () => {
    await save.mutateAsync({
      provider,
      api_key: apiKey,
      model: model || undefined,
      chat_model: chatModel || undefined,
    });
    setApiKey("");
    onSaved();
  };

  return (
    <div className="space-y-4">
      <div className="grid gap-2 sm:grid-cols-3">
        {PROVIDERS.map((p) => (
          <button
            key={p.id}
            type="button"
            onClick={() => pick(p.id)}
            className={`rounded-md border p-3 text-left text-sm transition-colors ${
              provider === p.id
                ? "border-primary bg-surface-sunken"
                : "border-border-default hover:bg-surface-sunken/60"
            }`}
          >
            <span className="block font-medium text-text-primary">{p.label}</span>
            <span className="mt-1 block text-xs text-text-muted">{p.hint}</span>
          </button>
        ))}
      </div>

      {provider === "openrouter" ? (
        <>
          <Button
            disabled={connecting}
            onClick={async () => {
              setConnecting(true);
              try {
                await startOpenRouterAuth(window.location.pathname);
              } catch (e) {
                setConnecting(false);
                setConnectError(
                  e instanceof Error ? e.message : "Could not start OpenRouter sign-in.",
                );
              }
            }}
          >
            {connecting ? "Redirecting…" : "Connect with OpenRouter"}
          </Button>
          {connectError && (
            <Alert variant="destructive">
              <AlertDescription>{connectError}</AlertDescription>
            </Alert>
          )}
        </>
      ) : (
        <>
          <label className="block text-xs text-text-muted">
            API key
            <Input
              className="mt-1 font-mono text-xs"
              type="password"
              autoComplete="off"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={provider === "openai" ? "sk-…" : "AIza…"}
            />
          </label>
          <ModelInputs
            model={model}
            chatModel={chatModel}
            placeholder={preset}
            onModel={setModel}
            onChatModel={setChatModel}
          />
          <div className="flex gap-2">
            <Button disabled={apiKey.trim().length < 8 || save.isPending} onClick={submit}>
              {save.isPending ? "Saving…" : "Save key"}
            </Button>
            {onCancel && (
              <Button variant="ghost" onClick={onCancel}>
                Cancel
              </Button>
            )}
          </div>
        </>
      )}
      <p className="text-xs text-text-muted">
        Your key is encrypted and never shown again. The models shown are defaults. Change
        them if you like.
      </p>
      {save.isError && (
        <Alert variant="destructive">
          <AlertDescription>{getErrorMessage(save.error)}</AlertDescription>
        </Alert>
      )}
    </div>
  );
}

/**
 * The one BYO-LLM form, hosted by the settings tab and by /onboarding.
 * `onConfigured` fires after a green connection test (onboarding uses it to
 * continue into the app).
 */
export function LlmProviderForm({ onConfigured }: { onConfigured?: () => void }) {
  const status = useLlmProvider();
  const test = useTestLlmProvider();
  const [editing, setEditing] = useState(false);
  const [autoTest, setAutoTest] = useState<LlmProviderTestResult | null>(null);

  if (status.isPending) return <LoadingSpinner size="sm" />;
  if (status.isError || !status.data) {
    return (
      <p className="text-sm text-red-500">
        Couldn’t load provider settings: {getErrorMessage(status.error)}
      </p>
    );
  }

  if (status.data.configured && !editing) {
    return (
      <>
        <ConnectedView
          status={status.data}
          onChange={() => setEditing(true)}
          onConfigured={onConfigured}
        />
        {autoTest && !test.isPending && <TestResult result={autoTest} />}
      </>
    );
  }

  return (
    <SetupView
      status={status.data}
      onCancel={status.data.configured ? () => setEditing(false) : undefined}
      onSaved={async () => {
        setEditing(false);
        // Auto-test right after a save so the user sees a verdict immediately.
        const result = await test.mutateAsync().catch(() => null);
        setAutoTest(result);
        if (result?.ok) onConfigured?.();
      }}
    />
  );
}
