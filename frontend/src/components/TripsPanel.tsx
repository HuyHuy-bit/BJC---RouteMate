import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Car, Lock, UserRound, Users } from "lucide-react";
import { api } from "../lib/api";
import type { TripOut, TripStatus } from "../types";
import { DIRECTION, NEXT_TRIP_ACTION, TRIP_STATUS, fmtVnd } from "../lib/format";
import Badge from "./ui/Badge";
import Button from "./ui/Button";
import Card from "./ui/Card";
import EmptyState from "./ui/EmptyState";
import Skeleton from "./ui/Skeleton";
import { useToast } from "./ui/Toast";

export default function TripsPanel({
  trips,
  loading,
}: {
  trips: TripOut[];
  loading?: boolean;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();

  const driversQuery = useQuery({
    queryKey: ["drivers"],
    queryFn: () => api.users.list("driver"),
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["trips"] });

  const handleAssign = async (trip: TripOut, driverId: string) => {
    if (!driverId) return;
    try {
      await api.dispatch.assignDriver(trip.id, driverId);
      const name = driversQuery.data?.find((d) => d.id === driverId)?.full_name;
      toast(`Đã giao chuyến cho ${name ?? "tài xế"}.`, "success");
      refresh();
    } catch {
      toast("Không giao được chuyến. Thử lại.", "error");
    }
  };

  const handleAdvance = async (trip: TripOut, next: TripStatus, label: string) => {
    try {
      await api.dispatch.updateStatus(trip.id, next);
      toast(`${label} — đã cập nhật.`, "success");
      refresh();
    } catch (err: any) {
      toast(err?.response?.data?.detail ?? "Không cập nhật được chuyến.", "error");
    }
  };

  if (loading) {
    return (
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <Skeleton className="h-52 w-full rounded-[var(--radius-lg)]" count={3} />
      </div>
    );
  }

  if (trips.length === 0) {
    return (
      <EmptyState
        icon={<Car size={18} aria-hidden="true" />}
        title="Chưa có chuyến nào được ghép"
        description="Nhấn “Ghép chuyến” để hệ thống gom khách cùng tuyến, cùng ngày vào một xe."
      />
    );
  }

  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {trips.map((trip, idx) => {
        const status = TRIP_STATUS[trip.status];
        const action = NEXT_TRIP_ACTION[trip.status];
        const revenue = trip.bookings.reduce((s, b) => s + b.price_vnd, 0);
        const direction = trip.bookings[0]?.direction;

        return (
          <Card
            key={trip.id}
            as="article"
            interactive
            accent={trip.is_private ? "var(--brand-red)" : "var(--brand-blue)"}
            className="p-4 flex flex-col"
          >
            <header className="flex items-start justify-between gap-2 mb-3">
              <div>
                <h3 className="text-sm font-semibold flex items-center gap-1.5">
                  <Car size={14} aria-hidden="true" className="text-[var(--text-tertiary)]" />
                  Xe {idx + 1}
                </h3>
                {direction && (
                  <p className="text-[11px] text-[var(--text-tertiary)] mt-0.5">
                    {DIRECTION[direction].label}
                  </p>
                )}
              </div>
              <Badge tone={status.tone}>{status.label}</Badge>
            </header>

            <p className="text-[11px] text-[var(--text-tertiary)] flex items-center gap-1.5 mb-2">
              {trip.is_private ? (
                <>
                  <Lock size={11} aria-hidden="true" /> Bao xe riêng
                </>
              ) : (
                <>
                  <Users size={11} aria-hidden="true" /> {trip.bookings.length}/4 chỗ
                </>
              )}
            </p>

            <ol className="space-y-1.5 mb-4 flex-1">
              {trip.bookings.map((b, i) => (
                <li key={b.id} className="flex items-baseline gap-2 text-[13px]">
                  <span
                    className="tnum text-[10px] text-[var(--text-tertiary)] w-3.5 shrink-0"
                    aria-hidden="true"
                  >
                    {i + 1}
                  </span>
                  <span className="truncate">{b.customer.full_name}</span>
                </li>
              ))}
            </ol>

            <div className="space-y-2 pt-3 border-t border-[var(--border)]">
              <label className="block">
                <span className="sr-only">Tài xế cho xe {idx + 1}</span>
                <div className="flex items-center gap-1.5 text-[11px] text-[var(--text-tertiary)] mb-1">
                  <UserRound size={11} aria-hidden="true" /> Tài xế
                </div>
                <select
                  value={trip.driver_id ?? ""}
                  onChange={(e) => handleAssign(trip, e.target.value)}
                  className="w-full h-8 px-2 text-xs rounded-[var(--radius)] bg-[var(--surface)] border border-[var(--border-strong)] hover:border-[var(--text-tertiary)] focus:border-[var(--border-focus)] transition-colors"
                >
                  <option value="">Chưa giao</option>
                  {driversQuery.data?.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.full_name}
                    </option>
                  ))}
                </select>
              </label>

              {action && (
                <Button
                  variant="secondary"
                  size="sm"
                  fullWidth
                  onClick={() => handleAdvance(trip, action.next, action.label)}
                >
                  {action.label}
                </Button>
              )}

              <div className="flex items-center justify-between pt-1">
                <span className="text-[11px] text-[var(--text-tertiary)]">
                  Doanh thu
                </span>
                <span className="text-sm font-semibold tnum">{fmtVnd(revenue)}</span>
              </div>
            </div>
          </Card>
        );
      })}
    </div>
  );
}
