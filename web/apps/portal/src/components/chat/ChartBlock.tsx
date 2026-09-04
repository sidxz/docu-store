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
                domain={["dataMin", "dataMax"]}
                tick={{ fontSize: 11 }}
                label={{ value: spec.x_label, position: "insideBottom", offset: -12, fontSize: 11 }}
              />
              <YAxis
                type="number"
                dataKey={spec.series[0]?.name ?? "y"}
                tick={{ fontSize: 11 }}
                label={{ value: spec.y_label, angle: -90, position: "insideLeft", fontSize: 11 }}
              />
              <Tooltip />
              {spec.series.map((s, i) => (
                <Scatter
                  key={s.name}
                  name={s.name}
                  data={s.points.map(([x, y]) => ({ x, [s.name]: y }))}
                  fill={colorFor(spec, s.name, i)}
                />
              ))}
              {spec.series.length > 1 && (
                <Legend verticalAlign="top" wrapperStyle={{ fontSize: 11 }} />
              )}
            </ScatterChart>
          ) : (
            <BarChart data={rows} margin={{ top: 8, right: 12, bottom: 20, left: 4 }}>
              <CartesianGrid strokeOpacity={0.25} vertical={false} />
              <XAxis
                dataKey="x"
                tickFormatter={tickFor}
                tick={{ fontSize: 11 }}
                label={{ value: spec.x_label, position: "insideBottom", offset: -12, fontSize: 11 }}
              />
              <YAxis
                tick={{ fontSize: 11 }}
                label={{ value: spec.y_label, angle: -90, position: "insideLeft", fontSize: 11 }}
              />
              <Tooltip labelFormatter={(x) => tickFor(Number(x))} />
              {spec.series.map((s, i) => (
                <Bar
                  key={s.name}
                  dataKey={s.name}
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
              {spec.series.length > 1 && (
                <Legend verticalAlign="top" wrapperStyle={{ fontSize: 11 }} />
              )}
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>

      {spec.notes?.length ? (
        // Stance is a judgement, and a reader must be able to overrule it.
        // Collapsed: the fragments are the appeal, not the finding.
        <details className="mt-2">
          <summary className="text-[0.6875rem] text-text-muted cursor-pointer">Verdicts</summary>
          <ul>
            {spec.notes.map((note) => (
              <li key={note} className="text-[0.6875rem] leading-relaxed text-text-muted">
                {note}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
      {/* footnote, partial_x and source_query stay on the block for the
          record but are not drawn: to a reader they look like debug output. */}
    </figure>
  );
}
