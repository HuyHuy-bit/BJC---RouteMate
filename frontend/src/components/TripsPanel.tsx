import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Car, Lock, UserRound, Users, Zap, GitMerge } from "lucide-react";
import { api } from "../lib/api";
import type { TripOut, TripStatus } from "../types";
import {
  DIRECTION,
  TRIP_STATUS,
  seatsTaken,
  tripActionFor,
  tripIdentity,
} from "../lib/format";
import Badge from "./ui/Badge";
import Button from "./ui/Button";
import Card from "./ui/Card";
import ConfirmDialog from "./ui/ConfirmDialog";
import EmptyState from "./ui/EmptyState";
import Select from "./ui/Select";
import { useToast } from "./ui/Toast";
import { getErrorMessage } from "../lib/errors";

// Loading and error states belong to the QueryState wrapper at the
// call site, so this component only ever renders real data.
export default function TripsPanel({ trips }: { trips: TripOut[] }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  // Keyed by "<action>:<tripId>" so a spinner appears on the one
  // control being used, not on every card at once.
  const [busy, setBusy] = useState<string | null>(null);
  const [pendingMerge, setPendingMerge] = useState<{
    source: TripOut;
    target: TripOut;
  } | null>(null);
  const [pendingReassign, setPendingReassign] = useState<{
    trip: TripOut;
    driverId: string;
  } | null>(null);
  // Sending a completion claim back puts a trip the driver believed was
  // finished back on their plate, so it asks for a reason first rather
  // than firing on a single tap.
  const [pendingBounce, setPendingBounce] = useState<TripOut | null>(null);
  const [bounceReason, setBounceReason] = useState("");

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
    setBusy(`assign:${trip.id}`);
    try {
      await api.dispatch.assignDriver(trip.id, driverId);
      const name = driversQuery.data?.find((d) => d.id === driverId)?.full_name;
      toast(`Đã giao chuyến cho ${name ?? "tài xế"}.`, "success");
      setPendingReassign(null);
      refresh();
    } catch (err: any) {
      toast(getErrorMessage(err, "Không giao được chuyến. Thử lại."), "error");
      setPendingReassign(null);
    } finally {
      setBusy(null);
    }
  };

  const handleAction = async (trip: TripOut, path: string, label: string) => {
    setBusy(`${path}:${trip.id}`);
    try {
      await api.dispatch.action(trip.id, path);
      toast(`${label} — đã cập nhật.`, "success");
      refresh();
    } catch (err: any) {
      toast(getErrorMessage(err, "Không cập nhật được chuyến."), "error");
    } finally {
      setBusy(null);
    }
  };

  const handleBounce = async (trip: TripOut, reason: string) => {
    setBusy(`reject-completion:${trip.id}`);
    try {
      await api.dispatch.rejectCompletion(trip.id, reason);
      toast("Đã trả chuyến lại cho tài xế.", "success");
      setPendingBounce(null);
      refresh();
    } catch (err: any) {
      toast(getErrorMessage(err, "Không trả lại được chuyến."), "error");
      setPendingBounce(null);
    } finally {
      setBusy(null);
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

  const handleMerge = async (source: TripOut, target: TripOut) => {
    setBusy(`merge:${source.id}`);
    try {
      await api.dispatch.mergeTrips(source.id, target.id);
      toast("Đã gộp hai chuyến.", "success");
      setPendingMerge(null);
      refresh();
    } catch (err: any) {
      toast(getErrorMessage(err, "Không gộp được chuyến."), "error");
      setPendingMerge(null);
    } finally {
      setBusy(null);
    }
  };

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
      {trips.map((trip) => {
        const status = TRIP_STATUS[trip.status];
        // Per-trip revenue is gone from this panel: it is a money
        // rollup, and dispatchers no longer see those (requirements
        // §3). Individual fares still show on the booking rows, which
        // is what a dispatcher actually needs to quote a customer.
        const actions = (trip.available_actions ?? [])
          .map((to) => tripActionFor(trip.status, to))
          .filter((a): a is NonNullable<typeof a> => a !== undefined);
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
            className="p-4 flex flex-col"
          >
            <header className="flex items-start justify-between gap-2 mb-3">
              <div>
                <h3 className="text-base font-semibold flex items-center gap-1.5">
                  <Car size={14} aria-hidden="true" className="text-faint" />
                  {tripIdentity(trip)}
                </h3>
                {direction && (
                  <p className="text-2xs text-faint mt-0.5">
                    {DIRECTION[direction].label}
                  </p>
                )}
              </div>
              <Badge tone={status.tone}>{status.label}</Badge>
            </header>

            <p className="text-2xs text-faint flex items-center gap-1.5 mb-2">
              {trip.is_private ? (
                <>
                  <Lock size={11} aria-hidden="true" /> Bao xe riêng
                </>
              ) : (
                <>
                  {/* Seats, not booking count — one booking can be a
                      family of several. */}
                  <Users size={11} aria-hidden="true" />{" "}
                  {seatsTaken(trip.bookings)}/4 chỗ
                </>
              )}
            </p>

            <ol className="space-y-1.5 mb-4 flex-1">
              {trip.bookings.map((b, i) => (
                <li key={b.id} className="flex items-baseline gap-2 text-sm">
                  <span
                    className="tnum text-2xs text-faint w-3.5 shrink-0"
                    aria-hidden="true"
                  >
                    {i + 1}
                  </span>
                  <span className="truncate">{b.customer.full_name}</span>
                </li>
              ))}
            </ol>

            <div className="space-y-2 pt-3 border-t border-line">
              {!isForming && (
                <Select
                  label={`Tài xế cho ${tripIdentity(trip)}`}
                  labelHidden
                  icon={<UserRound size={11} aria-hidden="true" />}
                  value={trip.driver_id ?? ""}
                  placeholder="Chưa giao"
                  pending={busy === `assign:${trip.id}`}
                  options={[
                    { value: "", label: "Chưa giao" },
                    ...(driversQuery.data ?? []).map((d) => ({
                      value: d.id,
                      label: d.full_name,
                    })),
                  ]}
                  onChange={(driverId) => {
                    // Reassigning a driver who is already en route is
                    // disruptive enough to be worth a question; the
                    // first assignment isn't.
                    if (trip.driver_id && driverId !== trip.driver_id) {
                      setPendingReassign({ trip, driverId });
                    } else {
                      handleAssign(trip, driverId);
                    }
                  }}
                />
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
                    /* Merging is irreversible and used to fire straight
                       off the native select's change event — one stray
                       arrow-key press away. Choosing a target now only
                       stages it; the confirm dialog commits it. */
                    <Select
                      label="Gộp với chuyến khác"
                      icon={<GitMerge size={11} aria-hidden="true" />}
                      value=""
                      placeholder="Chọn chuyến để gộp..."
                      pending={busy === `merge:${trip.id}`}
                      options={mergeCandidates.map((t) => ({
                        value: t.id,
                        label: tripIdentity(t),
                        detail: `${seatsTaken(t.bookings)} chỗ đã đặt`,
                      }))}
                      onChange={(targetId) => {
                        const target = trips.find((t) => t.id === targetId);
                        if (target) setPendingMerge({ source: trip, target });
                      }}
                    />
                  )}
                </>
              )}

              {/* Actions come from the backend's available_actions, so
                  a dispatcher is never offered Start or Complete — those
                  transitions are driver-only and the server refuses
                  them. This panel used to render them unconditionally. */}
              {actions.map((a) => (
                <Button
                  key={a.path}
                  variant={a.tone === "danger" ? "ghost" : "secondary"}
                  size="sm"
                  fullWidth
                  loading={busy === `${a.path}:${trip.id}`}
                  onClick={() =>
                    a.path === "reject-completion"
                      ? setPendingBounce(trip)
                      : handleAction(trip, a.path, a.label)
                  }
                >
                  {a.label}
                </Button>
              ))}
            </div>
          </Card>
        );
      })}

      <ConfirmDialog
        open={pendingMerge !== null}
        title="Gộp hai chuyến này?"
        description={
          pendingMerge
            ? `Toàn bộ khách của ${tripIdentity(pendingMerge.source)} sẽ chuyển sang ${tripIdentity(pendingMerge.target)} — tổng ${seatsTaken([...pendingMerge.source.bookings, ...pendingMerge.target.bookings])} chỗ. Thao tác này không thể hoàn tác; nếu vượt quá số chỗ của xe, hệ thống sẽ từ chối.`
            : undefined
        }
        confirmLabel="Gộp chuyến"
        loading={busy?.startsWith("merge:") ?? false}
        onConfirm={() =>
          pendingMerge && handleMerge(pendingMerge.source, pendingMerge.target)
        }
        onCancel={() => setPendingMerge(null)}
      />

      <ConfirmDialog
        open={pendingReassign !== null}
        title="Đổi tài xế cho chuyến này?"
        description={
          pendingReassign
            ? `Chuyến đã được giao cho một tài xế. Đổi sang ${
                driversQuery.data?.find((d) => d.id === pendingReassign.driverId)
                  ?.full_name ?? "tài xế khác"
              } sẽ gỡ chuyến khỏi tài xế hiện tại — hãy gọi cho họ để họ không chờ vô ích.`
            : undefined
        }
        confirmLabel="Đổi tài xế"
        loading={busy?.startsWith("assign:") ?? false}
        onConfirm={() =>
          pendingReassign &&
          handleAssign(pendingReassign.trip, pendingReassign.driverId)
        }
        onCancel={() => setPendingReassign(null)}
      />

      <ConfirmDialog
        open={pendingBounce !== null}
        title="Trả chuyến lại cho tài xế?"
        description="Tài xế đã báo hoàn thành chuyến này. Trả lại sẽ đưa chuyến về trạng thái đang chạy — xe vẫn tính là đang bận và vị trí xe chưa được cập nhật."
        confirmLabel="Trả lại tài xế"
        loading={busy?.startsWith("reject-completion:") ?? false}
        confirmDisabled={bounceReason.trim().length === 0}
        onConfirm={() =>
          pendingBounce && handleBounce(pendingBounce, bounceReason.trim())
        }
        onCancel={() => {
          setPendingBounce(null);
          setBounceReason("");
        }}
      >
        <label className="block">
          <span className="text-2xs text-faint">Lý do (tài xế sẽ thấy)</span>
          <input
            type="text"
            value={bounceReason}
            onChange={(e) => setBounceReason(e.target.value)}
            placeholder="VD: chưa trả khách cuối"
            className="mt-1 w-full h-touch px-3 text-base rounded border border-line-strong bg-surface focus:border-line-focus transition-colors"
          />
        </label>
      </ConfirmDialog>
    </div>
  );
}
