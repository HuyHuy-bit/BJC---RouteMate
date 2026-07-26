import { useId, useMemo, useState } from "react";
import type { DailyRevenuePoint } from "../types";
import { fmtVnd } from "../lib/format";

/**
 * Daily revenue over the selected window.
 *
 * A single series, so there is deliberately no legend — the heading
 * already says what is plotted, and a one-swatch box would just
 * restate it. Values are carried by the axis, one direct label on the
 * peak, and the hover readout; a number on every point would be noise
 * nobody reads.
 *
 * Hand-rolled SVG rather than a charting library: the app already
 * ships a 749 kB map chunk, and this is one area chart. Recharts and
 * friends would cost more than the feature.
 */

const H = 180; // plot height
const PAD_L = 8;
const PAD_R = 8;
const PAD_T = 12;
const PAD_B = 22;

export default function RevenueChart({
  points,
}: {
  points: DailyRevenuePoint[];
}) {
  const gradientId = useId();
  const [hover, setHover] = useState<number | null>(null);

  const model = useMemo(() => {
    if (points.length === 0) return null;

    const max = Math.max(...points.map((p) => p.revenue_vnd), 1);
    // Round the top of the scale to something a person would say out
    // loud, so the axis ticks land on clean numbers.
    const step = Math.pow(10, Math.floor(Math.log10(max)));
    const top = Math.ceil(max / step) * step;

    const innerW = 100; // viewBox user units, scaled by preserveAspectRatio
    const x = (i: number) =>
      points.length === 1
        ? innerW / 2
        : PAD_L + (i / (points.length - 1)) * (innerW - PAD_L - PAD_R);
    const y = (v: number) => PAD_T + (1 - v / top) * (H - PAD_T - PAD_B);

    const line = points.map((p, i) => `${x(i)},${y(p.revenue_vnd)}`).join(" ");
    const area =
      `${x(0)},${H - PAD_B} ` + line + ` ${x(points.length - 1)},${H - PAD_B}`;

    const peakIndex = points.reduce(
      (best, p, i) => (p.revenue_vnd > points[best].revenue_vnd ? i : best),
      0
    );

    return { max, top, x, y, line, area, peakIndex, innerW };
  }, [points]);

  if (!model) {
    return (
      <p className="text-base text-faint py-8 text-center">
        Chưa có chuyến nào hoàn tất trong khoảng thời gian này.
      </p>
    );
  }

  const { top, x, y, line, area, peakIndex, innerW } = model;
  const active = hover !== null ? points[hover] : null;
  const axis = axisLabels(points[0].day, points[points.length - 1].day);

  return (
    <div>
      <div className="relative">
        {/* Its own positioning context, sized to the plot only — the
            markers below are placed as a percentage of THIS box, and
            the outer div also holds the axis labels and tooltip. */}
        <div className="relative h-44">
        <svg
          viewBox={`0 0 ${innerW} ${H}`}
          preserveAspectRatio="none"
          className="w-full h-full block"
          role="img"
          aria-label={`Doanh thu theo ngày, ${points.length} ngày. Cao nhất ${fmtVnd(
            points[peakIndex].revenue_vnd
          )}.`}
          onPointerLeave={() => setHover(null)}
          onPointerMove={(e) => {
            // The crosshair finds the X: snap to the nearest day so the
            // reader aims at a date, not at a 2px line.
            const box = e.currentTarget.getBoundingClientRect();
            const rel = ((e.clientX - box.left) / box.width) * innerW;
            let nearest = 0;
            let best = Infinity;
            for (let i = 0; i < points.length; i++) {
              const d = Math.abs(x(i) - rel);
              if (d < best) {
                best = d;
                nearest = i;
              }
            }
            setHover(nearest);
          }}
        >
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              {/* ~10% wash, never a saturated block. */}
              <stop offset="0%" stopColor="var(--brand)" stopOpacity="0.16" />
              <stop offset="100%" stopColor="var(--brand)" stopOpacity="0.01" />
            </linearGradient>
          </defs>

          {/* Recessive grid: hairline, solid, one step off the surface. */}
          {[0, 0.5, 1].map((f) => (
            <line
              key={f}
              x1={PAD_L}
              x2={innerW - PAD_R}
              y1={y(top * f)}
              y2={y(top * f)}
              stroke="var(--border)"
              strokeWidth="0.5"
              vectorEffect="non-scaling-stroke"
            />
          ))}

          <polygon points={area} fill={`url(#${gradientId})`} />
          <polyline
            points={line}
            fill="none"
            stroke="var(--brand)"
            strokeWidth="2"
            strokeLinejoin="round"
            strokeLinecap="round"
            vectorEffect="non-scaling-stroke"
          />

          {hover !== null && (
            <line
              x1={x(hover)}
              x2={x(hover)}
              y1={PAD_T}
              y2={H - PAD_B}
              stroke="var(--border-strong)"
              strokeWidth="1"
              vectorEffect="non-scaling-stroke"
            />
          )}

        </svg>

        {/* Markers are HTML, not SVG.
            `preserveAspectRatio="none"` is what lets the line stretch to
            any container width, but it stretches everything drawn inside
            it — an SVG <circle> came out as a flat orange ellipse.
            A line distorted along x is still an honest picture of the
            data; a dot is not, it just looks broken. Positioning these
            in percentages keeps them round at every width. */}
        {[peakIndex, ...(hover !== null && hover !== peakIndex ? [hover] : [])].map(
          (i, n) => (
            <span
              key={`${i}-${n}`}
              aria-hidden="true"
              className="absolute w-2 h-2 rounded-full bg-brand ring-2 ring-surface -translate-x-1/2 -translate-y-1/2 pointer-events-none"
              style={{
                left: `${(x(i) / innerW) * 100}%`,
                top: `${(y(points[i].revenue_vnd) / H) * 100}%`,
              }}
            />
          )
        )}
        </div>

        {/* Values live in text tokens, never the series color.
            The middle label is the PEAK — an actual day's takings —
            not the axis ceiling it used to show. The ceiling is a
            rounded-up number that appears nowhere in the data, so
            printing it invited reading it as a real figure. */}
        <div className="flex justify-between text-2xs text-faint tnum mt-1">
          <span>{axis.start}</span>
          <span>Cao nhất {fmtVnd(points[peakIndex].revenue_vnd)}</span>
          <span>{axis.end}</span>
        </div>

        {active && (
          <div
            className="absolute top-0 left-0 right-0 flex justify-center pointer-events-none"
            aria-live="polite"
          >
            <div className="rounded border border-line bg-surface shadow-md px-2.5 py-1.5">
              {/* Value leads, label follows — the reader already knows
                  the series and wants the number. */}
              <div className="text-base font-semibold tnum text-ink">
                {fmtVnd(active.revenue_vnd)}
              </div>
              <div className="text-2xs text-faint tnum">
                {fmtDay(active.day)} · {active.trips} chuyến
              </div>
            </div>
          </div>
        )}
      </div>

      {/* The table view: every value reachable without hovering, which
          is what lets the chart label selectively. */}
      <details className="mt-3">
        <summary className="text-2xs text-muted cursor-pointer hover:text-ink">
          Xem dạng bảng
        </summary>
        <div className="overflow-x-auto mt-2 max-h-56 overflow-y-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="text-2xs text-faint">
                <th scope="col" className="font-medium py-1 pr-4">Ngày</th>
                <th scope="col" className="font-medium py-1 pr-4 text-right">Chuyến</th>
                <th scope="col" className="font-medium py-1 text-right">Doanh thu</th>
              </tr>
            </thead>
            <tbody>
              {[...points].reverse().map((p) => (
                <tr key={p.day} className="border-t border-line">
                  <td className="py-1 pr-4 text-xs tnum">{fmtDay(p.day)}</td>
                  <td className="py-1 pr-4 text-xs tnum text-right">{p.trips}</td>
                  <td className="py-1 text-xs tnum text-right">
                    {fmtVnd(p.revenue_vnd)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}

/** "2026-07-26" -> "26/07". The year is redundant across a 30-day window. */
function fmtDay(iso: string): string {
  const [, m, d] = iso.split("-");
  return `${d}/${m}`;
}

/**
 * The two ends of the x-axis, saying the month only when it changes.
 *
 * "26/07 … 27/07" repeats a month the reader already has; within one
 * month the second number is the only new information. Across a month
 * boundary both are spelled out, because then it genuinely differs.
 */
function axisLabels(first: string, last: string): { start: string; end: string } {
  const [, fm] = first.split("-");
  const [, lm] = last.split("-");
  return fm === lm
    ? { start: first.split("-")[2], end: fmtDay(last) }
    : { start: fmtDay(first), end: fmtDay(last) };
}
