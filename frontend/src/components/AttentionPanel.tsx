import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Ban, Car, Clock, Lock, Phone, Users, Wrench } from "lucide-react";
import { api } from "../lib/api";
import type { AttentionItem } from "../types";
import { DIRECTION } from "../lib/format";
import Badge from "./ui/Badge";
import Button from "./ui/Button";
import Card from "./ui/Card";
import { ErrorState } from "./ui/QueryState";
import { useToast } from "./ui/Toast";
import { getErrorMessage } from "../lib/errors";

// How much longer "wait a bit more" actually means. Matches the
// backend's TripExtendWait default.
const EXTEND_MINUTES = 20;

const OPTION_LABEL: Record<string, string> = {
  merge_with_nearby_pool: "Gộp với chuyến gần đó",
  offer_extended_wait: "Chờ thêm khách",
  offer_private_upgrade: "Đề nghị bao xe riêng",
  dispatch_at_loss: "Vẫn cho xe chạy dù chưa đủ khách",
  // Customers pay only after the trip, so a trip that never runs has
  // nothing to refund — the old "Hoàn tiền và huỷ" label promised a
  // step that doesn't exist in this business.
  cancel: "Huỷ chuyến",
};

const KIND_BADGE: Record<AttentionItem["kind"], { icon: JSX.Element; label: string }> = {
  no_vehicle: { icon: <Car size={10} aria-hidden="true" />, label: "Hết xe" },
  vehicle_down: {
    icon: <Wrench size={10} aria-hidden="true" />,
    label: "Xe gặp sự cố",
  },
  escalated: { icon: <Users size={10} aria-hidden="true" />, label: "Thiếu khách" },
};

export default function AttentionPanel() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState<string | null>(null);

  const attentionQuery = useQuery({
    queryKey: ["attention"],
    queryFn: () => api.dispatch.attention(),
    refetchInterval: 30_000,
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["attention"] });
    queryClient.invalidateQueries({ queryKey: ["trips"] });
    queryClient.invalidateQueries({ queryKey: ["bookings"] });
  };

  const handleForceSeal = async (item: AttentionItem) => {
    try {
      await api.dispatch.sealTrip(item.trip_id);
      toast("Đã chốt chuyến.", "success");
      refresh();
    } catch (err: any) {
      toast(getErrorMessage(err, "Không chốt được chuyến."), "error");
    }
  };

  const handleCancelAll = async (item: AttentionItem) => {
    try {
      await Promise.all(item.bookings.map((b) => api.bookings.cancel(b.id)));
      toast("Đã huỷ chuyến.", "success");
      refresh();
    } catch {
      toast("Không huỷ được toàn bộ khách. Kiểm tra lại.", "error");
    }
  };

  const handleExtendWait = async (item: AttentionItem) => {
    setBusy(item.trip_id);
    try {
      await api.dispatch.extendWait(item.trip_id, EXTEND_MINUTES);
      toast(`Đã gia hạn thêm ${EXTEND_MINUTES} phút.`, "success");
      refresh();
    } catch (err: any) {
      toast(getErrorMessage(err, "Không gia hạn được."), "error");
    } finally {
      setBusy(null);
    }
  };

  const handleUpgradePrivate = async (item: AttentionItem) => {
    setBusy(item.trip_id);
    try {
      await api.dispatch.upgradePrivate(item.trip_id);
      toast("Đã chuyển thành bao xe riêng và cho xe chạy.", "success");
      refresh();
    } catch (err: any) {
      toast(getErrorMessage(err, "Không chuyển được sang bao xe."), "error");
    } finally {
      setBusy(null);
    }
  };

  // This panel hides itself when there's nothing to act on, which is
  // right — but it must not hide itself when it simply failed to ask.
  // These are trips that need a human to phone a customer; silently
  // vanishing is the most expensive failure mode on this screen.
  if (attentionQuery.isError) {
    return (
      <div className="mb-6">
        <ErrorState
          title="Không kiểm tra được chuyến cần xử lý"
          message={getErrorMessage(
            attentionQuery.error,
            "Có thể đang có chuyến cần bạn gọi khách mà hệ thống chưa tải được. Thử lại để kiểm tra."
          )}
          onRetry={() => attentionQuery.refetch()}
          retrying={attentionQuery.isFetching}
        />
      </div>
    );
  }

  const items = attentionQuery.data ?? [];
  if (!attentionQuery.isPending && items.length === 0) return null;

  return (
    <div className="mb-6">
      <h2 className="text-base font-semibold mb-2 flex items-center gap-1.5">
        <AlertTriangle size={14} className="text-warning" aria-hidden="true" />
        Cần xử lý
        {items.length > 0 && (
          <span className="text-warning tnum">({items.length})</span>
        )}
      </h2>

      <div className="space-y-2">
        {items.map((item) => (
          <Card
            key={item.trip_id}
            className="p-4 border-l-[3px] border-l-warning"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap mb-1">
                  <Badge tone="warning">
                    {KIND_BADGE[item.kind].icon} {KIND_BADGE[item.kind].label}
                  </Badge>
                  <span className="text-xs text-faint">
                    {DIRECTION[item.direction].label} · {item.passenger_count} khách
                    {item.minutes_overdue > 0 &&
                      ` · trễ ${Math.round(item.minutes_overdue)} phút`}
                  </span>
                </div>
                <p className="text-base text-ink">{item.reason}</p>
                {/* Tap-to-call: resolving one of these means phoning
                    the customer — there's no customer-facing channel,
                    so don't make staff copy a number by hand. */}
                <ul className="text-xs text-faint mt-1 space-y-0.5">
                  {item.bookings.map((b) => (
                    <li key={b.id} className="flex items-center gap-1.5">
                      <span>{b.customer.full_name}</span>
                      <a
                        href={`tel:${b.customer.phone}`}
                        className="inline-flex items-center gap-1 text-cobalt font-medium hover:underline"
                        aria-label={`Gọi ${b.customer.full_name}`}
                      >
                        <Phone size={11} aria-hidden="true" />
                        <span className="tnum">{b.customer.phone}</span>
                      </a>
                    </li>
                  ))}
                </ul>

                {item.options && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {item.options.map((o) => (
                      <span
                        key={o}
                        className="text-2xs px-1.5 py-0.5 rounded bg-sunken text-faint"
                      >
                        {OPTION_LABEL[o] ?? o}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {/* Outcomes of the phone call the dispatcher just made.
                  Order matches what's most likely to save the trip:
                  wait a bit more, sell it as a private hire, send it
                  anyway, or give up. */}
              <div className="flex flex-col gap-1.5 shrink-0">
                {item.kind === "escalated" && (
                  <>
                    <Button
                      variant="secondary"
                      size="sm"
                      disabled={busy === item.trip_id}
                      iconLeft={<Clock size={12} aria-hidden="true" />}
                      onClick={() => handleExtendWait(item)}
                    >
                      Chờ thêm {EXTEND_MINUTES} phút
                    </Button>
                    {item.passenger_count === 1 && (
                      <Button
                        variant="secondary"
                        size="sm"
                        disabled={busy === item.trip_id}
                        iconLeft={<Lock size={12} aria-hidden="true" />}
                        onClick={() => handleUpgradePrivate(item)}
                      >
                        Khách đồng ý bao xe
                      </Button>
                    )}
                    <Button
                      variant="secondary"
                      size="sm"
                      disabled={busy === item.trip_id}
                      onClick={() => handleForceSeal(item)}
                    >
                      Vẫn cho chạy
                    </Button>
                  </>
                )}
                <Button
                  variant="danger-subtle"
                  size="sm"
                  disabled={busy === item.trip_id}
                  iconLeft={<Ban size={12} aria-hidden="true" />}
                  onClick={() => handleCancelAll(item)}
                >
                  Huỷ chuyến
                </Button>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
