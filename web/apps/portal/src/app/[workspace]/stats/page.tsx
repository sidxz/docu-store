"use client";

import { useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  BarChart3,
  Activity,
  Database,
  AlertTriangle,
  ShieldAlert,
  Cpu,
  Clock,
  MessageSquare,
  Search,
  Shield,
  Coins,
  FileText,
  CircleHelp,
} from "lucide-react";
import { Skeleton } from "primereact/skeleton";
import { SelectButton } from "primereact/selectbutton";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { useAuthzHasRole } from "@sentinel-auth/react";

import { PageHeader } from "@/components/ui/PageHeader";
import { StatCard } from "@/components/ui/StatCard";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import {
  useWorkflowStats,
  usePipelineStats,
  useVectorStats,
  useTokenUsageStats,
  useChatLatencyStats,
  useSearchQualityStats,
  useGroundingStats,
  useKnowledgeGaps,
  useCitationFrequency,
} from "@/hooks/use-stats";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtDuration(seconds: number): string {
  return `${(seconds / 60).toFixed(1)} min`;
}

function fmtNumber(n: number): string {
  return n.toLocaleString();
}

function cleanWorkflowName(name: string): string {
  return name.replace(/Workflow$/i, "").replace(/([a-z])([A-Z])/g, "$1 $2");
}

function fmtDate(iso: string | null): string {
  if (!iso) return "--";
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function truncate(text: string | null, max: number): string {
  if (!text) return "--";
  return text.length > max ? `${text.slice(0, max)}...` : text;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function LoadingSkeleton() {
  return (
    <div className="space-y-6">
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
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 rounded-xl border border-border-default bg-surface-elevated p-5">
          <Skeleton width="10rem" height="1rem" />
          <div className="mt-4">
            <Skeleton width="100%" height="16rem" />
          </div>
        </div>
        <div className="rounded-xl border border-border-default bg-surface-elevated p-5">
          <Skeleton width="10rem" height="1rem" />
          <div className="mt-4 space-y-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} width="100%" height="1.5rem" />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function StatsPage() {
  const isAdmin = useAuthzHasRole("admin");

  const {
    data: workflowData,
    isLoading: wfLoading,
    error: wfError,
  } = useWorkflowStats();
  const {
    data: pipelineData,
    isLoading: plLoading,
    error: plError,
  } = usePipelineStats();
  const {
    data: vectorData,
    isLoading: vecLoading,
    error: vecError,
  } = useVectorStats();

  const isLoading = wfLoading || plLoading || vecLoading;
  const error = wfError ?? plError ?? vecError;

  // -- derived stats --------------------------------------------------------

  const totalCompleted = useMemo(
    () =>
      workflowData?.completed.reduce((sum, w) => sum + w.count, 0) ?? 0,
    [workflowData],
  );

  const totalActive = useMemo(
    () => workflowData?.active.reduce((sum, w) => sum + w.count, 0) ?? 0,
    [workflowData],
  );

  const totalVectorPoints = useMemo(
    () =>
      vectorData?.collections.reduce((sum, c) => sum + c.points_count, 0) ??
      0,
    [vectorData],
  );

  const totalFailures = workflowData?.recent_failures.length ?? 0;

  // -- chart data -----------------------------------------------------------

  const chartData = useMemo(
    () =>
      (workflowData?.completed ?? []).map((w) => ({
        name: cleanWorkflowName(w.workflow_type),
        avg: +(w.avg_duration_seconds / 60).toFixed(2),
        p95: +(w.p95_duration_seconds / 60).toFixed(2),
        count: w.count,
      })),
    [workflowData],
  );

  // -- access guard ---------------------------------------------------------

  if (!isAdmin) {
    return (
      <EmptyState
        icon={ShieldAlert}
        title="Access Denied"
        description="You need admin privileges to view pipeline statistics."
      />
    );
  }

  // -- loading state --------------------------------------------------------

  if (isLoading) {
    return (
      <div>
        <PageHeader
          icon={BarChart3}
          title="Pipeline Stats"
          subtitle="Workflow performance, processing pipeline, and vector store health"
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
          icon={BarChart3}
          title="Pipeline Stats"
          subtitle="Workflow performance, processing pipeline, and vector store health"
        />
        <EmptyState
          icon={AlertTriangle}
          title="Failed to load stats"
          description={
            error instanceof Error ? error.message : "An unknown error occurred."
          }
        />
      </div>
    );
  }

  // -- main render ----------------------------------------------------------

  return (
    <div>
      <PageHeader
        icon={BarChart3}
        title="Pipeline Stats"
        subtitle="Workflow performance, processing pipeline, and vector store health"
      />

      {/* ---- Top stat cards ---- */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          icon={Activity}
          label="Completed Workflows"
          value={fmtNumber(totalCompleted)}
          accentColor="bg-blue-500/10"
        />
        <StatCard
          icon={Clock}
          label="Active Running"
          value={fmtNumber(totalActive)}
          accentColor="bg-green-500/10"
        />
        <StatCard
          icon={Database}
          label="Total Vector Points"
          value={fmtNumber(totalVectorPoints)}
          accentColor="bg-amber-500/10"
        />
        <StatCard
          icon={AlertTriangle}
          label="Recent Failures"
          value={fmtNumber(totalFailures)}
          accentColor="bg-red-500/10"
        />
      </div>

      {/* ---- Workflow Duration Chart + Pipeline Funnel ---- */}
      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Workflow Duration Chart (2/3) */}
        <Card className="lg:col-span-2" padding={false}>
          <div className="p-5">
            <CardHeader title="Workflow Duration (minutes)" />
            {chartData.length === 0 ? (
              <p className="py-8 text-center text-sm text-text-muted">
                No completed workflows yet.
              </p>
            ) : (
              <ResponsiveContainer width="100%" height={Math.max(chartData.length * 48, 200)}>
                <BarChart
                  data={chartData}
                  layout="vertical"
                  margin={{ top: 0, right: 24, bottom: 0, left: 8 }}
                >
                  <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                  <XAxis
                    type="number"
                    tick={{ fontSize: 12, fill: "var(--color-text-muted)" }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    type="category"
                    dataKey="name"
                    width={140}
                    tick={{ fontSize: 12, fill: "var(--color-text-secondary)" }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "var(--color-surface-elevated)",
                      border: "1px solid var(--color-border-default)",
                      borderRadius: "0.5rem",
                      fontSize: "0.75rem",
                    }}
                    formatter={(value, name) => [
                      `${Number(value).toFixed(2)} min`,
                      name === "avg" ? "Avg" : "P95",
                    ]}
                    labelFormatter={(label) => String(label)}
                  />
                  <Bar
                    dataKey="avg"
                    fill="#3b82f6"
                    radius={[0, 4, 4, 0]}
                    name="avg"
                  />
                  <Bar
                    dataKey="p95"
                    fill="#f59e0b"
                    radius={[0, 4, 4, 0]}
                    name="p95"
                  />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </Card>

        {/* Processing Pipeline Funnel (1/3) */}
        <Card>
          <CardHeader title="Processing Pipeline" />
          {pipelineData ? (
            <div className="space-y-4">
              <FunnelRow
                label="Total Artifacts"
                count={pipelineData.total_artifacts}
                total={pipelineData.total_artifacts}
                color="#3b82f6"
                isAbsolute
              />
              <FunnelRow
                label="Total Pages"
                count={pipelineData.total_pages}
                total={pipelineData.total_pages}
                color="#3b82f6"
                isAbsolute
              />
              <FunnelRow
                label="With Text"
                count={pipelineData.pages_with_text}
                total={pipelineData.total_pages}
                color="#10b981"
              />
              <FunnelRow
                label="With Summary"
                count={pipelineData.pages_with_summary}
                total={pipelineData.total_pages}
                color="#f59e0b"
              />
              <FunnelRow
                label="With Compounds"
                count={pipelineData.pages_with_compounds}
                total={pipelineData.total_pages}
                color="#8b5cf6"
              />
              <FunnelRow
                label="With Tags"
                count={pipelineData.pages_with_tags}
                total={pipelineData.total_pages}
                color="#ec4899"
              />
            </div>
          ) : (
            <p className="py-8 text-center text-sm text-text-muted">
              No pipeline data available.
            </p>
          )}
        </Card>
      </div>

      {/* ---- Vector Store + Recent Failures ---- */}
      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Vector Store Collections */}
        <Card padding={false}>
          <div className="p-5">
            <CardHeader title="Vector Store Collections" />
            {vectorData && vectorData.collections.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border-default text-left">
                      <th className="pb-2 pr-4 font-medium text-text-muted">
                        Collection
                      </th>
                      <th className="pb-2 pr-4 text-right font-medium text-text-muted">
                        Points
                      </th>
                      <th className="pb-2 pr-4 text-right font-medium text-text-muted">
                        Vectors
                      </th>
                      <th className="pb-2 font-medium text-text-muted">
                        Status
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border-subtle">
                    {vectorData.collections.map((c) => (
                      <tr key={c.collection_name}>
                        <td className="py-2.5 pr-4 font-medium text-text-primary">
                          {c.collection_name}
                        </td>
                        <td className="py-2.5 pr-4 text-right tabular-nums text-text-secondary">
                          {fmtNumber(c.points_count)}
                        </td>
                        <td className="py-2.5 pr-4 text-right tabular-nums text-text-secondary">
                          {fmtNumber(c.indexed_vectors_count)}
                        </td>
                        <td className="py-2.5">
                          <span
                            className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                              c.status === "green"
                                ? "bg-green-500/10 text-green-500"
                                : "bg-amber-500/10 text-amber-500"
                            }`}
                          >
                            {c.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="py-8 text-center text-sm text-text-muted">
                No vector collections found.
              </p>
            )}
          </div>
        </Card>

        {/* Recent Failures */}
        <Card padding={false}>
          <div className="p-5">
            <CardHeader title="Recent Failures" />
            {workflowData && workflowData.recent_failures.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border-default text-left">
                      <th className="pb-2 pr-4 font-medium text-text-muted">
                        Workflow
                      </th>
                      <th className="pb-2 pr-4 font-medium text-text-muted">
                        Type
                      </th>
                      <th className="pb-2 pr-4 font-medium text-text-muted">
                        Started
                      </th>
                      <th className="pb-2 font-medium text-text-muted">
                        Error
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border-subtle">
                    {workflowData.recent_failures.map((f) => (
                      <tr key={f.workflow_id}>
                        <td
                          className="max-w-[8rem] truncate py-2.5 pr-4 font-mono text-xs text-text-secondary"
                          title={f.workflow_id}
                        >
                          {f.workflow_id.slice(0, 12)}...
                        </td>
                        <td className="py-2.5 pr-4 text-text-primary">
                          {cleanWorkflowName(f.workflow_type)}
                        </td>
                        <td className="py-2.5 pr-4 whitespace-nowrap text-text-secondary">
                          {fmtDate(f.started_at)}
                        </td>
                        <td
                          className="max-w-[14rem] truncate py-2.5 text-xs text-red-400"
                          title={f.failure_message ?? undefined}
                        >
                          {truncate(f.failure_message, 60)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="py-8 text-center text-sm text-text-muted">
                No recent failures. All clear!
              </p>
            )}
          </div>
        </Card>
      </div>

      {/* ---- Model Configuration ---- */}
      {vectorData && (
        <div className="mt-6">
          <Card>
            <CardHeader title="Model Configuration" />
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
              <ModelInfoBlock
                icon={Cpu}
                title="Embedding Model"
                items={vectorData.embedding_model}
              />
              {vectorData.reranker ? (
                <ModelInfoBlock
                  icon={Cpu}
                  title="Reranker"
                  items={vectorData.reranker}
                />
              ) : (
                <div className="rounded-lg border border-border-default p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <Cpu className="h-4 w-4 text-text-muted" />
                    <span className="text-sm font-medium text-text-primary">
                      Reranker
                    </span>
                  </div>
                  <p className="text-xs text-text-muted">Disabled</p>
                </div>
              )}
            </div>
          </Card>
        </div>
      )}

      {/* ════════════════════════════════════════════════════════════════════ */}
      {/* Analytics & Quality Section                                        */}
      {/* ════════════════════════════════════════════════════════════════════ */}

      <AnalyticsSection />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Analytics & Quality Section
// ---------------------------------------------------------------------------

const PERIOD_OPTIONS = [
  { label: "Day", value: "day" },
  { label: "Week", value: "week" },
  { label: "Month", value: "month" },
];

function AnalyticsSection() {
  const { workspace } = useParams<{ workspace: string }>();
  const [period, setPeriod] = useState("week");

  const { data: tokenData } = useTokenUsageStats(period);
  const { data: latencyData } = useChatLatencyStats(period);
  const { data: searchData } = useSearchQualityStats(period);
  const { data: groundingData } = useGroundingStats(period);
  const { data: gapsData } = useKnowledgeGaps(period);
  const { data: citationData } = useCitationFrequency(period);

  // Token chart: aggregate by date (sum across modes)
  const tokenChartData = useMemo(() => {
    if (!tokenData) return [];
    const byDate = new Map<string, { date: string; tokens: number; messages: number }>();
    for (const b of tokenData.buckets) {
      const existing = byDate.get(b.date) ?? { date: b.date, tokens: 0, messages: 0 };
      existing.tokens += b.total_tokens;
      existing.messages += b.message_count;
      byDate.set(b.date, existing);
    }
    return Array.from(byDate.values()).sort((a, b) => a.date.localeCompare(b.date));
  }, [tokenData]);

  // Latency chart data
  const latencyChartData = useMemo(
    () =>
      (latencyData?.steps ?? []).map((s) => ({
        name: s.step_name.replace(/_/g, " "),
        avg: Math.round(s.avg_ms),
        p95: Math.round(s.p95_ms),
      })),
    [latencyData],
  );

  return (
    <div className="mt-10">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold text-text-primary">
            Analytics & Quality
          </h2>
          <p className="text-sm text-text-muted">
            Chat quality, search health, and LLM usage metrics
          </p>
        </div>
        <SelectButton
          value={period}
          options={PERIOD_OPTIONS}
          onChange={(e) => { if (e.value) setPeriod(e.value); }}
        />
      </div>

      {/* ---- Top-level analytics stat cards ---- */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          icon={Coins}
          label="Total Tokens"
          value={tokenData ? fmtNumber(tokenData.total_tokens) : "--"}
          accentColor="bg-amber-500/10"
        />
        <StatCard
          icon={MessageSquare}
          label="Chat Messages"
          value={tokenData ? fmtNumber(tokenData.total_messages) : "--"}
          accentColor="bg-blue-500/10"
        />
        <StatCard
          icon={Search}
          label="Total Searches"
          value={searchData ? fmtNumber(searchData.total_searches) : "--"}
          accentColor="bg-purple-500/10"
        />
        <StatCard
          icon={Shield}
          label="Grounded Rate"
          value={
            groundingData
              ? `${(groundingData.overall_grounded_rate * 100).toFixed(0)}%`
              : "--"
          }
          accentColor="bg-green-500/10"
        />
      </div>

      {/* ---- Token Usage Chart + Search Quality ---- */}
      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Token Usage over time (2/3) */}
        <Card className="lg:col-span-2" padding={false}>
          <div className="p-5">
            <CardHeader title="Token Usage (daily)" />
            {tokenChartData.length === 0 ? (
              <p className="py-8 text-center text-sm text-text-muted">
                No chat messages in this period.
              </p>
            ) : (
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={tokenChartData} margin={{ top: 0, right: 16, bottom: 0, left: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 11, fill: "var(--color-text-muted)" }}
                    tickFormatter={(v: string) => v.slice(5)} // MM-DD
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{ fontSize: 11, fill: "var(--color-text-muted)" }}
                    axisLine={false}
                    tickLine={false}
                    tickFormatter={(v: number) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : String(v)}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "var(--color-surface-elevated)",
                      border: "1px solid var(--color-border-default)",
                      borderRadius: "0.5rem",
                      fontSize: "0.75rem",
                    }}
                    formatter={(value, name) => [
                      fmtNumber(Number(value)),
                      name === "tokens" ? "Tokens" : "Messages",
                    ]}
                  />
                  <Bar dataKey="tokens" fill="#f59e0b" radius={[4, 4, 0, 0]} name="tokens" />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </Card>

        {/* Search Quality (1/3) */}
        <Card>
          <CardHeader title="Search Quality" />
          {searchData && searchData.modes.length > 0 ? (
            <div className="space-y-4">
              {searchData.modes.map((m) => (
                <div key={m.search_mode}>
                  <div className="flex items-center justify-between text-sm mb-1">
                    <span className="text-text-secondary capitalize">
                      {m.search_mode}
                    </span>
                    <span className="text-xs font-mono text-text-muted">
                      {m.total_searches} queries
                    </span>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="flex-1">
                      <div className="h-2 w-full overflow-hidden rounded-full bg-surface-sunken">
                        <div
                          className="h-full rounded-full bg-red-400 transition-all"
                          style={{ width: `${m.zero_result_rate * 100}%` }}
                        />
                      </div>
                    </div>
                    <span className="text-xs tabular-nums text-text-muted w-16 text-right">
                      {(m.zero_result_rate * 100).toFixed(1)}% empty
                    </span>
                  </div>
                  <p className="text-[11px] text-text-muted mt-0.5">
                    Avg {m.avg_result_count.toFixed(1)} results per query
                  </p>
                </div>
              ))}
              <div className="pt-2 border-t border-border-subtle">
                <div className="flex justify-between text-xs">
                  <span className="text-text-muted">Overall zero-result rate</span>
                  <span className="font-medium text-text-secondary">
                    {(searchData.overall_zero_result_rate * 100).toFixed(1)}%
                  </span>
                </div>
              </div>
            </div>
          ) : (
            <p className="py-8 text-center text-sm text-text-muted">
              No search activity in this period.
            </p>
          )}
        </Card>
      </div>

      {/* ---- Chat Latency + Grounding ---- */}
      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Pipeline Step Latency */}
        <Card padding={false}>
          <div className="p-5">
            <CardHeader title="Chat Pipeline Step Latency (ms)" />
            {latencyChartData.length === 0 ? (
              <p className="py-8 text-center text-sm text-text-muted">
                No chat messages in this period.
              </p>
            ) : (
              <>
                <ResponsiveContainer width="100%" height={Math.max(latencyChartData.length * 40, 160)}>
                  <BarChart
                    data={latencyChartData}
                    layout="vertical"
                    margin={{ top: 0, right: 24, bottom: 0, left: 8 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" opacity={0.15} />
                    <XAxis
                      type="number"
                      tick={{ fontSize: 11, fill: "var(--color-text-muted)" }}
                      axisLine={false}
                      tickLine={false}
                      tickFormatter={(v: number) => v >= 1000 ? `${(v / 1000).toFixed(1)}s` : `${v}`}
                    />
                    <YAxis
                      type="category"
                      dataKey="name"
                      width={120}
                      tick={{ fontSize: 11, fill: "var(--color-text-secondary)" }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "var(--color-surface-elevated)",
                        border: "1px solid var(--color-border-default)",
                        borderRadius: "0.5rem",
                        fontSize: "0.75rem",
                      }}
                      formatter={(value, name) => [
                        `${fmtNumber(Number(value))} ms`,
                        name === "avg" ? "Avg" : "P95",
                      ]}
                    />
                    <Bar dataKey="avg" fill="#3b82f6" radius={[0, 4, 4, 0]} name="avg" />
                    <Bar dataKey="p95" fill="#f59e0b" radius={[0, 4, 4, 0]} name="p95" />
                  </BarChart>
                </ResponsiveContainer>
                {latencyData && (
                  <div className="mt-3 flex gap-4 text-xs text-text-muted border-t border-border-subtle pt-3">
                    <span>
                      Overall avg:{" "}
                      <span className="font-medium text-text-secondary">
                        {fmtNumber(Math.round(latencyData.overall_avg_ms))} ms
                      </span>
                    </span>
                    <span>
                      Overall P95:{" "}
                      <span className="font-medium text-text-secondary">
                        {fmtNumber(Math.round(latencyData.overall_p95_ms))} ms
                      </span>
                    </span>
                  </div>
                )}
              </>
            )}
          </div>
        </Card>

        {/* Grounding Distribution */}
        <Card>
          <CardHeader title="Grounding Quality" />
          {groundingData && groundingData.modes.length > 0 ? (
            <div className="space-y-4">
              {groundingData.modes.map((m) => (
                <div key={m.mode} className="rounded-lg border border-border-subtle p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium text-text-primary capitalize">
                      {m.mode || "unknown"}
                    </span>
                    <span className="text-xs font-mono text-text-muted">
                      {m.total_messages} msgs
                    </span>
                  </div>
                  {/* Stacked bar: grounded vs not */}
                  <div className="flex h-3 w-full overflow-hidden rounded-full bg-surface-sunken">
                    <div
                      className="h-full bg-green-500 transition-all"
                      style={{ width: `${m.grounded_rate * 100}%` }}
                      title={`Grounded: ${m.grounded_count}`}
                    />
                    <div
                      className="h-full bg-red-400 transition-all"
                      style={{ width: `${(1 - m.grounded_rate) * 100}%` }}
                      title={`Not grounded: ${m.not_grounded_count}`}
                    />
                  </div>
                  <div className="flex justify-between mt-1.5 text-[11px] text-text-muted">
                    <span>
                      Grounded:{" "}
                      <span className="text-green-500 font-medium">
                        {(m.grounded_rate * 100).toFixed(0)}%
                      </span>
                    </span>
                    <span>
                      Avg confidence:{" "}
                      <span className="text-text-secondary font-medium">
                        {(m.avg_confidence * 100).toFixed(0)}%
                      </span>
                    </span>
                  </div>
                </div>
              ))}
              <div className="pt-2 border-t border-border-subtle">
                <div className="flex justify-between text-xs">
                  <span className="text-text-muted">Overall grounded rate</span>
                  <span className="font-medium text-green-500">
                    {(groundingData.overall_grounded_rate * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="flex justify-between text-xs mt-1">
                  <span className="text-text-muted">Overall avg confidence</span>
                  <span className="font-medium text-text-secondary">
                    {(groundingData.overall_avg_confidence * 100).toFixed(0)}%
                  </span>
                </div>
              </div>
            </div>
          ) : (
            <p className="py-8 text-center text-sm text-text-muted">
              No grounding data in this period.
            </p>
          )}
        </Card>
      </div>

      {/* ---- Knowledge Gaps + Citation Frequency ---- */}
      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Knowledge Gaps */}
        <Card>
          <CardHeader title="Knowledge Gaps" />
          <p className="text-xs text-text-muted -mt-2 mb-4">
            Entities detected in chat queries where the corpus couldn&apos;t provide grounded answers
          </p>
          {gapsData && gapsData.gaps.length > 0 ? (
            <div className="space-y-2.5">
              {gapsData.gaps.map((g) => (
                <div key={`${g.entity_text}-${g.entity_type}`} className="flex items-center gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <CircleHelp className="h-3.5 w-3.5 text-amber-500 flex-shrink-0" />
                      <span className="text-sm font-medium text-text-primary truncate">
                        {g.entity_text}
                      </span>
                      <span className="text-[10px] rounded-full bg-surface-sunken px-1.5 py-0.5 text-text-muted flex-shrink-0">
                        {g.entity_type}
                      </span>
                    </div>
                    <div className="mt-1 flex h-1.5 w-full overflow-hidden rounded-full bg-surface-sunken">
                      <div
                        className="h-full rounded-full bg-amber-500 transition-all"
                        style={{ width: `${g.gap_rate * 100}%` }}
                      />
                    </div>
                  </div>
                  <div className="text-right flex-shrink-0 w-20">
                    <span className="text-xs tabular-nums font-medium text-amber-500">
                      {(g.gap_rate * 100).toFixed(0)}% gap
                    </span>
                    <p className="text-[10px] text-text-muted tabular-nums">
                      {g.gap_count}/{g.query_count} queries
                    </p>
                  </div>
                </div>
              ))}
              <div className="pt-2 border-t border-border-subtle flex justify-between text-xs text-text-muted">
                <span>
                  {gapsData.total_gap_entities} gap entities / {gapsData.total_unique_entities} total
                </span>
              </div>
            </div>
          ) : (
            <p className="py-8 text-center text-sm text-text-muted">
              No knowledge gaps detected — all queried entities are well covered.
            </p>
          )}
        </Card>

        {/* Citation Frequency */}
        <Card>
          <CardHeader title="Citation Frequency" />
          <p className="text-xs text-text-muted -mt-2 mb-4">
            Which documents are cited most and least in chat answers
          </p>
          {citationData && citationData.most_cited.length > 0 ? (
            <div className="space-y-4">
              {/* Most cited */}
              <div>
                <h4 className="text-xs font-medium text-text-muted uppercase tracking-wider mb-2">
                  Most Cited
                </h4>
                <div className="space-y-1.5">
                  {citationData.most_cited.map((a, i) => (
                    <Link
                      key={a.artifact_id}
                      href={`/${workspace}/documents/${a.artifact_id}`}
                      className="flex items-center gap-2 group/cite rounded-md -mx-1 px-1 py-0.5 hover:bg-surface-hover transition-colors"
                    >
                      <span className="text-[10px] font-mono text-text-muted w-4 text-right">{i + 1}</span>
                      <FileText className="h-3.5 w-3.5 text-blue-500 flex-shrink-0" />
                      <span className="text-sm text-text-primary truncate flex-1 group-hover/cite:text-accent" title={a.artifact_title ?? a.artifact_id}>
                        {a.artifact_title ?? a.artifact_id.slice(0, 12)}
                      </span>
                      <span className="text-xs tabular-nums font-medium text-text-secondary flex-shrink-0">
                        {a.citation_count}
                      </span>
                      <span className="text-[10px] text-text-muted flex-shrink-0">
                        ({a.unique_conversation_count} conv)
                      </span>
                    </Link>
                  ))}
                </div>
              </div>

              {/* Least cited */}
              {citationData.least_cited.length > 0 && (
                <div>
                  <h4 className="text-xs font-medium text-text-muted uppercase tracking-wider mb-2">
                    Least Cited
                  </h4>
                  <div className="space-y-1.5">
                    {citationData.least_cited.map((a) => (
                      <Link
                        key={a.artifact_id}
                        href={`/${workspace}/documents/${a.artifact_id}`}
                        className="flex items-center gap-2 group/cite rounded-md -mx-1 px-1 py-0.5 hover:bg-surface-hover transition-colors"
                      >
                        <FileText className="h-3.5 w-3.5 text-text-muted flex-shrink-0 ml-5" />
                        <span className="text-sm text-text-secondary truncate flex-1 group-hover/cite:text-accent" title={a.artifact_title ?? a.artifact_id}>
                          {a.artifact_title ?? a.artifact_id.slice(0, 12)}
                        </span>
                        <span className="text-xs tabular-nums text-text-muted flex-shrink-0">
                          {a.citation_count}
                        </span>
                      </Link>
                    ))}
                  </div>
                </div>
              )}

              {/* Never cited */}
              {citationData.never_cited.length > 0 && (
                <div>
                  <h4 className="text-xs font-medium text-amber-500 uppercase tracking-wider mb-2">
                    Never Cited
                  </h4>
                  <div className="space-y-1.5">
                    {citationData.never_cited.map((a) => (
                      <Link
                        key={a.artifact_id}
                        href={`/${workspace}/documents/${a.artifact_id}`}
                        className="flex items-center gap-2 group/cite rounded-md -mx-1 px-1 py-0.5 hover:bg-surface-hover transition-colors"
                      >
                        <FileText className="h-3.5 w-3.5 text-amber-500/60 flex-shrink-0 ml-5" />
                        <span className="text-sm text-text-muted truncate flex-1 group-hover/cite:text-accent" title={a.artifact_title ?? a.artifact_id}>
                          {a.artifact_title ?? a.artifact_id.slice(0, 12)}
                        </span>
                      </Link>
                    ))}
                    {citationData.never_cited_count > citationData.never_cited.length && (
                      <p className="text-[11px] text-text-muted ml-5">
                        + {citationData.never_cited_count - citationData.never_cited.length} more
                      </p>
                    )}
                  </div>
                </div>
              )}

              {/* Summary */}
              <div className="pt-2 border-t border-border-subtle flex justify-between text-xs text-text-muted">
                <span>
                  {citationData.total_artifacts - citationData.never_cited_count} / {citationData.total_artifacts} documents cited
                </span>
                {citationData.never_cited_count > 0 && (
                  <span className="text-amber-500">
                    {citationData.never_cited_count} never cited
                  </span>
                )}
              </div>
            </div>
          ) : (
            <p className="py-8 text-center text-sm text-text-muted">
              No citation data in this period.
            </p>
          )}
        </Card>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Funnel row
// ---------------------------------------------------------------------------

function FunnelRow({
  label,
  count,
  total,
  color,
  isAbsolute = false,
}: {
  label: string;
  count: number;
  total: number;
  color: string;
  isAbsolute?: boolean;
}) {
  const pct = total > 0 ? (count / total) * 100 : 0;

  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-sm">
        <span className="text-text-secondary">{label}</span>
        <span className="font-medium tabular-nums text-text-primary">
          {fmtNumber(count)}
          {!isAbsolute && total > 0 && (
            <span className="ml-1 text-xs text-text-muted">
              ({pct.toFixed(0)}%)
            </span>
          )}
        </span>
      </div>
      {!isAbsolute && (
        <div className="h-2 w-full overflow-hidden rounded-full bg-surface-sunken">
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{ width: `${pct}%`, backgroundColor: color }}
          />
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Model info block
// ---------------------------------------------------------------------------

function ModelInfoBlock({
  icon: Icon,
  title,
  items,
}: {
  icon: typeof Cpu;
  title: string;
  items: Record<string, string | number>;
}) {
  return (
    <div className="rounded-lg border border-border-default p-4">
      <div className="flex items-center gap-2 mb-3">
        <Icon className="h-4 w-4 text-text-muted" />
        <span className="text-sm font-medium text-text-primary">{title}</span>
      </div>
      <dl className="space-y-1.5">
        {Object.entries(items).map(([key, value]) => (
          <div key={key} className="flex items-center justify-between text-xs">
            <dt className="text-text-muted capitalize">
              {key.replace(/_/g, " ")}
            </dt>
            <dd className="font-medium text-text-secondary">{String(value)}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
