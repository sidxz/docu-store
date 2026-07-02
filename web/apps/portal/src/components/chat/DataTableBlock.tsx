"use client";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

interface DataTableBlockProps {
  headers: string[];
  rows: string[][];
}

export function DataTableBlock({ headers, rows }: DataTableBlockProps) {
  return (
    <div className="my-3 overflow-x-auto rounded-lg border border-border-default">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            {headers.map((h) => (
              <TableHead key={h} className="px-3 py-1.5 text-sm">
                {h}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row, idx) => (
            <TableRow key={idx} className={cn(idx % 2 === 1 && "bg-surface-sunken/40")}>
              {headers.map((h, i) => (
                <TableCell key={h} className="px-3 py-1.5 text-sm whitespace-normal">
                  {row[i] ?? ""}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
