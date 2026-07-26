import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Bell, Plus, Shuffle } from "lucide-react";
import { api } from "../lib/api";
import type { BookingStatus } from "../types";
import AppShell from "../components/layout/AppShell";
import AttentionPanel from "../components/AttentionPanel";
import BookingForm from "../components/BookingForm";
import BookingsList from "../components/BookingsList";
import FleetStatusTable from "../components/FleetStatusTable";
import TripsPanel from "../components/TripsPanel";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import QueryState from "../components/ui/QueryState";
import Skeleton from "../components/ui/Skeleton";
import SlideOver from "../components/ui/SlideOver";
import { useToast } from "../components/ui/Toast";
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

  // The queue is for bookings still relevant to dispatch. Once a
  // booking is completed or cancelled it's history, not queue — GET
  // /bookings returns every booking ever made with no status filter,
  // so this list would otherwise fill up with finished rides forever.
  // HistoryPage is the real place to look those up.
  const bookings = useMemo(
    () =>
      (bookingsQuery.data ?? []).filter(
        (b) => b.status !== "completed" && b.status !== "cancelled"
      ),
    [bookingsQuery.data]
  );
  const trips = tripsQuery.data ?? [];

  const stats = useMemo(() => {
    return {
      waiting: bookings.filter((b) => b.status === "queued" || b.status === "waiting")
        .length,
      matched: bookings.filter((b) => b.status === "matched").length,
      // Cars physically on the road — status `in_progress` and nothing
      // else. This used to be `trips.length`, which counted every pool
      // including ones still gathering passengers, so the tile read
      // "Xe đang chạy: 7" directly above a fleet table that said 2 were
      // running. Two different numbers under the same word, 200px
      // apart, is how an operator learns to distrust a dashboard.
      running: trips.filter((t) => t.status === "in_progress").length,
      // Trips a driver has reported finished and nobody has approved
      // yet. This is the dispatcher's actual queue of work under the
      // new workflow, and it replaces the revenue tile that used to
      // sit here — money rollups are admin-only now (requirements §3).
      awaitingReview: trips.filter((t) => t.status === "completion_requested")
        .length,
    };
  }, [bookings, trips]);

  // Both queries feed the tiles, so either failing makes all four
  // numbers untrustworthy.
  const statsReady = !bookingsQuery.isError && !tripsQuery.isError;

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
          <Link to="/notifications">
            <Button variant="ghost" iconLeft={<Bell size={15} aria-hidden="true" />}>
              Thông báo
            </Button>
          </Link>
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
          state of the business below the fold.

          When a query has failed these show "—" rather than 0. A
          confident zero is a lie about the state of the business, and
          it is exactly the kind of lie a dispatcher would act on. */}
      {/* One hairline-divided strip rather than four cards. The cards
          spent ~140px of vertical space to show four integers, with the
          label and the value at nearly the same visual weight — so the
          numbers didn't read as the headline and the queue below got
          pushed off the fold. Card chrome now means "an object you can
          act on"; a number is just a number. */}
      <Card className="mb-5 grid grid-cols-2 lg:grid-cols-4 divide-y lg:divide-y-0 lg:divide-x divide-line">
        <Stat
          label="Khách chờ ghép"
          value={statsReady ? stats.waiting : "—"}
          tone={statsReady && stats.waiting > 0 ? "warning" : undefined}
        />
        <Stat
          label="Khách đã ghép"
          value={statsReady ? stats.matched : "—"}
          tone={statsReady && stats.matched > 0 ? "success" : undefined}
        />
        <Stat label="Xe đang chạy" value={statsReady ? stats.running : "—"} />
        <Stat
          label="Chờ duyệt hoàn thành"
          value={statsReady ? stats.awaitingReview : "—"}
          tone={statsReady && stats.awaitingReview > 0 ? "warning" : undefined}
        />
      </Card>

      <AttentionPanel />

      {/* Where every car in the fleet is right now — including the idle
          ones. This reads the vehicle roster and joins live trips onto
          it, rather than being built from trips alone, which is why a
          car used to vanish from the board the moment its trip
          finished. */}
      <div className="mb-6">
        <QueryState
          query={tripsQuery}
          errorTitle="Không tải được tình trạng đội xe"
          skeleton={<Skeleton className="h-56 w-full rounded-lg" />}
        >
          {(tripList) => <FleetStatusTable trips={tripList} />}
        </QueryState>
      </div>

      {/* Tablet gets its own two-column tier at `md` rather than
          falling back to the phone layout, which stacked the queue
          above the cars and made the board a very long scroll on the
          device dispatchers actually keep on the desk. */}
      <div className="grid md:grid-cols-2 lg:grid-cols-[minmax(0,420px)_minmax(0,1fr)] gap-5 items-start">
        {/* Queue */}
        <Card className="overflow-hidden">
          <div className="px-4 py-3 border-b border-line flex items-center justify-between gap-2">
            <h2 className="text-base font-semibold">
              Hàng chờ
              <span className="text-faint font-normal ml-1.5 tnum">
                {visibleBookings.length}
              </span>
            </h2>
          </div>

          <div
            className="flex gap-1 px-3 py-2 border-b border-line overflow-x-auto"
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
                  "px-2.5 h-7 rounded-full text-xs font-medium whitespace-nowrap transition-colors",
                  filter === f.value
                    ? "bg-inverse text-on-inverse"
                    : "text-muted hover:bg-sunken",
                ].join(" ")}
              >
                {f.label}
              </button>
            ))}
          </div>

          {/* Bounded by viewport height rather than a fixed rem offset:
              `24rem` assumed a specific amount of chrome above, which
              left roughly three visible rows on a 13" laptop. */}
          <div className="max-h-[min(60vh,40rem)] overflow-y-auto">
            <QueryState
              query={bookingsQuery}
              errorTitle="Không tải được hàng chờ"
              skeleton={
                <div className="space-y-2 p-3">
                  <Skeleton className="h-[72px] w-full" count={3} />
                </div>
              }
            >
              {() => (
                <BookingsList
                  bookings={visibleBookings}
                  filtered={filter !== "all"}
                  onChanged={refreshAll}
                  onAddBooking={() => setFormOpen(true)}
                  onClearFilter={() => setFilter("all")}
                />
              )}
            </QueryState>
          </div>
        </Card>

        {/* Cars */}
        <section aria-labelledby="cars-heading">
          <div className="flex items-center justify-between mb-3">
            <h2 id="cars-heading" className="text-base font-semibold">
              Xe đã ghép
              <span className="text-faint font-normal ml-1.5 tnum">
                {trips.length}
              </span>
            </h2>
          </div>
          <QueryState
            query={tripsQuery}
            errorTitle="Không tải được danh sách chuyến"
            skeleton={
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                <Skeleton className="h-52 w-full rounded-lg" count={3} />
              </div>
            }
          >
            {(tripList) => <TripsPanel trips={tripList} />}
          </QueryState>
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
  /** Only applied when the number is non-zero — a `0` rendered in
   *  warning amber looks like a fault rather than a quiet queue. */
  tone?: "warning" | "success";
}) {
  const color =
    tone === "warning"
      ? "text-warning"
      : tone === "success"
        ? "text-success"
        : "text-ink";
  return (
    <div className="px-4 py-3">
      <p className="text-2xs text-faint mb-1 uppercase tracking-wide">{label}</p>
      <p className={`text-2xl font-semibold tnum leading-none ${color}`}>
        {value}
      </p>
    </div>
  );
}
