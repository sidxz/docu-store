"use client";

import { DataTable } from "primereact/datatable";
import { Column } from "primereact/column";

interface DataTableBlockProps {
  headers: string[];
  rows: string[][];
}

export function DataTableBlock({ headers, rows }: DataTableBlockProps) {
  const data = rows.map((row, idx) => {
    const obj: Record<string, string> = { __idx: String(idx) };
    headers.forEach((h, i) => {
      obj[h] = row[i] ?? "";
    });
    return obj;
  });

  return (
    <div className="my-3 rounded-lg overflow-hidden border border-surface-200 dark:border-surface-700">
      <DataTable value={data} size="small" stripedRows scrollable>
        {headers.map((h) => (
          <Column key={h} field={h} header={h} />
        ))}
      </DataTable>
    </div>
  );
}
