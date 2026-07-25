import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ArrowLeft, History, Lock, Search, Users } from "lucide-react";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import type { TripOut } from "../types";
import {
  DIRECTION,
  TRIP_STATUS,
  fmtDateTime,
  fmtVnd,
  seatsTaken,
  tripIdentity,
} from "../lib/format";
import AppShell from "../components/layout/AppShell";
import Badge from "../components/ui/Badge";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import DataTable, { type Column } from "../components/ui/DataTable";
import EmptyState from "../components/ui/EmptyState";
import QueryState from "../components/ui/QueryState";
import Select from "../components/ui/Select";
import Skeleton from "../components/ui/Skeleton";

/**
 * How far back to show by default.
 *
 * The endpoint returns every trip ever completed or cancelled, with no
 * server-side window — so as an unfiltered card grid this screen grew
 * without bound and got slower every week the business ran. 30 days
 * matches how far back anyone actually calls to ask about a ride.
 */
const RANGES = [
  { value: "7", label: "7 ngày qua" },
  { value: "30", label: "30 ngày qua" },
  { value: "90", label: "3 tháng qua" },
  { value: "all", label: "Toàn bộ" },
];

const PAGE_SIZE = 25;

const finishedAt = (t: TripOut) => t.completed_at ?? t.cancelled_at;

export default function HistoryPage() {
  const { user } = useAuth();
  const isDriver = user?.role === "driver";

  const [range, setRange] = useState("30");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);

  const historyQuery = useQuery({
    queryKey: ["history", isDriver ? "mine" : "all"],
    queryFn: () => (isDriver ? api.dispatch.myHistory() : api.dispatch.history()),
  });

  const filtered = useMemo(() => {
    const all = historyQuery.data ?? [];
    const cutoff =
      range === "all" ? null : Date.now() - Number(range) * 86_400_000;
    const needle = query.trim().toLowerCase();

    return all
      .filter((t) => {
        const done = finishedAt(t);
        if (cutoff && done && new Date(done).getTime() < cutoff) return false;
        if (!needle) return true;
        // Staff look these up by customer name or phone — that is how a
        // "where was my ride" phone call actually starts.
        return (
          tripIdentity(t).toLowerCase().includes(needle) ||
          t.bookings.some(
            (b) =>
              b.customer.full_name.toLowerCase().includes(needle) ||
              b.customer.phone.includes(needle)
          )
        );
      })
      .sort((a, b) => {
        const ad = finishedAt(a) ?? "";
        const bd = finishedAt(b) ?? "";
        return ad < bd ? 1 : ad > bd ? -1 : 0;
      });
  }, [historyQuery.data, range, query]);

  const totalRevenue = useMemo(
    () =>
      filtered.reduce(
        (sum, t) => sum + t.bookings.reduce((s, b) => s + b.price_vnd, 0),
        0
      ),
    [filtered]
  );

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const visible = filtered.slice(
    safePage * PAGE_SIZE,
    safePage * PAGE_SIZE + PAGE_SIZE
  );

  const columns: Column<TripOut>[] = [
    {
      header: "Hoàn tất",
      className: "tnum whitespace-nowrap",
      cell: (t) => {
        const done = finishedAt(t);
        return done ? fmtDateTime(done) : "—";
      },
    },
    {
      header: "Xe",
      className: "font-medium whitespace-nowrap",
      cell: (t) => tripIdentity(t),
    },
    {
      header: "Tuyến",
      className: "whitespace-nowrap",
      cell: (t) => {
        const d = t.bookings[0]?.direction;
        return d ? DIRECTION[d].short : "—";
      },
    },
    {
      header: "Khách",
      cell: (t) => (
        <span className="flex items-center gap-1.5 whitespace-nowrap">
          {t.is_private ? (
            <>
              <Lock size={11} aria-hidden="true" className="text-faint" />
              Bao xe
            </>
          ) : (
            <>
              <Users size={11} aria-hidden="true" className="text-faint" />
              <span className="tnum">{t.bookings.length}</span>
            </>
          )}
        </span>
      ),
    },
    {
      header: "Chỗ",
      align: "right",
      className: "tnum",
      cell: (t) => seatsTaken(t.bookings),
    },
    {
      header: "Trạng thái",
      cell: (t) => {
        const s = TRIP_STATUS[t.status];
        return <Badge tone={s.tone}>{s.label}</Badge>;
      },
    },
    {
      header: "Doanh thu",
      align: "right",
      className: "tnum",
      cell: (t) => fmtVnd(t.bookings.reduce((s, b) => s + b.price_vnd, 0)),
      total: fmtVnd(totalRevenue),
    },
  ];

  return (
    <AppShell
      title="Lịch sử chuyến"
      subtitle={
        isDriver
          ? "Các chuyến bạn đã hoàn thành"
          : "Toàn bộ chuyến đã hoàn thành hoặc huỷ"
      }
      width="wide"
      actions={
        <Link to={isDriver ? "/driver" : "/"}>
          <Button variant="ghost" iconLeft={<ArrowLeft size={15} aria-hidden="true" />}>
            Quay lại
          </Button>
        </Link>
      }
    >
      <QueryState
        query={historyQuery}
        errorTitle="Không tải được lịch sử chuyến"
        skeleton={<Skeleton className="h-96 w-full rounded-lg" />}
        empty={
          <Card>
            <EmptyState
              icon={<History size={18} aria-hidden="true" />}
              title="Chưa có chuyến nào trong lịch sử"
              description="Các chuyến sau khi hoàn thành hoặc bị huỷ sẽ xuất hiện ở đây, cùng danh sách khách và thời gian hoàn tất."
            />
          </Card>
        }
      >
        {() => (
          <Card className="overflow-hidden">
            <div className="px-4 py-3 border-b border-line flex flex-wrap items-end gap-3">
              <div className="flex-1 min-w-[13rem]">
                <label
                  htmlFor="history-search"
                  className="block text-xs font-medium mb-1.5 text-muted"
                >
                  Tìm khách hoặc xe
                </label>
                <div className="relative">
                  <Search
                    size={14}
                    aria-hidden="true"
                    className="absolute left-3 top-1/2 -translate-y-1/2 text-faint pointer-events-none"
                  />
                  <input
                    id="history-search"
                    type="search"
                    value={query}
                    onChange={(e) => {
                      setQuery(e.target.value);
                      setPage(0);
                    }}
                    placeholder="Tên khách, số điện thoại, biển số"
                    className="w-full h-9 pl-9 pr-3 text-base rounded bg-surface border border-line-strong hover:border-faint focus:border-line-focus transition-colors placeholder:text-faint"
                  />
                </div>
              </div>

              <Select
                label="Khoảng thời gian"
                value={range}
                options={RANGES}
                onChange={(v) => {
                  setRange(v);
                  setPage(0);
                }}
                className="w-[11rem]"
              />
            </div>

            {filtered.length === 0 ? (
              <EmptyState
                icon={<Search size={18} aria-hidden="true" />}
                title="Không tìm thấy chuyến nào"
                description="Thử mở rộng khoảng thời gian hoặc bỏ từ khoá tìm kiếm."
                action={
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => {
                      setQuery("");
                      setRange("all");
                    }}
                  >
                    Xem toàn bộ
                  </Button>
                }
              />
            ) : (
              <>
                <DataTable
                  columns={columns}
                  rows={visible}
                  rowKey={(t) => t.id}
                  caption="Lịch sử các chuyến đã hoàn thành hoặc huỷ"
                  minWidth={860}
                  showTotals
                  totalsLabel={`${filtered.length} chuyến`}
                />

                {pageCount > 1 && (
                  <div className="px-4 py-3 border-t border-line flex items-center justify-between gap-3">
                    <p className="text-xs text-faint tnum">
                      {safePage * PAGE_SIZE + 1}–
                      {safePage * PAGE_SIZE + visible.length} / {filtered.length}
                    </p>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="secondary"
                        size="sm"
                        disabled={safePage === 0}
                        onClick={() => setPage(safePage - 1)}
                      >
                        Trước
                      </Button>
                      <span className="text-xs text-faint tnum">
                        {safePage + 1} / {pageCount}
                      </span>
                      <Button
                        variant="secondary"
                        size="sm"
                        disabled={safePage >= pageCount - 1}
                        onClick={() => setPage(safePage + 1)}
                      >
                        Sau
                      </Button>
                    </div>
                  </div>
                )}
              </>
            )}
          </Card>
        )}
      </QueryState>
    </AppShell>
  );
}
