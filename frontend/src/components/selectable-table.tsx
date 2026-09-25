"use client";

import {
  createColumnHelper,
  rowSelectionFeature,
  tableFeatures,
  useTable,
  type ColumnDef,
  type RowSelectionState,
} from "@tanstack/react-table";
import { useMemo, useState, type ReactNode } from "react";

import { cn } from "@/lib/utils";

export const selectionFeatures = tableFeatures({ rowSelectionFeature });
type Features = typeof selectionFeatures;

type Row = { id: number };

/** Column helper bound to the selectable table: `const col = columnsFor<Vacancy>()`. */
export const columnsFor = <T extends Row>() => createColumnHelper<Features, T>();

type Props<T extends Row> = {
  data: T[];
  columns: ColumnDef<Features, T, any>[]; // eslint-disable-line @typescript-eslint/no-explicit-any -- TanStack's own signature
  /** The bar shown over the table while rows are selected: gets the ids and a way to clear the selection. */
  actions: (ids: number[], clear: () => void) => ReactNode;
  empty: ReactNode;
  onRowClick?: (row: T) => void;
  /** Selection is cleared whenever this changes, e.g. the filter. */
  resetKey?: unknown;
  maxHeight?: number;
  label: string;
};

/** A table with checkboxes (Shift-click selects a range) and a bulk action bar. */
export function SelectableTable<T extends Row>({ data, columns, actions, empty, onRowClick, resetKey, maxHeight = 560, label }: Props<T>) {
  const allColumns = useMemo(() => {
    const col = columnsFor<T>();
    return [
      col.display({
        id: "select",
        header: ({ table }) => (
          <input
            type="checkbox"
            aria-label="Выбрать все"
            className="size-4 cursor-pointer accent-foreground"
            checked={table.getIsAllRowsSelected()}
            ref={(el) => {
              if (el) el.indeterminate = table.getIsSomeRowsSelected();
            }}
            onChange={table.getToggleAllRowsSelectedHandler()}
          />
        ),
        cell: ({ row }) => (
          <input
            type="checkbox"
            aria-label="Выбрать"
            className="size-4 cursor-pointer accent-foreground"
            checked={row.getIsSelected()}
            onChange={() => undefined}
            onClick={row.getToggleSelectedHandler()}
          />
        ),
      }),
      ...columns,
    ];
  }, [columns]);

  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  // a new filter means a new list: drop the selection (React's «adjust state on prop change», no effect needed)
  const [shownKey, setShownKey] = useState(resetKey);
  if (shownKey !== resetKey) {
    setShownKey(resetKey);
    setRowSelection({});
  }

  const table = useTable({
    features: selectionFeatures,
    data,
    columns: allColumns,
    getRowId: (r: T) => String(r.id),
    state: { rowSelection },
    onRowSelectionChange: setRowSelection,
  });

  const selected = Object.keys(rowSelection)
    .filter((k) => rowSelection[k])
    .map(Number);
  const clear = () => setRowSelection({});

  return (
    <div>
      {selected.length > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-2 rounded-xl bg-foreground px-3 py-2.5 text-background [&_button]:border-background/30 [&_button]:bg-transparent [&_button]:text-background [&_button:hover]:border-brand [&_button:hover]:text-brand">
          <b className="mr-auto">Выбрано: {selected.length}</b>
          {actions(selected, clear)}
        </div>
      )}
      <div className="overflow-auto rounded-xl border bg-card" style={{ maxHeight }}>
        <table className="w-full border-collapse text-sm" aria-label={label}>
          <thead>
            {table.getHeaderGroups().map((group) => (
              <tr key={group.id}>
                {group.headers.map((header) => (
                  <th
                    key={header.id}
                    className={cn(
                      "sticky top-0 z-[1] border-b bg-card px-3.5 py-2.5 text-left text-[12.5px] font-semibold text-muted-foreground",
                      header.id === "select" && "w-9",
                      (header.column.columnDef.meta as { className?: string } | undefined)?.className,
                    )}
                  >
                    {header.isPlaceholder ? null : <table.FlexRender header={header} />}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr
                key={row.id}
                data-selected={row.getIsSelected() || undefined}
                className={cn(
                  "border-b border-muted last:border-0 hover:bg-surface-2 data-[selected]:bg-brand-soft",
                  onRowClick && "cursor-pointer",
                )}
                onClick={(e) => {
                  if (!onRowClick || (e.target as HTMLElement).closest("input,a,button")) return;
                  onRowClick(row.original);
                }}
              >
                {row.getAllCells().map((cell) => (
                  <td
                    key={cell.id}
                    className={cn(
                      "px-3.5 py-2.5 align-middle",
                      (cell.column.columnDef.meta as { className?: string } | undefined)?.className,
                    )}
                  >
                    <table.FlexRender cell={cell} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {!data.length && empty}
      </div>
    </div>
  );
}
