import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Car, Lock, UserRound, Users, Zap, GitMerge } from "lucide-react";
import { api } from "../lib/api";
import type { TripOut, TripStatus } from "../types";
import { DIRECTION, NEXT_TRIP_ACTION, TRIP_STATUS, fmtVnd } from "../lib/format";
import Badge from "./ui/Badge";
import Button from "./ui/Button";
import Card from "./ui/Card";
import EmptyState from "./ui/EmptyState";
import Skeleton from "./ui/Skeleton";
import { useToast } from "./ui/Toast";
import { getErrorMessage } from "../lib/errors";

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

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["trips"] });
    queryClient.invalidateQueries({ queryKey: ["attention"] });
    queryClient.invalidateQueries({ queryKey: ["bookings"] });
  };

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
      toast(getErrorMessage(err, "Không cập nhật được chuyến."), "error");
    }
  };

  const handleForceSeal = async (trip: TripOut) => {
    try {
      await api.dispatch.sealTrip(trip.id);
      toast("Đã chốt chuyến.", "success");
      refresh();
    } catch (err: any) {
      toast(getErrorMessage(err, "Không chốt được chuyến."), "error");
    }
  };

  const handleMerge = async (sourceId: string, targetId: string) => {
    try {
      await api.dispatch.mergeTrips(sourceId, targetId);
      toast("Đã gộp hai chuyến.", "success");
      refresh();
    } catch (err: any) {
      toast(getErrorMessage(err, "Không gộp được chuyến."), "error");
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
        const isForming = trip.status === "forming";

        // Other forming pools going the same way — merge candidates.
        const mergeCandidates = isForming
          ? trips.filter(
              (t) =>
                t.id !== trip.id &&
                t.status === "forming" &&
                t.bookings[0]?.direction === direction
            )
          : [];

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
              {!isForming && (
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
              )}

              {isForming && (
                <>
                  {/* Manual overrides — the algorithm doesn't get every
                      case right, and a dispatcher who can't intervene
                      will stop trusting it. */}
                  <Button
                    variant="secondary"
                    size="sm"
                    fullWidth
                    iconLeft={<Zap size={13} aria-hidden="true" />}
                    onClick={() => handleForceSeal(trip)}
                  >
                    Chốt ngay
                  </Button>

                  {mergeCandidates.length > 0 && (
                    <label className="block">
                      <span className="flex items-center gap-1.5 text-[11px] text-[var(--text-tertiary)] mb-1">
                        <GitMerge size={11} aria-hidden="true" /> Gộp với xe khác
                      </span>
                      <select
                        value=""
                        onChange={(e) => {
                          if (e.target.value) handleMerge(trip.id, e.target.value);
                        }}
                        className="w-full h-8 px-2 text-xs rounded-[var(--radius)] bg-[var(--surface)] border border-[var(--border-strong)] hover:border-[var(--text-tertiary)] focus:border-[var(--border-focus)] transition-colors"
                      >
                        <option value="">Chọn xe để gộp...</option>
                        {mergeCandidates.map((t) => {
                          const tIdx = trips.findIndex((x) => x.id === t.id);
                          return (
                            <option key={t.id} value={t.id}>
                              Xe {tIdx + 1} ({t.bookings.length} khách)
                            </option>
                          );
                        })}
                      </select>
                    </label>
                  )}
                </>
              )}

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
