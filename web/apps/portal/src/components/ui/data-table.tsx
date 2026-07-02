"use client";

import { useEffect, useMemo, useState } from "react";
import {
  type ColumnDef, type ColumnFiltersState, type RowData, type SortingState,
  flexRender, getCoreRowModel, getFilteredRowModel, getPaginationRowModel,
  getSortedRowModel, useReactTable,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";

export type FilterMeta =
  | { variant: "text"; placeholder?: string }
  | { variant: "select"; options: { label: string; value: string }[]; placeholder?: string };

declare module "@tanstack/react-table" {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface ColumnMeta<TData extends RowData, TValue> {
    filter?: FilterMeta;
    headerClassName?: string;
    cellClassName?: string;
  }
}

const ALL = "__all__";

interface DataTableProps<TData> {
  columns: ColumnDef<TData, unknown>[];
  data: TData[];
  isLoading?: boolean;
  emptyMessage?: string;
  defaultSorting?: SortingState;
  pageSize?: number;
  pageSizeOptions?: number[];
  /** Hide the pagination footer and show every row (page size = row count). */
  hidePagination?: boolean;
}

export function DataTable<TData>({
  columns, data, isLoading = false, emptyMessage = "No results.",
  defaultSorting = [], pageSize = 20, pageSizeOptions = [10, 20, 50],
  hidePagination = false,
}: DataTableProps<TData>) {
  const [sorting, setSorting] = useState<SortingState>(defaultSorting);
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);

  const effectiveColumns = useMemo(
    () =>
      columns.map((c) => {
        const f = c.meta?.filter;
        if (!f || c.filterFn) return c;
        return { ...c, filterFn: (f.variant === "select" ? "equalsString" : "includesString") as ColumnDef<TData, unknown>["filterFn"] };
      }),
    [columns],
  );

  const table = useReactTable({
    data, columns: effectiveColumns,
    state: { sorting, columnFilters },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize: hidePagination ? Math.max(data.length, 1) : pageSize } },
  });

  // initialState only applies on mount — keep page size pinned to the full
  // row count as data loads/changes while hidePagination is on.
  useEffect(() => {
    if (hidePagination) table.setPageSize(Math.max(data.length, 1));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hidePagination, data.length]);

  const hasFilterRow = table.getAllLeafColumns().some((c) => c.columnDef.meta?.filter);
  const { pageIndex, pageSize: ps } = table.getState().pagination;
  const total = table.getFilteredRowModel().rows.length;

  return (
    <div className="overflow-hidden rounded-xl border border-border-default">
      <Table>
        <TableHeader>
          {table.getHeaderGroups().map((hg) => (
            <TableRow key={hg.id} className="bg-surface-sunken hover:bg-surface-sunken">
              {hg.headers.map((h) => {
                const canSort = h.column.getCanSort();
                const dir = h.column.getIsSorted();
                return (
                  <TableHead
                    key={h.id}
                    style={{ width: h.column.columnDef.size !== 150 ? h.column.columnDef.size : undefined }}
                    className={cn("text-xs font-semibold uppercase tracking-wider text-text-muted", h.column.columnDef.meta?.headerClassName)}
                    aria-sort={canSort ? (dir === "asc" ? "ascending" : dir === "desc" ? "descending" : "none") : undefined}
                  >
                    {h.isPlaceholder ? null : canSort ? (
                      <button
                        type="button"
                        className="inline-flex items-center gap-1 hover:text-text-primary"
                        onClick={h.column.getToggleSortingHandler()}
                      >
                        {flexRender(h.column.columnDef.header, h.getContext())}
                        {dir === "asc" ? <ArrowUp className="size-3" /> : dir === "desc" ? <ArrowDown className="size-3" /> : <ArrowUpDown className="size-3 opacity-40" />}
                      </button>
                    ) : (
                      flexRender(h.column.columnDef.header, h.getContext())
                    )}
                  </TableHead>
                );
              })}
            </TableRow>
          ))}
          {hasFilterRow && (
            <TableRow className="bg-surface hover:bg-surface">
              {table.getAllLeafColumns().map((col) => {
                const f = col.columnDef.meta?.filter;
                return (
                  <TableHead key={col.id} className="py-1.5">
                    {f?.variant === "text" && (
                      <Input
                        value={(col.getFilterValue() as string) ?? ""}
                        onChange={(e) => col.setFilterValue(e.target.value || undefined)}
                        placeholder={f.placeholder ?? "Search…"}
                        className="h-8"
                      />
                    )}
                    {f?.variant === "select" && (
                      <Select
                        value={(col.getFilterValue() as string) ?? ALL}
                        onValueChange={(v) => col.setFilterValue(v === ALL ? undefined : v)}
                      >
                        <SelectTrigger className="h-8"><SelectValue placeholder={f.placeholder ?? "All"} /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value={ALL}>All</SelectItem>
                          {f.options.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    )}
                  </TableHead>
                );
              })}
            </TableRow>
          )}
        </TableHeader>
        <TableBody>
          {isLoading ? (
            Array.from({ length: 5 }).map((_, i) => (
              <TableRow key={i}>
                {table.getAllLeafColumns().map((c) => (
                  <TableCell key={c.id}><Skeleton className="h-4 w-full" /></TableCell>
                ))}
              </TableRow>
            ))
          ) : table.getRowModel().rows.length === 0 ? (
            <TableRow>
              <TableCell colSpan={table.getAllLeafColumns().length} className="h-24 text-center text-text-muted">
                {emptyMessage}
              </TableCell>
            </TableRow>
          ) : (
            table.getRowModel().rows.map((row, i) => (
              <TableRow key={row.id} className={cn(i % 2 === 1 && "bg-surface-sunken/40")}>
                {row.getVisibleCells().map((cell) => (
                  <TableCell key={cell.id} className={cell.column.columnDef.meta?.cellClassName}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </TableCell>
                ))}
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
      {!hidePagination && (
        <div className="flex items-center justify-between border-t border-border-default px-3 py-2 text-xs text-text-muted">
          <span className="font-mono tabular-nums">
            {total === 0 ? "0" : `${pageIndex * ps + 1}–${Math.min((pageIndex + 1) * ps, total)}`} of {total}
          </span>
          <div className="flex items-center gap-2">
            <Select value={String(ps)} onValueChange={(v) => table.setPageSize(Number(v))}>
              <SelectTrigger className="h-7 w-[70px]"><SelectValue /></SelectTrigger>
              <SelectContent>
                {pageSizeOptions.map((n) => <SelectItem key={n} value={String(n)}>{n}</SelectItem>)}
              </SelectContent>
            </Select>
            <Button variant="ghost" size="icon" className="size-7" disabled={!table.getCanPreviousPage()} onClick={() => table.previousPage()} aria-label="Previous page">
              <ChevronLeft className="size-4" />
            </Button>
            <Button variant="ghost" size="icon" className="size-7" disabled={!table.getCanNextPage()} onClick={() => table.nextPage()} aria-label="Next page">
              <ChevronRight className="size-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
