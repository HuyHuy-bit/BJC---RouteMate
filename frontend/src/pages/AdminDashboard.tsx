import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ArrowLeft, Car, TrendingUp, Users } from "lucide-react";
import { api } from "../lib/api";
import { fmtVnd } from "../lib/format";
import AppShell from "../components/layout/AppShell";
import RevenueChart from "../components/RevenueChart";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import QueryState from "../components/ui/QueryState";
import Select from "../components/ui/Select";
import Skeleton from "../components/ui/Skeleton";

/**
 * The business view — revenue, its trend, collection health, and how
 * the operation performed.
 *
 * Deliberately a separate page from the dispatch board rather than a
 * section on it. Requirements §2 draws a hard line: dispatchers run
 * the operation and see no money at all, admins own the financial
 * picture. Two audiences, two screens.
 */

const RANGES = [
  { value: "7", label: "7 ngày qua" },
  { value: "30", label: "30 ngày qua" },
  { value: "90", label: "3 tháng qua" },
];

export default function AdminDashboard() {
  const [days, setDays] = useState("30");

  const query = useQuery({
    queryKey: ["admin-dashboard", days],
    queryFn: () => api.admin.dashboard(Number(days)),
  });

  return (
    <AppShell
      title="Tổng quan kinh doanh"
      subtitle="Doanh thu và hiệu quả vận hành"
      width="wide"
      actions={
        <Link to="/">
          <Button variant="ghost" iconLeft={<ArrowLeft size={15} aria-hidden="true" />}>
            Về bảng điều phối
          </Button>
        </Link>
      }
    >
      <QueryState
        query={query}
        errorTitle="Không tải được số liệu kinh doanh"
        skeleton={
          <div className="space-y-5">
            <Skeleton className="h-24 w-full rounded-lg" />
            <Skeleton className="h-72 w-full rounded-lg" />
          </div>
        }
      >
        {(d) => (
          <div className="space-y-5">
            {/* Four headline numbers are a KPI row, not a bar chart —
                there is nothing to compare them against on an axis. */}
            <Card className="grid grid-cols-2 lg:grid-cols-4 divide-y lg:divide-y-0 lg:divide-x divide-line">
              <Money label="Hôm nay" value={d.revenue_today_vnd} lead />
              <Money label="Tuần này" value={d.revenue_week_vnd} />
              <Money label="Tháng này" value={d.revenue_month_vnd} />
              <Money label="Tổng cộng" value={d.revenue_total_vnd} />
            </Card>

            <Card className="p-4">
              {/* Filters sit in one row above the chart. */}
              <div className="flex flex-wrap items-end justify-between gap-3 mb-3">
                <div>
                  <h2 className="text-base font-semibold text-ink">
                    Doanh thu theo ngày
                  </h2>
                  <p className="text-2xs text-faint mt-0.5">
                    Chỉ tính các chuyến đã được điều phối duyệt hoàn thành
                  </p>
                </div>
                <div className="w-40">
                  <Select
                    label="Khoảng thời gian"
                    labelHidden
                    value={days}
                    options={RANGES}
                    onChange={setDays}
                  />
                </div>
              </div>
              <RevenueChart points={d.daily} />
            </Card>

            <div className="grid gap-5 lg:grid-cols-2">
              <Card className="p-4">
                <h2 className="text-base font-semibold text-ink mb-3">
                  Tình hình thu tiền
                </h2>
                <Meter
                  collected={d.collected_vnd}
                  expected={d.expected_vnd}
                />
                {/* Status classes carry an explicit label, never colour
                    alone — and as a labelled list rather than a stacked
                    bar, because `disputed` and `outstanding` sit at
                    ΔE 11 in this palette and would be indistinguishable
                    as adjacent segments even with full colour vision. */}
                <dl className="mt-4 space-y-2">
                  <MoneyRow label="Đã thu" value={d.collected_vnd} tone="success" />
                  <MoneyRow label="Chưa thu" value={d.outstanding_vnd} tone="warning" />
                  <MoneyRow label="Thiếu tiền" value={d.disputed_vnd} tone="danger" />
                  <MoneyRow label="Đã miễn" value={d.waived_vnd} tone="neutral" />
                </dl>
              </Card>

              <Card className="p-4">
                <h2 className="text-base font-semibold text-ink mb-3">
                  Hiệu quả vận hành
                </h2>
                <dl className="space-y-2">
                  <Stat
                    icon={<Car size={13} aria-hidden="true" />}
                    label="Chuyến hoàn thành"
                    value={d.trips_finalized.toLocaleString("vi-VN")}
                  />
                  <Stat
                    icon={<Users size={13} aria-hidden="true" />}
                    label="Lượt khách"
                    value={`${d.passengers_carried.toLocaleString("vi-VN")} khách · ${d.seats_carried.toLocaleString("vi-VN")} chỗ`}
                  />
                  <Stat
                    icon={<TrendingUp size={13} aria-hidden="true" />}
                    label="Doanh thu trung bình / chuyến"
                    value={fmtVnd(d.avg_revenue_per_trip_vnd)}
                  />
                  <Stat
                    icon={<Users size={13} aria-hidden="true" />}
                    label="Số chỗ trung bình / chuyến"
                    value={`${d.avg_seats_per_trip} chỗ`}
                    hint="Càng cao nghĩa là ghép khách càng hiệu quả"
                  />
                  <Stat
                    icon={<Car size={13} aria-hidden="true" />}
                    label="Chuyến bị huỷ"
                    value={d.trips_cancelled.toLocaleString("vi-VN")}
                  />
                </dl>
              </Card>
            </div>
          </div>
        )}
      </QueryState>
    </AppShell>
  );
}

/** A headline figure. `lead` gives the one the page opens with more size. */
function Money({
  label,
  value,
  lead = false,
}: {
  label: string;
  value: number;
  lead?: boolean;
}) {
  return (
    <div className="px-4 py-3">
      <dt className="text-2xs text-faint">{label}</dt>
      <dd
        className={`tnum font-semibold text-ink mt-0.5 ${
          lead ? "text-2xl" : "text-lg"
        }`}
      >
        {fmtVnd(value)}
      </dd>
    </div>
  );
}

/**
 * One ratio against a limit — a meter, not a two-slice pie. Single
 * hue on a same-ramp track, so there is no colour pair to confuse.
 */
function Meter({ collected, expected }: { collected: number; expected: number }) {
  const pct = expected > 0 ? Math.min(100, (collected / expected) * 100) : 0;
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-2xl font-semibold tnum text-ink">
          {Math.round(pct)}%
        </span>
        <span className="text-2xs text-faint tnum">
          {fmtVnd(collected)} / {fmtVnd(expected)}
        </span>
      </div>
      <div
        className="mt-2 h-2 rounded-full bg-sunken overflow-hidden"
        role="meter"
        aria-valuenow={Math.round(pct)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Tỉ lệ đã thu trên tổng cước"
      >
        <div
          className="h-full rounded-full bg-brand transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

const TONE_DOT: Record<string, string> = {
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
  neutral: "bg-border-strong",
};

function MoneyRow({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: keyof typeof TONE_DOT;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="flex items-center gap-2 text-base text-muted">
        <span
          aria-hidden="true"
          className={`w-2 h-2 rounded-full shrink-0 ${TONE_DOT[tone]}`}
        />
        {label}
      </dt>
      <dd className="text-base tnum font-medium text-ink">{fmtVnd(value)}</dd>
    </div>
  );
}

function Stat({
  icon,
  label,
  value,
  hint,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="min-w-0">
        <span className="flex items-center gap-2 text-base text-muted">
          <span className="text-faint shrink-0">{icon}</span>
          {label}
        </span>
        {hint && <span className="block text-2xs text-faint ml-5">{hint}</span>}
      </dt>
      <dd className="text-base tnum font-medium text-ink whitespace-nowrap">
        {value}
      </dd>
    </div>
  );
}
