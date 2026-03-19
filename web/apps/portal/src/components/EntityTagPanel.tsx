import Link from "next/link";
import type { components } from "@docu-store/api-client";
import { Card } from "@/components/ui/Card";

type TagMentionItem = NonNullable<
  components["schemas"]["ArtifactResponse"]["tag_mentions"]
>[number];

type Bioactivity = {
  assay_type: string;
  value: string;
  unit: string;
  raw_text: string;
};

const ENTITY_STYLE: Record<string, { label: string; dot: string; pill: string }> = {
  compound_name: { label: "Compounds", dot: "bg-emerald-500", pill: "border-emerald-500/30" },
  target: { label: "Targets", dot: "bg-amber-500", pill: "border-amber-500/30" },
  disease: { label: "Diseases", dot: "bg-rose-500", pill: "border-rose-500/30" },
};
const FALLBACK_STYLE = { label: "", dot: "bg-zinc-400", pill: "border-zinc-400/30" };

interface EntityTagPanelProps {
  tagMentions: TagMentionItem[];
  /** Used to build page links: /{workspace}/documents/{artifactId}/pages/{pageId} */
  workspace: string;
  artifactId: string;
}

function groupTags(tagMentions: TagMentionItem[]) {
  const compounds: TagMentionItem[] = [];
  const grouped = new Map<string, TagMentionItem[]>();
  for (const tm of tagMentions) {
    const key = tm.entity_type ?? "other";
    if (key === "compound_name") {
      compounds.push(tm);
    } else {
      const arr = grouped.get(key);
      if (arr) arr.push(tm);
      else grouped.set(key, [tm]);
    }
  }
  return { compounds, grouped };
}

function SourceBadges({
  sources,
  workspace,
  artifactId,
}: {
  sources: { page_id: string; page_index: number }[] | undefined | null;
  workspace: string;
  artifactId: string;
}) {
  if (!sources || sources.length === 0) return null;
  const sorted = [...sources].sort((a, b) => a.page_index - b.page_index);
  return (
    <span className="inline-flex items-center gap-1">
      {sorted.map((s) => (
        <Link
          key={s.page_id}
          href={`/${workspace}/documents/${artifactId}/pages/${s.page_id}`}
          className="flex h-5 min-w-[20px] items-center justify-center rounded-md bg-surface-sunken px-1.5 text-[10px] font-medium tabular-nums text-text-muted transition-colors hover:bg-accent-light hover:text-accent-text"
        >
          {s.page_index + 1}
        </Link>
      ))}
    </span>
  );
}

function SourcePillSuffix({
  sources,
  workspace,
  artifactId,
}: {
  sources: { page_id: string; page_index: number }[] | undefined | null;
  workspace: string;
  artifactId: string;
}) {
  if (!sources || sources.length === 0) return null;
  const sorted = [...sources].sort((a, b) => a.page_index - b.page_index);
  return (
    <span className="flex items-center gap-0.5 border-l border-border-subtle py-1 pl-2 pr-2.5">
      {sorted.map((s) => (
        <Link
          key={s.page_id}
          href={`/${workspace}/documents/${artifactId}/pages/${s.page_id}`}
          className="rounded px-1 text-[10px] font-medium tabular-nums text-text-muted transition-colors hover:text-accent-text"
        >
          {s.page_index + 1}
        </Link>
      ))}
    </span>
  );
}

export function EntityTagPanel({ tagMentions, workspace, artifactId }: EntityTagPanelProps) {
  const { compounds, grouped } = groupTags(tagMentions);

  return (
    <Card>
      <h3 className="mb-4 text-sm font-medium text-text-secondary">Entities</h3>
      <div className="space-y-5">
        {compounds.length > 0 && (
          <div>
            <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-text-muted">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
              Compounds
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              {compounds.map((tm, i) => {
                const params = tm.additional_model_params as Record<string, unknown> | undefined;
                const activities = params?.bioactivities as Bioactivity[] | undefined;
                const synonyms = params?.synonyms as string | undefined;
                const sources = (tm as Record<string, unknown>).sources as
                  | { page_id: string; page_index: number }[]
                  | undefined;
                return (
                  <div
                    key={`${tm.tag}-${i}`}
                    className="rounded-lg border border-emerald-500/20 bg-emerald-500/[0.03] p-3"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-baseline gap-2 overflow-hidden">
                        <span className="text-sm font-semibold text-text-primary">{tm.tag}</span>
                        {synonyms && (
                          <span className="truncate text-xs text-text-muted">aka {synonyms}</span>
                        )}
                      </div>
                      <SourceBadges sources={sources} workspace={workspace} artifactId={artifactId} />
                    </div>
                    {activities && activities.length > 0 && (
                      <div className="mt-2.5 overflow-hidden rounded-md border border-border-subtle">
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="border-b border-border-subtle bg-surface-sunken/50">
                              <th className="px-2 py-1.5 text-left font-medium text-text-muted">Assay</th>
                              <th className="px-2 py-1.5 text-left font-medium text-text-muted">Value</th>
                              <th className="px-2 py-1.5 text-left font-medium text-text-muted">Source</th>
                            </tr>
                          </thead>
                          <tbody>
                            {activities.map((a, j) => (
                              <tr key={j} className="border-b border-border-subtle last:border-0">
                                <td className="px-2 py-1.5 font-mono font-medium text-text-primary">{a.assay_type}</td>
                                <td className="px-2 py-1.5 font-mono text-text-primary">{a.value}{a.unit ? ` ${a.unit}` : ""}</td>
                                <td className="px-2 py-1.5 text-text-muted">{a.raw_text}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
        {[...grouped.entries()].map(([entityType, tags]) => {
          const style = ENTITY_STYLE[entityType] ?? FALLBACK_STYLE;
          return (
            <div key={entityType}>
              <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-text-muted">
                <span className={`h-1.5 w-1.5 rounded-full ${style.dot}`} />
                {style.label || entityType.replace(/_/g, " ")}
              </div>
              <div className="flex flex-wrap gap-2">
                {tags.map((tm, i) => {
                  const sources = (tm as Record<string, unknown>).sources as
                    | { page_id: string; page_index: number }[]
                    | undefined;
                  const hasSources = sources && sources.length > 0;
                  return (
                    <span
                      key={`${tm.tag}-${i}`}
                      className={`inline-flex items-center rounded-md border ${style.pill} bg-surface-elevated text-sm`}
                    >
                      <span className={`py-1 pl-3 font-medium text-text-primary ${hasSources ? "pr-2" : "pr-3"}`}>
                        {tm.tag}
                      </span>
                      {hasSources && (
                        <SourcePillSuffix sources={sources} workspace={workspace} artifactId={artifactId} />
                      )}
                    </span>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
