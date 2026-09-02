"use client";

import { useId, useState } from "react";
import { CheckCircle2, ChevronDown, KeyRound, XCircle } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
} from "@/components/ui/input-group";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import {
  type LlmProviderEntry,
  type LlmProviderId,
  type LlmProviderStatus,
  type LlmProviderTestResult,
  useActivateLlmProvider,
  useDeleteLlmProvider,
  useLlmProvider,
  useSaveLlmProvider,
  useTestLlmProvider,
} from "@/hooks/use-llm-provider";
import { getErrorMessage } from "@/lib/api-error";
import { startOpenRouterAuth } from "@/lib/openrouter-pkce";

/** OpenRouter's own catalog, filtered to what entity extraction can actually use. */
const OPENROUTER_CAPABLE_MODELS =
  "https://openrouter.ai/models?supported_parameters=structured_outputs";

interface Provider {
  id: LlmProviderId;
  label: string;
  hint: string;
  keysUrl: string;
  pricingUrl: string;
}

/** Order is the recommendation: the two direct providers first, OpenRouter for
 *  whoever wants the long tail and is willing to check what a model supports. */
const PROVIDERS: Provider[] = [
  {
    id: "openai",
    label: "OpenAI",
    hint: "Connect with an OpenAI API key.",
    keysUrl: "https://platform.openai.com/api-keys",
    pricingUrl: "https://platform.openai.com/docs/pricing",
  },
  {
    id: "gemini",
    label: "Google Gemini",
    hint: "Connect with a Google AI Studio API key. A paid plan is recommended for document processing.",
    keysUrl: "https://aistudio.google.com/apikey",
    pricingUrl: "https://ai.google.dev/gemini-api/docs/pricing",
  },
  {
    id: "openrouter",
    label: "OpenRouter",
    hint: "Hundreds of models through one account. You pick the model yourself.",
    keysUrl: "https://openrouter.ai/settings/keys",
    pricingUrl: OPENROUTER_CAPABLE_MODELS,
  },
];

const LANE_LABEL = {
  batch: "Ingestion (summaries, metadata)",
  chat: "Chat",
  // Its own lane: a model can pass the batch check and still reject the
  // structured-output request entity extraction makes.
  ner: "Entity extraction (needs structured output)",
} as const;

function providerOf(id: LlmProviderId): Provider | undefined {
  return PROVIDERS.find((p) => p.id === id);
}

function providerLabel(id: LlmProviderId): string {
  return providerOf(id)?.label ?? id;
}

/** Where to get a key and what it costs — both live at the provider, not here. */
function ProviderLinks({ provider }: { provider: LlmProviderId }) {
  const p = providerOf(provider);
  if (!p) return null;
  return (
    <p className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-muted">
      <a
        className="underline hover:text-text-primary"
        href={p.keysUrl}
        target="_blank"
        rel="noreferrer"
      >
        Get an API key ↗
      </a>
      <a
        className="underline hover:text-text-primary"
        href={p.pricingUrl}
        target="_blank"
        rel="noreferrer"
      >
        Models &amp; pricing ↗
      </a>
    </p>
  );
}

/** OpenRouter resells models that cannot do entity extraction, and activating one
 *  is refused. Say so up front rather than only in the rejection. */
function StructuredOutputNote() {
  return (
    <p className="text-xs text-text-muted">
      Whichever ingestion model you pick must support structured outputs — entity
      extraction cannot run without it.{" "}
      <a
        className="underline hover:text-text-primary"
        href={OPENROUTER_CAPABLE_MODELS}
        target="_blank"
        rel="noreferrer"
      >
        Browse the models that do ↗
      </a>
    </p>
  );
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

/**
 * One free-text model field, listed three ways: the `datalist` completes what you
 * type, the chevron opens the whole list for anyone who does not know the names,
 * and anything else you type is still accepted. Chrome's own datalist arrow is
 * hidden — the chevron is that button, and two of them is one too many. The names
 * come from the backend reading OpenRouter's live catalog, so both lists are
 * absent for OpenRouter itself and whenever that catalog is down.
 */
function ModelField({
  label,
  value,
  placeholder,
  suggestions,
  onChange,
}: {
  label: string;
  value: string;
  placeholder: string;
  suggestions: string[];
  onChange: (v: string) => void;
}) {
  const id = useId();
  const listId = `${id}-models`;
  const hasList = suggestions.length > 0;
  return (
    <div>
      <label htmlFor={id} className="text-xs text-text-muted">
        {label}
      </label>
      <InputGroup className="mt-1">
        <InputGroupInput
          id={id}
          className="font-mono text-xs [&::-webkit-calendar-picker-indicator]:hidden!"
          list={hasList ? listId : undefined}
          value={value}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
        />
        {hasList && (
          <InputGroupAddon align="inline-end">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <InputGroupButton size="icon-xs" aria-label={`Choose a ${label.toLowerCase()}`}>
                  <ChevronDown />
                </InputGroupButton>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="max-h-72 overflow-y-auto">
                {suggestions.map((m) => (
                  <DropdownMenuItem
                    key={m}
                    className="font-mono text-xs"
                    onSelect={() => onChange(m)}
                  >
                    {m}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          </InputGroupAddon>
        )}
      </InputGroup>
      {hasList && (
        <datalist id={listId}>
          {suggestions.map((m) => (
            <option key={m} value={m} />
          ))}
        </datalist>
      )}
    </div>
  );
}

function ModelInputs({
  model,
  chatModel,
  placeholder,
  suggestions,
  onModel,
  onChatModel,
}: {
  model: string;
  chatModel: string;
  placeholder: { model: string; chat_model: string };
  suggestions: string[];
  onModel: (v: string) => void;
  onChatModel: (v: string) => void;
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <ModelField
        label="Ingestion model"
        value={model}
        placeholder={placeholder.model}
        suggestions={suggestions}
        onChange={onModel}
      />
      <ModelField
        label="Chat model (needs tools + vision)"
        value={chatModel}
        placeholder={placeholder.chat_model}
        suggestions={suggestions}
        onChange={onChatModel}
      />
    </div>
  );
}

/** One stored provider: what it runs, whether it is the active one, and the
 *  four things you can do to it. Its key stays put whatever happens elsewhere. */
function ProviderRow({
  entry,
  status,
  onActivated,
}: {
  entry: LlmProviderEntry;
  status: LlmProviderStatus;
  onActivated?: () => void;
}) {
  const save = useSaveLlmProvider();
  const remove = useDeleteLlmProvider();
  const activate = useActivateLlmProvider();
  const test = useTestLlmProvider();
  const [model, setModel] = useState(entry.model);
  const [chatModel, setChatModel] = useState(entry.chat_model);
  const [result, setResult] = useState<LlmProviderTestResult | null>(null);
  const dirty = model !== entry.model || chatModel !== entry.chat_model;
  const busy = save.isPending || remove.isPending || activate.isPending || test.isPending;
  const error = save.error ?? remove.error ?? activate.error ?? test.error;

  // Tests what is in the boxes, not what is in the database: you test a model to
  // find out whether it works, so needing to save it first would be backwards.
  const runTest = async () => {
    setResult(
      await test
        .mutateAsync({ provider: entry.provider, model, chat_model: chatModel })
        .catch(() => null),
    );
  };

  return (
    <div
      className={`rounded-lg border p-4 ${
        entry.active ? "border-primary bg-surface-sunken/40" : "border-border-default"
      }`}
    >
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <KeyRound className="h-4 w-4 text-text-muted" />
        <span className="font-medium text-text-primary">{providerLabel(entry.provider)}</span>
        <span className="font-mono text-xs text-text-muted">key ••••{entry.key_last4}</span>
        {entry.active ? (
          <Badge variant="success">Active</Badge>
        ) : (
          <Badge variant="outline" className="text-text-muted">
            Inactive
          </Badge>
        )}
      </div>

      <div className="mt-3 space-y-3">
        <ModelInputs
          model={model}
          chatModel={chatModel}
          placeholder={status.presets[entry.provider]}
          suggestions={status.suggestions?.[entry.provider] ?? []}
          onModel={setModel}
          onChatModel={setChatModel}
        />
        {entry.provider === "openrouter" && <StructuredOutputNote />}
        <ProviderLinks provider={entry.provider} />

        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={!dirty || busy}
            onClick={() =>
              save.mutate({
                provider: entry.provider,
                model: model || undefined,
                chat_model: chatModel || undefined,
              })
            }
          >
            {save.isPending ? "Saving…" : "Save models"}
          </Button>
          <Button size="sm" variant="outline" disabled={busy} onClick={runTest}>
            {test.isPending ? "Testing…" : "Test"}
          </Button>
          {!entry.active && (
            <Button
              size="sm"
              disabled={busy}
              onClick={async () => {
                await activate.mutateAsync(entry.provider).catch(() => null);
                onActivated?.();
              }}
            >
              {activate.isPending ? "Switching…" : "Make active"}
            </Button>
          )}
          <Button
            size="sm"
            variant="ghost"
            className="text-red-600"
            disabled={busy}
            onClick={() => remove.mutate(entry.provider)}
          >
            Delete
          </Button>
        </div>

        {save.isPending && (
          <p className="text-xs text-text-muted">
            Checking the ingestion model can run entity extraction — this calls the
            provider, so it takes a few seconds.
          </p>
        )}
        {dirty && !save.isPending && (
          <p className="text-xs text-text-muted">Unsaved model changes.</p>
        )}
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{getErrorMessage(error)}</AlertDescription>
          </Alert>
        )}
        {result && <TestResult result={result} />}
      </div>
    </div>
  );
}

/** Add a provider, or replace the key of one already here. Never touches the others. */
function AddProvider({
  status,
  onSaved,
  onCancel,
}: {
  status: LlmProviderStatus;
  onSaved: (provider: LlmProviderId) => void;
  onCancel?: () => void;
}) {
  const save = useSaveLlmProvider();
  const [provider, setProvider] = useState<LlmProviderId>("openai");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [chatModel, setChatModel] = useState("");
  const [connecting, setConnecting] = useState(false);
  const [connectError, setConnectError] = useState<string | null>(null);
  const preset = status.presets[provider];
  const alreadyStored = status.providers.some((p) => p.provider === provider);

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
    onSaved(provider);
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

      {alreadyStored && (
        <p className="text-xs text-text-muted">
          {providerLabel(provider)} is already configured — adding it again replaces its
          stored key.
        </p>
      )}

      <ProviderLinks provider={provider} />

      {provider === "openrouter" ? (
        <>
          <StructuredOutputNote />
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
            suggestions={status.suggestions?.[provider] ?? []}
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
        A new provider becomes the active one. Whatever you had stays stored, so switching
        back is one click.
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
 * The one BYO-LLM panel, hosted by the settings tab and by /onboarding.
 * `onConfigured` fires after a green connection test (onboarding uses it to
 * continue into the app).
 */
export function LlmProviderForm({ onConfigured }: { onConfigured?: () => void }) {
  const status = useLlmProvider();
  const test = useTestLlmProvider();
  const [adding, setAdding] = useState(false);
  const [autoTest, setAutoTest] = useState<LlmProviderTestResult | null>(null);

  if (status.isPending) return <LoadingSpinner size="sm" />;
  if (status.isError || !status.data) {
    return (
      <p className="text-sm text-red-500">
        Couldn’t load provider settings: {getErrorMessage(status.error)}
      </p>
    );
  }

  const { providers, configured } = status.data;
  const showAdd = adding || providers.length === 0;

  return (
    <div className="space-y-5">
      {providers.length > 0 && !configured && (
        <Alert variant="destructive">
          <AlertDescription>
            No active provider — document processing and chat are stopped until you make one
            active.
          </AlertDescription>
        </Alert>
      )}

      {providers.map((entry) => (
        <ProviderRow
          key={entry.provider}
          entry={entry}
          status={status.data}
          onActivated={onConfigured}
        />
      ))}

      {autoTest && !test.isPending && <TestResult result={autoTest} />}

      {showAdd ? (
        <AddProvider
          status={status.data}
          onCancel={providers.length > 0 ? () => setAdding(false) : undefined}
          onSaved={async (provider) => {
            setAdding(false);
            // Auto-test right after a save so the verdict is immediate — and if it
            // is red, the provider you came from is still one click away.
            const result = await test.mutateAsync({ provider }).catch(() => null);
            setAutoTest(result);
            if (result?.ok) onConfigured?.();
          }}
        />
      ) : (
        <Button variant="outline" size="sm" onClick={() => setAdding(true)}>
          Add another provider
        </Button>
      )}
    </div>
  );
}
