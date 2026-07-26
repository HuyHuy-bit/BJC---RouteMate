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
import Menu from "../components/ui/Menu";
import QueryState from "../components/ui/QueryState";
import Skeleton from "../components/ui/Skeleton";
import { useToast } from "../components/ui/Toast";
import { getErrorMessage } from "../lib/errors";
import {
  DIRECTION,
  PAYMENT_STATUS,
  TRIP_STATUS,
  fmtDayLabel,
  fmtTime,
  fmtVnd,
  tripActionFor,
} from "../lib/format";

const ISSUE_REASONS: { value: TripReportIssueReason; label: string }[] = [
  { value: "breakdown", label: "Hỏng xe" },
  { value: "accident", label: "Tai nạn" },
  { value: "driver_unavailable", label: "Không thể tiếp tục" },
  { value: "other", label: "Lý do khác" },
];

/**
 * The order the driver should actually collect people in.
 *
 * This used to sort by `pickup_lng` ascending, which was wrong in a
 * way that was invisible on screen: Bắc Giang sits EAST of Hà Nội
 * (~106.19°E vs ~105.85°E), so on every outbound trip ascending
 * longitude produced the exact reverse of the real route — and the
 * driver followed it.
 *
 * The backend already solves stop order properly (branch-and-bound
 * PDP solver, then per-stop ETAs written to `estimated_pickup_at`),
 * so the honest thing is to trust that and stop re-deriving geometry
 * in the UI. Bookings without an ETA yet sort last on requested
 * time rather than being silently dropped into position zero.
 */
function orderedStops(bookings: BookingOut[]): BookingOut[] {
  return [...bookings].sort((a, b) => {
    const at = a.estimated_pickup_at ?? a.requested_pickup_at;
    const bt = b.estimated_pickup_at ?? b.requested_pickup_at;
    if (at === bt) return 0;
    return at < bt ? -1 : 1;
  });
}

export default function DriverDashboard() {
  const toast = useToast();
  const queryClient = useQueryClient();

  const tripsQuery = useQuery({
    queryKey: ["my-trips"],
    queryFn: () => api.dispatch.myTrips(),
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["my-trips"] });

  const tripCount = tripsQuery.data?.length ?? 0;

  return (
    <AppShell
      title="Chuyến của tôi"
      subtitle={tripCount > 0 ? `${tripCount} chuyến đang chờ bạn` : undefined}
      width="narrow"
    >
      <QueryState
        query={tripsQuery}
        errorTitle="Không tải được chuyến của bạn"
        skeleton={
          <div className="space-y-4">
            <Skeleton className="h-64 w-full rounded-lg" count={2} />
          </div>
        }
        empty={
          <Card>
            <EmptyState
              icon={<Car size={18} aria-hidden="true" />}
              title="Chưa có chuyến nào được giao"
              description="Khi điều phối viên giao chuyến cho bạn, chuyến sẽ hiện ở đây kèm danh sách khách và thứ tự đón."
            />
          </Card>
        }
      >
        {(trips) => (
          <div className="space-y-4">
            {trips.map((trip) => (
              <TripCard
                key={trip.id}
                trip={trip}
                onRefresh={refresh}
                toast={toast}
              />
            ))}
          </div>
        )}
      </QueryState>
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
  const [busyPath, setBusyPath] = useState<string | null>(null);

  const status = TRIP_STATUS[trip.status];
  const actions = (trip.available_actions ?? [])
    .map((to) => tripActionFor(trip.status, to))
    .filter((a): a is NonNullable<typeof a> => a !== undefined);
  const direction = trip.bookings[0]?.direction;
  const stops = orderedStops(trip.bookings);
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

  const advance = async (path: string, label: string) => {
    setBusyPath(path);
    try {
      await api.dispatch.action(trip.id, path);
      // "Hoàn thành chuyến" no longer ends the trip — it raises a
      // request a dispatcher has to approve. Say so, or the driver
      // will think the app failed when the card stays on screen.
      toast(
        path === "request-completion"
          ? "Đã báo hoàn thành. Chờ điều phối duyệt."
          : `${label} — đã cập nhật.`,
        "success"
      );
      onRefresh();
    } catch (err: any) {
      toast(getErrorMessage(err, "Không cập nhật được chuyến."), "error");
    } finally {
      setBusyPath(null);
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

  // No colour rail for private hire. Red was doing double duty as both
  // "primary action" and "bao xe riêng", which diluted both — the Lock
  // icon and the "Bao xe riêng" label carry that meaning without
  // spending the brand colour on a content attribute.
  return (
    <Card as="article" className="overflow-hidden">
      <header className="px-4 py-3 border-b border-line flex items-center justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold">
            {direction ? DIRECTION[direction].label : "Chuyến xe"}
          </h2>
          <p className="text-2xs text-faint mt-0.5">
            {trip.is_private ? "Bao xe riêng" : `${trip.bookings.length} khách`}
            {trip.bookings[0] && ` · ${fmtDayLabel(trip.bookings[0].requested_pickup_at)}`}
          </p>
        </div>
        <Badge tone={status.tone}>{status.label}</Badge>
      </header>

      <ol className="divide-y divide-line">
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

      {(actions.length > 0 || canReportIssue) && (
        <div className="p-4 border-t border-line bg-sunken space-y-2">
          {/* Driven by the backend's available_actions, so the button
              a driver sees is always one the server will accept —
              Nhận chuyến, then Bắt đầu, then Hoàn thành. */}
          {actions.map((a) => (
            <Button
              key={a.path}
              variant={a.tone === "danger" ? "danger-subtle" : "primary"}
              size="lg"
              fullWidth
              loading={busyPath === a.path}
              onClick={() => advance(a.path, a.label)}
            >
              {a.label}
            </Button>
          ))}

          {canReportIssue && !reportingIssue && (
            <Button
              variant="danger-subtle"
              size="lg"
              fullWidth
              iconLeft={<TriangleAlert size={15} aria-hidden="true" />}
              onClick={() => setReportingIssue(true)}
            >
              Báo sự cố xe
            </Button>
          )}

          {reportingIssue && (
            /* Reasons are stacked full-width at 44px rather than wrapped
               as chips. A driver reporting a breakdown is stationary,
               stressed, and holding a phone one-handed — this is the
               worst possible moment to ask for a precise tap. */
            <fieldset className="border-0 p-0 m-0 pt-1">
              <legend className="text-xs text-faint mb-2">
                Chuyện gì đang xảy ra?
              </legend>
              <div className="space-y-1.5">
                {ISSUE_REASONS.map((r) => (
                  <Button
                    key={r.value}
                    variant="secondary"
                    size="lg"
                    fullWidth
                    disabled={submittingIssue}
                    onClick={() => reportIssue(r.value)}
                  >
                    {r.label}
                  </Button>
                ))}
                <Button
                  variant="ghost"
                  size="lg"
                  fullWidth
                  disabled={submittingIssue}
                  onClick={() => setReportingIssue(false)}
                >
                  Huỷ
                </Button>
              </div>
            </fieldset>
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

  // Labels come from the shared PAYMENT_STATUS map so this and the
  // history detail panel can't drift into calling the same state two
  // different things. "pending" is excluded here because the "Thu tiền"
  // button already communicates it.
  const paymentBadge =
    b.payment && b.payment.status !== "pending"
      ? PAYMENT_STATUS[b.payment.status].label
      : null;

  return (
    <li className="px-4 py-3">
      <div className="flex items-start gap-3">
        <span
          className="w-5 h-5 rounded-full bg-sunken text-2xs font-semibold flex items-center justify-center shrink-0 mt-0.5 tnum"
          aria-hidden="true"
        >
          {i + 1}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <span className="text-base font-medium truncate">{b.customer.full_name}</span>
            {/* Tap-to-call — a driver holding a phone shouldn't have to
                copy a number by hand */}
            <a
              href={`tel:${b.customer.phone}`}
              className="shrink-0 inline-flex items-center gap-1 text-xs text-cobalt font-medium hover:underline"
              aria-label={`Gọi ${b.customer.full_name}`}
            >
              <Phone size={12} aria-hidden="true" />
              <span className="tnum">{b.customer.phone}</span>
            </a>
          </div>

          <p className="text-xs text-muted mt-1.5 flex items-start gap-1.5">
            <ArrowUpFromLine
              size={12}
              className="mt-0.5 shrink-0 text-cobalt"
              aria-hidden="true"
            />
            <span className="leading-snug">{b.pickup_address}</span>
          </p>
          <p className="text-xs text-muted mt-1 flex items-start gap-1.5">
            <ArrowDownToLine
              size={12}
              className="mt-0.5 shrink-0 text-brand-text"
              aria-hidden="true"
            />
            <span className="leading-snug">{b.dropoff_address}</span>
          </p>
          {/* The computed ETA leads, because that is the time this
              driver should actually arrive — it comes out of the route
              solver and accounts for the other stops on the run. The
              customer's requested time is kept alongside it, but
              demoted: it's useful context for the conversation at the
              door, not the number to drive to. Showing only the
              requested time (as this did) sends the driver to the wrong
              place at the wrong moment on any multi-stop trip. */}
          <p className="text-2xs text-faint mt-1.5 flex flex-wrap items-baseline gap-x-2">
            {b.estimated_pickup_at ? (
              <>
                <span className="text-xs font-medium text-ink tnum">
                  Đón lúc {fmtTime(b.estimated_pickup_at)}
                </span>
                <span className="tnum">
                  khách hẹn {fmtTime(b.requested_pickup_at)}
                </span>
              </>
            ) : (
              <span className="text-xs font-medium text-ink tnum">
                Khách hẹn {fmtTime(b.requested_pickup_at)}
              </span>
            )}
          </p>

          {/* Collecting money is the action a driver takes at almost
              every stop, so it gets a real thumb-sized button. Marking
              a no-show is rare and not undoable, so it moves behind the
              overflow menu — previously the two sat side by side as
              identical 12px text links, one tap apart. */}
          <div className="mt-2.5 flex items-center gap-2">
            {canCollectPayment && !collecting && (
              <Button
                variant="secondary"
                size="lg"
                iconLeft={<Banknote size={15} aria-hidden="true" />}
                onClick={() => setCollecting(true)}
                className="flex-1"
              >
                Thu tiền
              </Button>
            )}

            {paymentBadge && (
              <span className="text-xs text-faint flex-1">{paymentBadge}</span>
            )}

            {tripStatus === "in_progress" && (
              <Menu
                label={`Thao tác khác cho ${b.customer.full_name}`}
                items={[
                  {
                    label: "Khách không đến",
                    icon: <UserX size={15} />,
                    onSelect: markNoShow,
                    danger: true,
                  },
                ]}
              />
            )}
          </div>

          {collecting && (
            <div className="mt-2.5 flex items-center gap-2">
              <input
                type="number"
                inputMode="numeric"
                value={amount}
                onChange={(e) => setAmount(Number(e.target.value))}
                className="w-32 h-touch px-3 text-base rounded border border-line-strong bg-surface tnum focus:border-line-focus transition-colors"
                aria-label="Số tiền đã thu (VND)"
              />
              <Button
                variant="primary"
                size="lg"
                loading={submitting}
                onClick={collectPayment}
              >
                Xác nhận
              </Button>
              <Button
                variant="ghost"
                size="lg"
                onClick={() => setCollecting(false)}
              >
                Huỷ
              </Button>
            </div>
          )}

          {b.payment && (
            <p className="text-2xs text-faint mt-1 tnum">
              Cần thu: {fmtVnd(b.payment.expected_amount_vnd)}
            </p>
          )}
        </div>
      </div>
    </li>
  );
}
