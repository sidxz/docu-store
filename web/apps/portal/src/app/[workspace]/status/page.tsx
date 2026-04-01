"use client";

import { useState, useCallback } from "react";
import {
  Activity,
  AlertTriangle,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ClipboardCopy,
  HardDrive,
  Layers,
  MonitorCog,
  RefreshCw,
  Server,
  ShieldAlert,
  XCircle,
} from "lucide-react";
import { Skeleton } from "primereact/skeleton";
import { SelectButton } from "primereact/selectbutton";
import { useQueryClient } from "@tanstack/react-query";
import { useAuthzHasRole } from "@sentinel-auth/react";

import { PageHeader } from "@/components/ui/PageHeader";
import { StatCard } from "@/components/ui/StatCard";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { queryKeys } from "@/lib/query-keys";
import {
  useDetailedHealth,
  useReembedAll,
  ALL_REEMBED_TARGETS,
  type ReEmbedTarget,
  type ServiceStatus,
  type ModelStatus,
  type GpuDevice,
  type DetailedHealthResponse,
} from "@/hooks/use-health";
import {
  fmtUptime,
  statusBg,
  statusColor,
  statusDot,
  statusLabel,
} from "./status-helpers";
import { WorkersSection } from "./WorkersSection";

const REFRESH_OPTIONS = [
  { label: "15s", value: 15_000 },
  { label: "30s", value: 30_000 },
  { label: "60s", value: 60_000 },
  { label: "Off", value: false as const },
];

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function OverallBanner({ status }: { status: string }) {
  const icon =
    status === "healthy" ? CheckCircle2 : status === "degraded" ? AlertTriangle : XCircle;
  const Icon = icon;
  const label =
    status === "healthy"
      ? "All Systems Operational"
      : status === "degraded"
        ? "Partial System Degradation"
        : "System Unhealthy";

  return (
    <div
      className={`mb-6 flex items-center gap-3 rounded-xl border p-4 ${statusBg(status)}`}
    >
      <Icon className={`h-6 w-6 ${statusColor(status)}`} />
      <div>
        <p className={`text-sm font-semibold ${statusColor(status)}`}>{label}</p>
        <p className="text-xs text-text-muted">
          {status === "healthy"
            ? "All services, models, and infrastructure checks passed."
            : "Some checks reported issues. See details below."}
        </p>
      </div>
    </div>
  );
}

function ServiceRow({ service }: { service: ServiceStatus }) {
  const [expanded, setExpanded] = useState(false);
  const hasDetails = service.error || service.details;

  return (
    <div className="border-b border-border-default last:border-b-0">
      <button
        type="button"
        className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-surface-sunken/50"
        onClick={() => hasDetails && setExpanded(!expanded)}
        disabled={!hasDetails}
      >
        <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${statusDot(service.status)}`} />
        <span className="flex-1 text-sm font-medium text-text-primary">
          {service.name}
        </span>
        {service.version && (
          <span className="rounded bg-surface-sunken px-2 py-0.5 text-xs text-text-muted">
            v{service.version}
          </span>
        )}
        {service.latency_ms != null && (
          <span className="rounded bg-surface-sunken px-2 py-0.5 text-xs tabular-nums text-text-muted">
            {service.latency_ms}ms
          </span>
        )}
        <span className={`text-xs font-medium ${statusColor(service.status)}`}>
          {statusLabel(service.status)}
        </span>
        {hasDetails ? (
          expanded ? (
            <ChevronDown className="h-4 w-4 text-text-muted" />
          ) : (
            <ChevronRight className="h-4 w-4 text-text-muted" />
          )
        ) : (
          <span className="w-4" />
        )}
      </button>
      {expanded && hasDetails && (
        <div className="border-t border-border-default bg-surface-sunken/30 px-4 py-3">
          {service.error && (
            <p className="mb-2 text-xs text-ds-error">
              <span className="font-semibold">Error:</span> {service.error}
            </p>
          )}
          {service.details && (
            <pre className="max-h-48 overflow-auto rounded bg-surface-sunken p-2 text-xs text-text-secondary">
              {JSON.stringify(service.details, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

function ModelRow({ model }: { model: ModelStatus }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border-b border-border-default last:border-b-0">
      <button
        type="button"
        className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-surface-sunken/50"
        onClick={() => model.error && setExpanded(!expanded)}
        disabled={!model.error}
      >
        {model.inference_ok === true ? (
          <Check className="h-4 w-4 shrink-0 text-ds-success" />
        ) : model.inference_ok === false ? (
          <XCircle className="h-4 w-4 shrink-0 text-ds-error" />
        ) : (
          <span className="h-4 w-4 shrink-0 rounded-full bg-gray-400/40" />
        )}
        <span className="flex-1 text-sm font-medium text-text-primary">
          {model.name}
        </span>
        <span className="rounded bg-surface-sunken px-2 py-0.5 text-xs text-text-muted">
          {model.model_name}
        </span>
        <span
          className={`rounded px-2 py-0.5 text-xs font-medium ${
            model.device === "cuda"
              ? "bg-green-500/10 text-green-600 dark:text-green-400"
              : model.device === "mps"
                ? "bg-blue-500/10 text-blue-600 dark:text-blue-400"
                : "bg-surface-sunken text-text-muted"
          }`}
        >
          {model.device}
        </span>
        {model.error ? (
          expanded ? (
            <ChevronDown className="h-4 w-4 text-text-muted" />
          ) : (
            <ChevronRight className="h-4 w-4 text-text-muted" />
          )
        ) : (
          <span className="w-4" />
        )}
      </button>
      {expanded && model.error && (
        <div className="border-t border-border-default bg-surface-sunken/30 px-4 py-3">
          <p className="text-xs text-ds-error">
            <span className="font-semibold">Error:</span> {model.error}
          </p>
        </div>
      )}
    </div>
  );
}

function GpuSection({
  gpu,
  configSmiles,
  configEmbedding,
}: {
  gpu: DetailedHealthResponse["gpu"];
  configSmiles: string;
  configEmbedding: string;
}) {
  const needsCuda =
    configSmiles === "cuda" || configEmbedding === "cuda";
  const gpuMissing = needsCuda && !gpu.cuda_available;

  return (
    <Card>
      <CardHeader title="GPU & Compute" />
      <div className="space-y-3">
        {gpuMissing && (
          <div className="flex items-start gap-2 rounded-lg border border-red-500/20 bg-red-500/10 p-3">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-ds-error" />
            <div>
              <p className="text-sm font-semibold text-ds-error">
                CUDA configured but no GPU detected
              </p>
              <p className="mt-0.5 text-xs text-text-secondary">
                Models configured for CUDA will fail. Check NVIDIA drivers and
                Docker GPU runtime. This causes silent failures in SMILES
                embedding generation.
              </p>
            </div>
          </div>
        )}

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <InfoCell
            label="CUDA"
            value={gpu.cuda_available ? "Available" : "Not available"}
            ok={gpu.cuda_available || !needsCuda}
          />
          <InfoCell
            label="MPS (Apple)"
            value={gpu.mps_available ? "Available" : "Not available"}
            ok={true}
          />
          <InfoCell
            label="CUDA Version"
            value={gpu.cuda_version ?? "N/A"}
            ok={true}
          />
          <InfoCell
            label="GPU Count"
            value={String(gpu.device_count)}
            ok={true}
          />
        </div>

        {gpu.devices.length > 0 && (
          <div className="space-y-2">
            {gpu.devices.map((device) => (
              <GpuDeviceCard key={device.index} device={device} />
            ))}
          </div>
        )}
      </div>
    </Card>
  );
}

function GpuDeviceCard({ device }: { device: GpuDevice }) {
  const usedPct = Math.round(
    (device.memory_used_mb / device.memory_total_mb) * 100,
  );

  return (
    <div className="rounded-lg border border-border-default bg-surface-sunken/40 p-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-text-primary">
          GPU {device.index}: {device.name}
        </span>
        <span className="text-xs text-text-muted">
          {device.memory_used_mb} / {device.memory_total_mb} MB ({usedPct}%)
        </span>
      </div>
      <div className="mt-2 h-2 w-full rounded-full bg-surface-sunken">
        <div
          className={`h-2 rounded-full transition-all ${
            usedPct > 90
              ? "bg-red-500"
              : usedPct > 70
                ? "bg-amber-500"
                : "bg-emerald-500"
          }`}
          style={{ width: `${usedPct}%` }}
        />
      </div>
    </div>
  );
}

function InfoCell({
  label,
  value,
  ok,
}: {
  label: string;
  value: string;
  ok: boolean;
}) {
  return (
    <div className="rounded-lg border border-border-default bg-surface-sunken/40 p-2.5">
      <p className="text-xs text-text-muted">{label}</p>
      <p
        className={`mt-0.5 text-sm font-medium ${ok ? "text-text-primary" : "text-ds-error"}`}
      >
        {value}
      </p>
    </div>
  );
}

function ConfigSection({ config }: { config: DetailedHealthResponse["config"] }) {
  const entries: [string, string][] = [
    ["Environment", config.app_env],
    ["LLM Provider", config.llm_provider],
    ["LLM Model", config.llm_model],
    ["Chat LLM Provider", config.chat_llm_provider],
    ["Chat LLM Model", config.chat_llm_model],
    ["Embedding Model", config.embedding_model],
    ["Embedding Device", config.embedding_device],
    ["SMILES Model", config.smiles_model],
    ["SMILES Device", config.smiles_device],
    ["Reranker Enabled", config.reranker_enabled ? "Yes" : "No"],
    ...(config.reranker_model ? [["Reranker Model", config.reranker_model] as [string, string]] : []),
    ...(config.reranker_device ? [["Reranker Device", config.reranker_device] as [string, string]] : []),
    ["Kafka Enabled", config.kafka_enabled ? "Yes" : "No"],
    ["Temporal Address", config.temporal_address],
    ["Temporal Max Activities", String(config.temporal_max_concurrent_activities)],
    ["Temporal Max LLM Activities", String(config.temporal_max_concurrent_llm_activities)],
    ["Qdrant URL", config.qdrant_url],
    ["Blob Storage", config.blob_base_url],
  ];

  return (
    <Card>
      <CardHeader title="Configuration" />
      <div className="grid grid-cols-1 gap-px overflow-hidden rounded-lg border border-border-default sm:grid-cols-2">
        {entries.map(([label, value]) => (
          <div
            key={label}
            className="flex items-baseline justify-between border-b border-border-default bg-surface-sunken/30 px-3 py-2 last:border-b-0 sm:[&:nth-last-child(2):nth-child(odd)]:border-b-0"
          >
            <span className="text-xs text-text-muted">{label}</span>
            <span className="ml-4 text-right text-xs font-medium text-text-primary">
              {value}
            </span>
          </div>
        ))}
      </div>
    </Card>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-border-default bg-surface-elevated p-4">
        <Skeleton width="12rem" height="1rem" />
        <div className="mt-1">
          <Skeleton width="20rem" height="0.75rem" />
        </div>
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="rounded-xl border border-border-default bg-surface-elevated p-5"
          >
            <Skeleton width="5rem" height="0.875rem" />
            <div className="mt-4">
              <Skeleton width="4rem" height="1.75rem" />
            </div>
          </div>
        ))}
      </div>
      {Array.from({ length: 3 }).map((_, i) => (
        <div
          key={i}
          className="rounded-xl border border-border-default bg-surface-elevated p-5"
        >
          <Skeleton width="10rem" height="1rem" />
          <div className="mt-4 space-y-3">
            {Array.from({ length: 4 }).map((_, j) => (
              <Skeleton key={j} width="100%" height="2.5rem" />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Re-embed Admin Action
// ---------------------------------------------------------------------------

const REEMBED_LABELS: Record<ReEmbedTarget, string> = {
  text: "Text Embeddings",
  smiles: "SMILES Embeddings",
  summaries: "Summary Embeddings",
};

function ReEmbedSection() {
  const reembedAll = useReembedAll();
  const [selected, setSelected] = useState<Set<ReEmbedTarget>>(
    () => new Set(ALL_REEMBED_TARGETS),
  );

  const toggle = (t: ReEmbedTarget) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next;
    });

  const allSelected = selected.size === ALL_REEMBED_TARGETS.length;

  const toggleAll = () =>
    setSelected(
      allSelected ? new Set() : new Set(ALL_REEMBED_TARGETS),
    );

  return (
    <Card>
      <CardHeader title="Admin Actions" />
      <div className="space-y-3">
        <div className="rounded-lg border border-border-default bg-surface-sunken/30 p-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-amber-500/10">
              <Layers className="h-4.5 w-4.5 text-amber-600 dark:text-amber-400" />
            </div>
            <div>
              <p className="text-sm font-medium text-text-primary">
                Re-embed Documents
              </p>
              <p className="text-xs text-text-muted">
                Triggers batch re-embedding for every artifact. Select which
                vector collections to rebuild.
              </p>
            </div>
          </div>

          {/* Collection selector */}
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={toggleAll}
              className="rounded-md border border-border-default px-2.5 py-1 text-xs font-medium text-text-muted transition-colors hover:bg-surface-sunken"
            >
              {allSelected ? "Deselect All" : "Select All"}
            </button>
            <span className="text-text-muted/40">|</span>
            {ALL_REEMBED_TARGETS.map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => toggle(t)}
                className={`rounded-md border px-2.5 py-1 text-xs font-medium transition-colors ${
                  selected.has(t)
                    ? "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-400"
                    : "border-border-default text-text-muted hover:bg-surface-sunken"
                }`}
              >
                {selected.has(t) && (
                  <Check className="mr-1 inline-block h-3 w-3" />
                )}
                {REEMBED_LABELS[t]}
              </button>
            ))}
          </div>

          {/* Trigger button */}
          <div className="mt-3 flex justify-end">
            <button
              type="button"
              onClick={() => reembedAll.mutate([...selected])}
              disabled={reembedAll.isPending || selected.size === 0}
              className="shrink-0 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-2 text-xs font-semibold text-amber-700 transition-colors hover:bg-amber-500/20 disabled:opacity-50 dark:text-amber-400"
            >
              {reembedAll.isPending ? "Triggering..." : "Trigger Re-embed"}
            </button>
          </div>
        </div>

        {reembedAll.isSuccess && (
          <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-4 py-3">
            <p className="text-xs font-medium text-emerald-700 dark:text-emerald-400">
              Started {reembedAll.data.triggered} re-embed workflow
              {reembedAll.data.triggered !== 1 ? "s" : ""} for{" "}
              {reembedAll.data.targets
                .map((t) => REEMBED_LABELS[t])
                .join(", ")}
              .
            </p>
          </div>
        )}

        {reembedAll.isError && (
          <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3">
            <p className="text-xs font-medium text-ds-error">
              Failed to trigger re-embed:{" "}
              {reembedAll.error instanceof Error
                ? reembedAll.error.message
                : "Unknown error"}
            </p>
          </div>
        )}
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function StatusPage() {
  const isAdmin = useAuthzHasRole("admin");
  const queryClient = useQueryClient();
  const [refreshInterval, setRefreshInterval] = useState<number | false>(30_000);
  const [copied, setCopied] = useState(false);

  const { data, isLoading, error, dataUpdatedAt } = useDetailedHealth(refreshInterval);

  const handleRefresh = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: queryKeys.health.all });
  }, [queryClient]);

  const handleCopyReport = useCallback(() => {
    if (!data) return;
    navigator.clipboard.writeText(JSON.stringify(data, null, 2)).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [data]);

  // -- access guard ---------------------------------------------------------

  if (!isAdmin) {
    return (
      <EmptyState
        icon={ShieldAlert}
        title="Access Denied"
        description="You need admin privileges to view system status."
      />
    );
  }

  // -- loading state --------------------------------------------------------

  if (isLoading) {
    return (
      <div>
        <PageHeader
          icon={Activity}
          title="System Status"
          subtitle="Infrastructure health, GPU status, and service connectivity"
        />
        <LoadingSkeleton />
      </div>
    );
  }

  // -- error state ----------------------------------------------------------

  if (error) {
    return (
      <div>
        <PageHeader
          icon={Activity}
          title="System Status"
          subtitle="Infrastructure health, GPU status, and service connectivity"
        />
        <EmptyState
          icon={AlertTriangle}
          title="Failed to load health status"
          description={
            error instanceof Error ? error.message : "An unknown error occurred."
          }
        />
      </div>
    );
  }

  if (!data) return null;

  // -- main render ----------------------------------------------------------

  return (
    <div>
      <PageHeader
        icon={Activity}
        title="System Status"
        subtitle="Infrastructure health, GPU status, and service connectivity"
        badge={
          <span className="flex items-center gap-1.5 text-xs font-medium text-text-muted">
            <span className="rounded bg-surface-sunken px-2 py-0.5">
              BE v{data.system.app_version}
            </span>
            <span className="rounded bg-surface-sunken px-2 py-0.5">
              FE v{process.env.APP_VERSION ?? "dev"}
            </span>
          </span>
        }
        actions={
          <div className="flex items-center gap-3">
            <SelectButton
              value={refreshInterval}
              onChange={(e) => setRefreshInterval(e.value)}
              options={REFRESH_OPTIONS}
              className="p-selectbutton-sm"
            />
            <button
              type="button"
              onClick={handleCopyReport}
              className="flex items-center gap-1.5 rounded-lg border border-border-default bg-surface-elevated px-3 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:bg-surface-sunken"
            >
              {copied ? (
                <Check className="h-3.5 w-3.5 text-ds-success" />
              ) : (
                <ClipboardCopy className="h-3.5 w-3.5" />
              )}
              {copied ? "Copied" : "Copy Report"}
            </button>
            <button
              type="button"
              onClick={handleRefresh}
              className="flex items-center gap-1.5 rounded-lg border border-border-default bg-surface-elevated px-3 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:bg-surface-sunken"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Refresh
            </button>
          </div>
        }
      />

      {/* ---- Overall Status Banner ---- */}
      <OverallBanner status={data.overall_status} />

      {/* ---- System Info Cards ---- */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <StatCard
          icon={Server}
          label="BE Version"
          value={data.system.app_version}
          accentColor="bg-blue-500/10"
        />
        <StatCard
          icon={Layers}
          label="FE Version"
          value={process.env.APP_VERSION ?? "dev"}
          accentColor="bg-indigo-500/10"
        />
        <StatCard
          icon={MonitorCog}
          label="Python"
          value={data.system.python_version}
          accentColor="bg-green-500/10"
        />
        <StatCard
          icon={HardDrive}
          label="Hostname"
          value={data.system.hostname}
          accentColor="bg-purple-500/10"
        />
        <StatCard
          icon={Activity}
          label="Uptime"
          value={fmtUptime(data.system.uptime_seconds)}
          accentColor="bg-amber-500/10"
        />
      </div>

      {/* ---- GPU & Compute ---- */}
      <div className="mt-6">
        <GpuSection
          gpu={data.gpu}
          configSmiles={data.config.smiles_device}
          configEmbedding={data.config.embedding_device}
        />
      </div>

      {/* ---- Workers Fleet ---- */}
      <div className="mt-6">
        <WorkersSection workers={data.workers} />
      </div>

      {/* ---- Services + Models (2-column) ---- */}
      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Service Dependencies */}
        <Card padding={false}>
          <div className="px-4 pt-4 pb-2">
            <CardHeader title="Service Dependencies" />
          </div>
          <div>
            {data.services.map((svc) => (
              <ServiceRow key={svc.name} service={svc} />
            ))}
          </div>
        </Card>

        {/* ML Models */}
        <Card padding={false}>
          <div className="px-4 pt-4 pb-2">
            <CardHeader title="ML Models" />
          </div>
          <div>
            {data.models.map((model) => (
              <ModelRow key={model.name} model={model} />
            ))}
          </div>
        </Card>
      </div>

      {/* ---- Configuration ---- */}
      <div className="mt-6">
        <ConfigSection config={data.config} />
      </div>

      {/* ---- Admin Actions ---- */}
      <div className="mt-6">
        <ReEmbedSection />
      </div>

      {/* ---- Footer: last checked ---- */}
      <p className="mt-4 text-right text-xs text-text-muted">
        Last checked:{" "}
        {dataUpdatedAt
          ? new Date(dataUpdatedAt).toLocaleTimeString()
          : "--"}
      </p>
    </div>
  );
}
