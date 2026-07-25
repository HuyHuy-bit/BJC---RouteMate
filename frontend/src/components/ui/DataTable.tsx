import { ChevronRight } from "lucide-react";
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
  onRowClick,
  rowActionLabel,
}: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  /** Describes the table for screen readers; visually hidden. */
  caption?: string;
  minWidth?: number;
  showTotals?: boolean;
  totalsLabel?: string;
  /**
   * Opens the row's detail view. Clicking anywhere on the row triggers
   * this, but that is a mouse affordance only — the real control is the
   * button rendered in the trailing column, which is what keyboard and
   * screen reader users reach. A <tr> cannot be made properly
   * focusable or announced as a control, so putting the semantics on a
   * button and treating the row click as a shortcut is the honest way
   * round rather than bolting role="button" onto a table row.
   */
  onRowClick?: (row: T) => void;
  /** Accessible name for that button, e.g. "Chi tiết chuyến 98A-12345". */
  rowActionLabel?: (row: T) => string;
}) {
  const interactive = Boolean(onRowClick);
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
            {interactive && (
              <th scope="col" className="w-touch px-2 py-2">
                <span className="sr-only">Xem chi tiết</span>
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={rowKey(row)}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={[
                "border-t border-line hover:bg-sunken transition-colors",
                interactive ? "cursor-pointer" : "",
              ].join(" ")}
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
              {interactive && (
                <td className="px-2 py-1.5 text-right">
                  <button
                    type="button"
                    onClick={(e) => {
                      // The row handler would otherwise fire a second
                      // time for the same click.
                      e.stopPropagation();
                      onRowClick?.(row);
                    }}
                    aria-label={rowActionLabel?.(row) ?? "Xem chi tiết"}
                    className="w-touch h-touch inline-flex items-center justify-center rounded text-faint hover:text-ink hover:bg-sunken transition-colors"
                  >
                    <ChevronRight size={16} aria-hidden="true" />
                  </button>
                </td>
              )}
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
              {interactive && <td aria-hidden="true" />}
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  );
}
