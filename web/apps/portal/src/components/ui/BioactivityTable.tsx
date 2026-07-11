import type { Bioactivity } from "@docu-store/types";

export function BioactivityTable({ activities }: { activities: Bioactivity[] }) {
  return (
    <div className="mt-2.5 overflow-hidden rounded-md border border-border-subtle">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-border-subtle bg-surface-sunken/50">
            <th className="px-2 py-1.5 text-left text-[10px] font-semibold uppercase tracking-wider text-text-muted">Assay</th>
            <th className="px-2 py-1.5 text-left text-[10px] font-semibold uppercase tracking-wider text-text-muted">Value</th>
            <th className="px-2 py-1.5 text-left text-[10px] font-semibold uppercase tracking-wider text-text-muted">Source</th>
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
  );
}
