import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Shuffle } from "lucide-react";
import { api } from "../lib/api";
import type { BookingStatus } from "../types";
import AppShell from "../components/layout/AppShell";
import BookingForm from "../components/BookingForm";
import BookingsList from "../components/BookingsList";
import TripsPanel from "../components/TripsPanel";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import SlideOver from "../components/ui/SlideOver";
import { useToast } from "../components/ui/Toast";
import { fmtVnd } from "../lib/format";
import { getErrorMessage } from "../lib/errors";

// Fixed rather than dispatcher-adjustable — 15km covers this business's
// service area without putting a technical knob in an operational UI.
const MAX_DETOUR_METERS = 15000;

type Filter = "all" | BookingStatus;

const FILTERS: { value: Filter; label: string }[] = [
  { value: "all", label: "Tất cả" },
  { value: "queued", label: "Chờ ghép" },
  { value: "waiting", label: "Chưa đủ khách" },
  { value: "matched", label: "Đã ghép xe" },
];

export default function DispatchBoard() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [running, setRunning] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");

  const bookingsQuery = useQuery({
    queryKey: ["bookings"],
    queryFn: () => api.bookings.list(),
  });
  const tripsQuery = useQuery({
    queryKey: ["trips"],
    queryFn: () => api.dispatch.trips(),
  });

  const refreshAll = () => {
    queryClient.invalidateQueries({ queryKey: ["bookings"] });
    queryClient.invalidateQueries({ queryKey: ["trips"] });
  };

  const bookings = bookingsQuery.data ?? [];
  const trips = tripsQuery.data ?? [];

  const stats = useMemo(() => {
    const active = bookings.filter((b) => b.status !== "cancelled");
    return {
      waiting: active.filter((b) => b.status === "queued" || b.status === "waiting")
        .length,
      matched: active.filter((b) => b.status === "matched").length,
      cars: trips.length,
      revenue: trips.reduce(
        (sum, t) => sum + t.bookings.reduce((s, b) => s + b.price_vnd, 0),
        0
      ),
    };
  }, [bookings, trips]);

  const visibleBookings = useMemo(
    () => (filter === "all" ? bookings : bookings.filter((b) => b.status === filter)),
    [bookings, filter]
  );

  const runMatching = async () => {
    setRunning(true);
    try {
      const result = await api.dispatch.run(MAX_DETOUR_METERS);
      toast(
        result.trips_created > 0
          ? `Đã ghép ${result.trips_created} xe.`
          : "Chưa ghép được xe nào. Cần thêm khách cùng tuyến, cùng ngày.",
        result.trips_created > 0 ? "success" : "info"
      );
      refreshAll();
    } catch (err: any) {
      toast(getErrorMessage(err, "Không ghép được chuyến."), "error");
    } finally {
      setRunning(false);
    }
  };

  return (
    <AppShell
      title="Bảng điều phối"
      subtitle="Bắc Giang ⇄ Hà Nội"
      actions={
        <>
          <Button
            variant="secondary"
            iconLeft={<Plus size={15} aria-hidden="true" />}
            onClick={() => setFormOpen(true)}
          >
            Thêm khách
          </Button>
          <Button
            variant="primary"
            iconLeft={<Shuffle size={15} aria-hidden="true" />}
            onClick={runMatching}
            loading={running}
          >
            Ghép chuyến
          </Button>
        </>
      }
    >
      {/* Stats — the operational picture, above everything else.
          Previously the form occupied this space and pushed the actual
          state of the business below the fold. */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
        <Stat label="Khách chờ ghép" value={stats.waiting} tone="warning" />
        <Stat label="Khách đã ghép" value={stats.matched} tone="success" />
        <Stat label="Xe đang chạy" value={stats.cars} />
        <Stat label="Doanh thu dự kiến" value={fmtVnd(stats.revenue)} />
      </div>

      <div className="grid lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)] gap-5 items-start">
        {/* Queue */}
        <Card className="overflow-hidden">
          <div className="px-4 py-3 border-b border-[var(--border)] flex items-center justify-between gap-2">
            <h2 className="text-sm font-semibold">
              Hàng chờ
              <span className="text-[var(--text-tertiary)] font-normal ml-1.5 tnum">
                {visibleBookings.length}
              </span>
            </h2>
          </div>

          <div
            className="flex gap-1 px-3 py-2 border-b border-[var(--border)] overflow-x-auto"
            role="tablist"
            aria-label="Lọc theo trạng thái"
          >
            {FILTERS.map((f) => (
              <button
                key={f.value}
                role="tab"
                aria-selected={filter === f.value}
                onClick={() => setFilter(f.value)}
                className={[
                  "px-2.5 h-7 rounded-[var(--radius-full)] text-xs font-medium whitespace-nowrap transition-colors",
                  filter === f.value
                    ? "bg-[var(--surface-inverse)] text-white"
                    : "text-[var(--text-secondary)] hover:bg-[var(--surface-sunken)]",
                ].join(" ")}
              >
                {f.label}
              </button>
            ))}
          </div>

          <div className="max-h-[calc(100vh-24rem)] overflow-y-auto">
            <BookingsList
              bookings={visibleBookings}
              loading={bookingsQuery.isLoading}
              onChanged={refreshAll}
              onAddBooking={() => setFormOpen(true)}
            />
          </div>
        </Card>

        {/* Cars */}
        <section aria-labelledby="cars-heading">
          <div className="flex items-center justify-between mb-3">
            <h2 id="cars-heading" className="text-sm font-semibold">
              Xe đã ghép
              <span className="text-[var(--text-tertiary)] font-normal ml-1.5 tnum">
                {trips.length}
              </span>
            </h2>
          </div>
          <TripsPanel trips={trips} loading={tripsQuery.isLoading} />
        </section>
      </div>

      <SlideOver
        open={formOpen}
        title="Thêm khách mới"
        description="Nhập thông tin và địa chỉ để đưa khách vào hàng chờ ghép."
        onClose={() => setFormOpen(false)}
      >
        <BookingForm
          onCreated={() => {
            refreshAll();
            setFormOpen(false);
          }}
        />
      </SlideOver>
    </AppShell>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string | number;
  tone?: "warning" | "success";
}) {
  const color =
    tone === "warning"
      ? "text-[var(--warning)]"
      : tone === "success"
        ? "text-[var(--success)]"
        : "text-[var(--text)]";
  return (
    <Card className="px-4 py-3">
      <p className="text-[11px] text-[var(--text-tertiary)] mb-1">{label}</p>
      <p className={`text-xl font-semibold tnum ${color}`}>{value}</p>
    </Card>
  );
}
