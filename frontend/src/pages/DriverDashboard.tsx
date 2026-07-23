import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDownToLine, ArrowUpFromLine, Car, Phone } from "lucide-react";
import { api } from "../lib/api";
import type { TripOut, TripStatus } from "../types";
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
} from "../lib/format";

export default function DriverDashboard() {
  const toast = useToast();
  const queryClient = useQueryClient();

  const tripsQuery = useQuery({
    queryKey: ["my-trips"],
    queryFn: () => api.dispatch.myTrips(),
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["my-trips"] });

  const advance = async (trip: TripOut, next: TripStatus, label: string) => {
    try {
      await api.dispatch.updateStatus(trip.id, next);
      toast(`${label} — đã cập nhật.`, "success");
      refresh();
    } catch (err: any) {
      toast(getErrorMessage(err, "Không cập nhật được chuyến."), "error");
    }
  };

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
        {trips.map((trip) => {
          const status = TRIP_STATUS[trip.status];
          const action = NEXT_TRIP_ACTION[trip.status];
          const direction = trip.bookings[0]?.direction;
          const stops = [...trip.bookings].sort(
            (a, b) => (a.pickup_lng ?? 0) - (b.pickup_lng ?? 0)
          );

          return (
            <Card
              key={trip.id}
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
                    {trip.is_private
                      ? "Bao xe riêng"
                      : `${trip.bookings.length} khách`}
                    {trip.bookings[0] &&
                      ` · ${fmtDayLabel(trip.bookings[0].requested_pickup_at)}`}
                  </p>
                </div>
                <Badge tone={status.tone}>{status.label}</Badge>
              </header>

              <ol className="divide-y divide-[var(--border)]">
                {stops.map((b, i) => (
                  <li key={b.id} className="px-4 py-3">
                    <div className="flex items-start gap-3">
                      <span
                        className="w-5 h-5 rounded-full bg-[var(--surface-sunken)] text-[10px] font-semibold flex items-center justify-center shrink-0 mt-0.5 tnum"
                        aria-hidden="true"
                      >
                        {i + 1}
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-sm font-medium truncate">
                            {b.customer.full_name}
                          </span>
                          {/* Tap-to-call — a driver holding a phone
                              shouldn't have to copy a number by hand */}
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
                      </div>
                    </div>
                  </li>
                ))}
              </ol>

              {action && (
                <div className="p-4 border-t border-[var(--border)] bg-[var(--surface-sunken)]">
                  <Button
                    variant="primary"
                    size="lg"
                    fullWidth
                    onClick={() => advance(trip, action.next, action.label)}
                  >
                    {action.label}
                  </Button>
                </div>
              )}
            </Card>
          );
        })}
      </div>
    </AppShell>
  );
}
