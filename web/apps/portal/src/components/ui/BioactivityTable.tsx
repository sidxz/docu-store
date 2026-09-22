import type { Bioactivity } from "@docu-store/types";

export function BioactivityTable({ activities }: { activities: Bioactivity[] }) {
  // Most values name no protein (cell assays) or no organism (enzyme assays), so each
  // column appears only when some value has one.
  const showTarget = activities.some((a) => a.target);
  const showStrain = activities.some((a) => a.strain);
  return (
    <div className="mt-2.5 overflow-hidden rounded-md border border-border-subtle">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-border-subtle bg-surface-sunken/50">
            <th className="px-2 py-1.5 text-left text-[10px] font-semibold uppercase tracking-wider text-text-muted">Endpoint</th>
            {showTarget && (
              <th className="px-2 py-1.5 text-left text-[10px] font-semibold uppercase tracking-wider text-text-muted">Target</th>
            )}
            <th className="px-2 py-1.5 text-left text-[10px] font-semibold uppercase tracking-wider text-text-muted">Assay</th>
            {showStrain && (
              <th className="px-2 py-1.5 text-left text-[10px] font-semibold uppercase tracking-wider text-text-muted">Strain</th>
            )}
            <th className="px-2 py-1.5 text-left text-[10px] font-semibold uppercase tracking-wider text-text-muted">Value</th>
            <th className="px-2 py-1.5 text-left text-[10px] font-semibold uppercase tracking-wider text-text-muted">Source</th>
          </tr>
        </thead>
        <tbody>
          {activities.map((a, j) => (
            <tr key={j} className="border-b border-border-subtle last:border-0">
              <td className="px-2 py-1.5 font-mono font-medium text-text-primary">{a.assay_type || "—"}</td>
              {showTarget && <td className="px-2 py-1.5 text-text-primary">{a.target ?? "—"}</td>}
              {/* A partner drug means the value is for the combination, not the compound alone. */}
              <td className="px-2 py-1.5 text-text-primary">
                {[a.assay, a.combination && `with ${a.combination}`].filter(Boolean).join(" · ") || "—"}
              </td>
              {showStrain && <td className="px-2 py-1.5 text-text-primary">{a.strain ?? "—"}</td>}
              <td className="px-2 py-1.5 font-mono text-text-primary">{a.value}{a.unit ? ` ${a.unit}` : ""}</td>
              <td className="px-2 py-1.5 text-text-muted">{a.raw_text}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
