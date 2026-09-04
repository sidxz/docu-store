"use client";

import type { ChartSpec } from "@docu-store/types";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

/** Fixed hue order. Assigned by series index and never cycled, so a series
 *  keeps its colour when a sibling is absent. Validated for colour-vision
 *  separation against both theme surfaces. */
const SERIES_COLORS = ["#0090A0", "#BA5215", "#3F4FA5", "#7D8A2E"];

/** Stance is polarity, not identity: two poles and a neutral middle, in the
 *  fixed order the classifier emits. */
const STANCE_COLORS: Record<string, string> = {
  supports: "#0090A0",
  mixed: "#8B9490",
  refutes: "#BA5215",
  none: "#B8BFB7",
};

/** The classifier's vocabulary is not the reader's. `none` is the largest
 *  bucket by design and read as a bug when the legend prints it raw. */
const STANCE_NAMES: Record<string, string> = { none: "no position" };

/** recharts hardcodes light-mode greys — tooltip background #fff, axis stroke
 *  #666 — and its legend colours each label with the series fill, which makes
 *  the neutral stance labels near-invisible. All three need explicit tokens. */
const TOOLTIP_STYLE = {
  backgroundColor: "var(--ds-surface-elevated)",
  border: "1px solid var(--ds-border)",
  borderRadius: "0.375rem",
  color: "var(--ds-text-primary)",
  fontSize: 11,
} as const;
const TOOLTIP_LABEL_STYLE = { color: "var(--ds-text-primary)" } as const;
const TOOLTIP_ITEM_STYLE = { color: "var(--ds-text-secondary)" } as const;
const AXIS_TICK = { fontSize: 11, fill: "var(--ds-text-muted)" } as const;
const AXIS_LABEL = { fontSize: 11, fill: "var(--ds-text-muted)" } as const;
const LEGEND_STYLE = { fontSize: 11, color: "var(--ds-text-secondary)" } as const;

function displayName(spec: ChartSpec, name: string): string {
  return spec.panel === "stance" ? (STANCE_NAMES[name.toLowerCase()] ?? name) : name;
}

function colorFor(spec: ChartSpec, name: string, index: number): string {
  if (spec.panel === "stance") {
    return STANCE_COLORS[name.toLowerCase()] ?? SERIES_COLORS[index % SERIES_COLORS.length];
  }
  return SERIES_COLORS[index % SERIES_COLORS.length];
}

/** Recharts wants one row per x with a column per series. The spec carries one
 *  point list per series, because that is the shape the tool produces. */
function toRows(spec: ChartSpec): Record<string, number>[] {
  const byX = new Map<number, Record<string, number>>();
  for (const s of spec.series) {
    for (const [x, y] of s.points) {
      const row = byX.get(x) ?? { x };
      row[s.name] = y;
      byX.set(x, row);
    }
  }
  return [...byX.values()].sort((a, b) => a.x - b.x);
}

export function ChartBlock({ spec }: { spec: ChartSpec }) {
  const rows = toRows(spec);
  const isScatter = spec.panel === "landmarks";
  const stacked = spec.panel === "stance" || spec.panel === "evidence_mix";
  // Shown whenever there is more than one colour to name. Stance and
  // evidence_mix routinely collapse to one series — a well-supported claim is
  // all `supports` — and an unlabelled coloured bar names nothing.
  const showLegend = spec.series.length > 1 || stacked;
  const partialDrawn =
    spec.partial_x != null && rows.some((r) => r.x === spec.partial_x);

  const tickFor = (x: number) =>
    spec.categories ? (spec.categories[x] ?? String(x)) : String(x);

  return (
    <figure className="my-1 rounded-lg border border-border-default bg-surface-elevated p-3">
      <figcaption className="mb-2 text-xs font-medium text-text-primary">
        {spec.title}
      </figcaption>

      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          {isScatter ? (
            <ScatterChart margin={{ top: 8, right: 12, bottom: 20, left: 4 }}>
              <CartesianGrid strokeOpacity={0.25} />
              <XAxis
                type="number"
                dataKey="x"
                /* `name`, not a labelFormatter: ScatterChart forces item-type
                   tooltips, where labelFormatter never runs and the axis's
                   dataKey leaks through as the row label ("x : 2005"). */
                name={spec.x_label}
                domain={["dataMin", "dataMax"]}
                tick={AXIS_TICK}
                label={{ value: spec.x_label, position: "insideBottom", offset: -12, ...AXIS_LABEL }}
              />
              <YAxis
                type="number"
                dataKey={spec.series[0]?.name ?? "y"}
                name={spec.y_label}
                tick={AXIS_TICK}
                label={{ value: spec.y_label, angle: -90, position: "insideLeft", ...AXIS_LABEL }}
              />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                labelStyle={TOOLTIP_LABEL_STYLE}
                itemStyle={TOOLTIP_ITEM_STYLE}
                cursor={{ strokeOpacity: 0.3 }}
                /* The panel exists to surface canonical papers, so hovering a
                   point has to name one. */
                formatter={(value, name, item) => {
                  const label = (item?.payload as { label?: string } | undefined)?.label;
                  return label ? [`${value} — ${label}`, name] : [value, name];
                }}
              />
              {spec.series.map((s, i) => (
                <Scatter
                  key={s.name}
                  name={s.name}
                  data={s.points.map(([x, y], p) => ({
                    x,
                    [s.name]: y,
                    label: s.labels?.[p],
                  }))}
                  fill={colorFor(spec, s.name, i)}
                />
              ))}
              {spec.series.length > 1 && (
                <Legend verticalAlign="top" wrapperStyle={LEGEND_STYLE} />
              )}
            </ScatterChart>
          ) : (
            <BarChart data={rows} margin={{ top: 8, right: 12, bottom: 20, left: 4 }}>
              <CartesianGrid strokeOpacity={0.25} vertical={false} />
              <XAxis
                dataKey="x"
                tickFormatter={tickFor}
                tick={AXIS_TICK}
                label={{ value: spec.x_label, position: "insideBottom", offset: -12, ...AXIS_LABEL }}
              />
              <YAxis
                tick={AXIS_TICK}
                label={{ value: spec.y_label, angle: -90, position: "insideLeft", ...AXIS_LABEL }}
              />
              <Tooltip
                labelFormatter={(x) => tickFor(Number(x))}
                contentStyle={TOOLTIP_STYLE}
                labelStyle={TOOLTIP_LABEL_STYLE}
                itemStyle={TOOLTIP_ITEM_STYLE}
                cursor={{ fillOpacity: 0.08 }}
              />
              {spec.series.map((s, i) => (
                <Bar
                  key={s.name}
                  dataKey={s.name}
                  name={displayName(spec, s.name)}
                  stackId={stacked ? "a" : undefined}
                  fill={colorFor(spec, s.name, i)}
                  radius={[2, 2, 0, 0]}
                >
                  {/* The partial year is drawn faint. Without it the chart
                      always ends on a decline that is an artefact of the
                      calendar, not of the field. */}
                  {rows.map((r) => (
                    <Cell
                      key={`${s.name}-${r.x}`}
                      fillOpacity={spec.partial_x != null && r.x === spec.partial_x ? 0.4 : 1}
                    />
                  ))}
                </Bar>
              ))}
              {showLegend && (
                /* itemSorter off: recharts alphabetises by default, which
                   scrambles the deliberate supports/refutes/mixed polarity
                   order into mixed/none/refutes/supports. */
                <Legend
                  verticalAlign="top"
                  wrapperStyle={LEGEND_STYLE}
                  itemSorter={() => 0}
                />
              )}
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>

      {spec.notes?.length ? (
        // Stance is a judgement, and a reader must be able to overrule it.
        // Collapsed: the fragments are the appeal, not the finding.
        <details className="mt-2">
          <summary className="text-[0.6875rem] text-text-muted cursor-pointer">
            {spec.panel === "stance" ? "Verdicts" : "Papers"}
          </summary>
          <ul>
            {/* Keyed by index: Europe PMC indexes a preprint and its version of
                record separately, so two notes can be byte-identical. */}
            {spec.notes.map((note, i) => (
              <li key={i} className="text-[0.6875rem] leading-relaxed text-text-muted">
                {note}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
      {spec.footnote || partialDrawn ? (
        <p className="mt-2 text-[0.6875rem] leading-relaxed text-text-muted">
          {spec.footnote}
          {/* The faint bar is meaningless unless it is named: unexplained it
              reads as a real decline rather than an incomplete year. */}
          {partialDrawn ? ` ${tickFor(Number(spec.partial_x))} is still in progress.` : ""}
        </p>
      ) : null}
      {/* source_query stays on the block but is not drawn. */}
    </figure>
  );
}
