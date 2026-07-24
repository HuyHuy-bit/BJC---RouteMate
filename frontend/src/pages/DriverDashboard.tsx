import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDownToLine,
  ArrowUpFromLine,
  Banknote,
  Car,
  Phone,
  TriangleAlert,
  UserX,
} from "lucide-react";
import { api } from "../lib/api";
import type { BookingOut, TripOut, TripReportIssueReason, TripStatus } from "../types";
import AppShell from "../components/layout/AppShell";
import Badge from "../components/ui/Badge";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import EmptyState from "../components/ui/EmptyState";
import Skeleton from "../components/ui/Skeleton";
import { useToast } from "../components/ui/Toast";
import { getErrorMessage } from "../lib/errors";
import {
  DIRECTION,
  NEXT_TRIP_ACTION,
  TRIP_STATUS,
  fmtDayLabel,
  fmtTime,
  fmtVnd,
} from "../lib/format";

const ISSUE_REASONS: { value: TripReportIssueReason; label: string }[] = [
  { value: "breakdown", label: "Hỏng xe" },
  { value: "accident", label: "Tai nạn" },
  { value: "driver_unavailable", label: "Không thể tiếp tục" },
  { value: "other", label: "Lý do khác" },
];

export default function DriverDashboard() {
  const toast = useToast();
  const queryClient = useQueryClient();

  const tripsQuery = useQuery({
    queryKey: ["my-trips"],
    queryFn: () => api.dispatch.myTrips(),
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["my-trips"] });

  const trips = tripsQuery.data ?? [];

  return (
    <AppShell
      title="Chuyến của tôi"
      subtitle={
        trips.length > 0 ? `${trips.length} chuyến đang chờ bạn` : undefined
      }
      width="narrow"
    >
      {tripsQuery.isLoading && (
        <Skeleton className="h-64 w-full rounded-[var(--radius-lg)] mb-4" count={2} />
      )}

      {!tripsQuery.isLoading && trips.length === 0 && (
        <Card>
          <EmptyState
            icon={<Car size={18} aria-hidden="true" />}
            title="Chưa có chuyến nào được giao"
            description="Khi điều phối viên giao chuyến cho bạn, chuyến sẽ hiện ở đây kèm danh sách khách và thứ tự đón."
          />
        </Card>
      )}

      <div className="space-y-4">
        {trips.map((trip) => (
          <TripCard key={trip.id} trip={trip} onRefresh={refresh} toast={toast} />
        ))}
      </div>
    </AppShell>
  );
}

function TripCard({
  trip,
  onRefresh,
  toast,
}: {
  trip: TripOut;
  onRefresh: () => void;
  toast: (message: string, tone?: "success" | "error") => void;
}) {
  const [reportingIssue, setReportingIssue] = useState(false);
  const [submittingIssue, setSubmittingIssue] = useState(false);

  const status = TRIP_STATUS[trip.status];
  const action = NEXT_TRIP_ACTION[trip.status];
  const direction = trip.bookings[0]?.direction;
  const stops = [...trip.bookings].sort(
    (a, b) => (a.pickup_lng ?? 0) - (b.pickup_lng ?? 0)
  );
  const canReportIssue = trip.status === "assigned" || trip.status === "in_progress";

  // Periodic location ping while this vehicle is actually out on a
  // trip — feeds dispatch_service's proximity-based vehicle assignment
  // and route ordering (see backend Phase 4). Best-effort only: a
  // denied permission or a failed request must never interrupt the
  // driver's actual flow, so every failure path here is silent.
  useEffect(() => {
    const active = trip.status === "assigned" || trip.status === "in_progress";
    if (!active || !trip.vehicle_id || !("geolocation" in navigator)) return;

    const ping = () => {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          api.vehicles
            .reportLocation(trip.vehicle_id as string, {
              lat: pos.coords.latitude,
              lng: pos.coords.longitude,
            })
            .catch(() => {});
        },
        () => {},
        { enableHighAccuracy: false, timeout: 10_000, maximumAge: 20_000 }
      );
    };

    ping();
    const id = setInterval(ping, 30_000);
    return () => clearInterval(id);
  }, [trip.vehicle_id, trip.status]);

  const advance = async (next: TripStatus, label: string) => {
    try {
      await api.dispatch.updateStatus(trip.id, next);
      toast(`${label} — đã cập nhật.`, "success");
      onRefresh();
    } catch (err: any) {
      toast(getErrorMessage(err, "Không cập nhật được chuyến."), "error");
    }
  };

  const reportIssue = async (reason: TripReportIssueReason) => {
    setSubmittingIssue(true);
    try {
      await api.dispatch.reportIssue(trip.id, { reason });
      toast("Đã báo sự cố. Đang tìm xe thay thế.", "success");
      setReportingIssue(false);
      onRefresh();
    } catch (err: any) {
      toast(getErrorMessage(err, "Không báo được sự cố."), "error");
    } finally {
      setSubmittingIssue(false);
    }
  };

  return (
    <Card
      as="article"
      accent={trip.is_private ? "var(--brand-red)" : "var(--brand-blue)"}
      className="overflow-hidden"
    >
      <header className="px-4 py-3 border-b border-[var(--border)] flex items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold">
            {direction ? DIRECTION[direction].label : "Chuyến xe"}
          </h2>
          <p className="text-[11px] text-[var(--text-tertiary)] mt-0.5">
            {trip.is_private ? "Bao xe riêng" : `${trip.bookings.length} khách`}
            {trip.bookings[0] && ` · ${fmtDayLabel(trip.bookings[0].requested_pickup_at)}`}
          </p>
        </div>
        <Badge tone={status.tone}>{status.label}</Badge>
      </header>

      <ol className="divide-y divide-[var(--border)]">
        {stops.map((b, i) => (
          <BookingRow
            key={b.id}
            booking={b}
            index={i}
            tripStatus={trip.status}
            onRefresh={onRefresh}
            toast={toast}
          />
        ))}
      </ol>

      {action && (
        <div className="p-4 border-t border-[var(--border)] bg-[var(--surface-sunken)] space-y-2">
          <Button
            variant="primary"
            size="lg"
            fullWidth
            onClick={() => advance(action.next, action.label)}
          >
            {action.label}
          </Button>

          {canReportIssue && !reportingIssue && (
            <button
              onClick={() => setReportingIssue(true)}
              className="w-full inline-flex items-center justify-center gap-1 text-xs text-[var(--danger)] hover:underline py-1"
            >
              <TriangleAlert size={12} aria-hidden="true" />
              Báo sự cố xe
            </button>
          )}

          {reportingIssue && (
            <div className="pt-1">
              <p className="text-xs text-[var(--text-tertiary)] mb-1.5">
                Chọn lý do:
              </p>
              <div className="flex flex-wrap gap-1.5">
                {ISSUE_REASONS.map((r) => (
                  <button
                    key={r.value}
                    disabled={submittingIssue}
                    onClick={() => reportIssue(r.value)}
                    className="text-xs px-2 py-1 rounded-[var(--radius-sm)] border border-[var(--danger)] text-[var(--danger)] hover:bg-[var(--danger)] hover:text-white disabled:opacity-50"
                  >
                    {r.label}
                  </button>
                ))}
                <button
                  disabled={submittingIssue}
                  onClick={() => setReportingIssue(false)}
                  className="text-xs px-2 py-1 text-[var(--text-tertiary)] hover:underline"
                >
                  Huỷ
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

function BookingRow({
  booking: b,
  index: i,
  tripStatus,
  onRefresh,
  toast,
}: {
  booking: BookingOut;
  index: number;
  tripStatus: TripStatus;
  onRefresh: () => void;
  toast: (message: string, tone?: "success" | "error") => void;
}) {
  const [collecting, setCollecting] = useState(false);
  const [amount, setAmount] = useState(b.payment?.expected_amount_vnd ?? b.price_vnd);
  const [submitting, setSubmitting] = useState(false);

  const markNoShow = async () => {
    try {
      await api.bookings.noShow(b.id);
      toast(`Đã đánh dấu ${b.customer.full_name} không đến.`, "success");
      onRefresh();
    } catch (err: any) {
      toast(getErrorMessage(err, "Không cập nhật được."), "error");
    }
  };

  const collectPayment = async () => {
    setSubmitting(true);
    try {
      await api.payments.collect(b.id, { method: "cash", collected_amount_vnd: amount });
      toast("Đã ghi nhận thanh toán.", "success");
      setCollecting(false);
      onRefresh();
    } catch (err: any) {
      toast(getErrorMessage(err, "Không ghi nhận được thanh toán."), "error");
    } finally {
      setSubmitting(false);
    }
  };

  const canCollectPayment =
    (tripStatus === "in_progress" || tripStatus === "completed") &&
    b.payment?.status === "pending";

  const paymentBadge =
    b.payment && b.payment.status !== "pending"
      ? { collected: "Đã thu tiền", disputed: "Thiếu tiền", waived: "Đã miễn" }[
          b.payment.status
        ]
      : null;

  return (
    <li className="px-4 py-3">
      <div className="flex items-start gap-3">
        <span
          className="w-5 h-5 rounded-full bg-[var(--surface-sunken)] text-[10px] font-semibold flex items-center justify-center shrink-0 mt-0.5 tnum"
          aria-hidden="true"
        >
          {i + 1}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm font-medium truncate">{b.customer.full_name}</span>
            {/* Tap-to-call — a driver holding a phone shouldn't have to
                copy a number by hand */}
            <a
              href={`tel:${b.customer.phone}`}
              className="shrink-0 inline-flex items-center gap-1 text-xs text-[var(--brand-blue)] font-medium hover:underline"
              aria-label={`Gọi ${b.customer.full_name}`}
            >
              <Phone size={12} aria-hidden="true" />
              <span className="tnum">{b.customer.phone}</span>
            </a>
          </div>

          <p className="text-xs text-[var(--text-secondary)] mt-1.5 flex items-start gap-1.5">
            <ArrowUpFromLine
              size={12}
              className="mt-0.5 shrink-0 text-[var(--brand-blue)]"
              aria-hidden="true"
            />
            <span className="leading-snug">{b.pickup_address}</span>
          </p>
          <p className="text-xs text-[var(--text-secondary)] mt-1 flex items-start gap-1.5">
            <ArrowDownToLine
              size={12}
              className="mt-0.5 shrink-0 text-[var(--brand-red)]"
              aria-hidden="true"
            />
            <span className="leading-snug">{b.dropoff_address}</span>
          </p>
          <p className="text-[11px] text-[var(--text-tertiary)] mt-1.5 tnum">
            Đón lúc {fmtTime(b.requested_pickup_at)}
          </p>

          <div className="mt-2 flex flex-wrap items-center gap-3">
            {tripStatus === "in_progress" && (
              <button
                onClick={markNoShow}
                className="inline-flex items-center gap-1 text-xs text-[var(--danger)] hover:underline"
              >
                <UserX size={12} aria-hidden="true" />
                Khách không đến
              </button>
            )}

            {canCollectPayment && !collecting && (
              <button
                onClick={() => setCollecting(true)}
                className="inline-flex items-center gap-1 text-xs text-[var(--brand-blue)] hover:underline"
              >
                <Banknote size={12} aria-hidden="true" />
                Thu tiền
              </button>
            )}

            {paymentBadge && (
              <span className="text-[11px] text-[var(--text-tertiary)]">
                {paymentBadge}
              </span>
            )}
          </div>

          {collecting && (
            <div className="mt-2 flex items-center gap-2">
              <input
                type="number"
                value={amount}
                onChange={(e) => setAmount(Number(e.target.value))}
                className="w-28 text-xs px-2 py-1 rounded-[var(--radius-sm)] border border-[var(--border)] bg-[var(--surface)] tnum"
                aria-label="Số tiền đã thu (VND)"
              />
              <Button size="sm" disabled={submitting} onClick={collectPayment}>
                Xác nhận
              </Button>
              <button
                onClick={() => setCollecting(false)}
                className="text-xs text-[var(--text-tertiary)] hover:underline"
              >
                Huỷ
              </button>
            </div>
          )}

          {b.payment && (
            <p className="text-[11px] text-[var(--text-tertiary)] mt-1 tnum">
              Cần thu: {fmtVnd(b.payment.expected_amount_vnd)}
            </p>
          )}
        </div>
      </div>
    </li>
  );
}
