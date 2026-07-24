import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Ban, Car, Users, Wrench } from "lucide-react";
import { api } from "../lib/api";
import type { AttentionItem } from "../types";
import { DIRECTION } from "../lib/format";
import Badge from "./ui/Badge";
import Button from "./ui/Button";
import Card from "./ui/Card";
import { useToast } from "./ui/Toast";
import { getErrorMessage } from "../lib/errors";

const OPTION_LABEL: Record<string, string> = {
  merge_with_nearby_pool: "Gộp với chuyến gần đó",
  offer_extended_wait: "Chờ thêm khách",
  offer_private_upgrade: "Đề nghị bao xe riêng",
  dispatch_at_loss: "Vẫn cho xe chạy dù chưa đủ khách",
  refund_and_cancel: "Hoàn tiền và huỷ chuyến",
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
      toast("Đã huỷ và hoàn tất xử lý.", "success");
      refresh();
    } catch {
      toast("Không huỷ được toàn bộ khách. Kiểm tra lại.", "error");
    }
  };

  const items = attentionQuery.data ?? [];
  if (!attentionQuery.isLoading && items.length === 0) return null;

  return (
    <div className="mb-6">
      <h2 className="text-sm font-semibold mb-2 flex items-center gap-1.5">
        <AlertTriangle size={14} className="text-[var(--warning)]" aria-hidden="true" />
        Cần xử lý
        {items.length > 0 && (
          <span className="text-[var(--warning)] tnum">({items.length})</span>
        )}
      </h2>

      <div className="space-y-2">
        {items.map((item) => (
          <Card
            key={item.trip_id}
            className="p-4 border-l-[3px] border-l-[var(--warning)]"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap mb-1">
                  <Badge tone="warning">
                    {KIND_BADGE[item.kind].icon} {KIND_BADGE[item.kind].label}
                  </Badge>
                  <span className="text-xs text-[var(--text-tertiary)]">
                    {DIRECTION[item.direction].label} · {item.passenger_count} khách
                    {item.minutes_overdue > 0 &&
                      ` · trễ ${Math.round(item.minutes_overdue)} phút`}
                  </span>
                </div>
                <p className="text-sm text-[var(--text)]">{item.reason}</p>
                <ul className="text-xs text-[var(--text-tertiary)] mt-1">
                  {item.bookings.map((b) => (
                    <li key={b.id}>
                      {b.customer.full_name} — {b.customer.phone}
                    </li>
                  ))}
                </ul>

                {item.options && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {item.options.map((o) => (
                      <span
                        key={o}
                        className="text-[10px] px-1.5 py-0.5 rounded-[var(--radius-sm)] bg-[var(--surface-sunken)] text-[var(--text-tertiary)]"
                      >
                        {OPTION_LABEL[o] ?? o}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              <div className="flex flex-col gap-1.5 shrink-0">
                {item.kind === "escalated" && (
                  <Button variant="secondary" size="sm" onClick={() => handleForceSeal(item)}>
                    Vẫn cho chạy
                  </Button>
                )}
                <Button
                  variant="danger-subtle"
                  size="sm"
                  iconLeft={<Ban size={12} aria-hidden="true" />}
                  onClick={() => handleCancelAll(item)}
                >
                  Huỷ & hoàn tiền
                </Button>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
