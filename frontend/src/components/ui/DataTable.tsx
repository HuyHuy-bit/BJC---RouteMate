import type { ReactNode } from "react";

export interface Column<T> {
  /** Header text. Keep it short — these are scanned, not read. */
  header: string;
  /** Cell contents for one row. */
  cell: (row: T) => ReactNode;
  /** Right-align numeric columns so magnitudes line up by length. */
  align?: "left" | "right";
  /** Applied to both the header and every cell in the column. */
  className?: string;
  /** Contents of this column's cell in the totals row, if any. */
  total?: ReactNode;
}

/**
 * Tabular data, rendered as an actual table.
 *
 * Extracted from FleetStatusTable's hand-rolled markup, which was
 * already doing the right things — scoped headers, its own horizontal
 * scroll container — so that HistoryPage could stop rendering columnar
 * data as a grid of cards. Comparison across rows is the entire job of
 * a history screen, and cards force serial reading: you cannot run your
 * eye down a column that doesn't exist.
 *
 * Wide content scrolls inside this container, never the page body.
 */
export default function DataTable<T>({
  columns,
  rows,
  rowKey,
  caption,
  minWidth = 640,
  showTotals = false,
  totalsLabel = "Tổng",
}: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  /** Describes the table for screen readers; visually hidden. */
  caption?: string;
  minWidth?: number;
  showTotals?: boolean;
  totalsLabel?: string;
}) {
  return (
    <div className="overflow-x-auto">
      <table
        className="w-full text-left border-collapse"
        style={{ minWidth }}
      >
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead>
          <tr className="text-2xs text-faint">
            {columns.map((c) => (
              <th
                key={c.header}
                scope="col"
                className={[
                  "font-medium px-4 py-2 whitespace-nowrap",
                  c.align === "right" ? "text-right" : "",
                  c.className ?? "",
                ].join(" ")}
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={rowKey(row)}
              className="border-t border-line hover:bg-sunken transition-colors"
            >
              {columns.map((c) => (
                <td
                  key={c.header}
                  className={[
                    "px-4 py-2.5 text-sm",
                    c.align === "right" ? "text-right" : "",
                    c.className ?? "",
                  ].join(" ")}
                >
                  {c.cell(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
        {showTotals && rows.length > 0 && (
          <tfoot>
            <tr className="border-t-2 border-line-strong bg-sunken">
              {columns.map((c, i) => (
                <td
                  key={c.header}
                  className={[
                    "px-4 py-2.5 text-sm font-semibold",
                    c.align === "right" ? "text-right" : "",
                    c.className ?? "",
                  ].join(" ")}
                >
                  {c.total ?? (i === 0 ? totalsLabel : null)}
                </td>
              ))}
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  );
}
