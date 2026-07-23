import { useState } from "react";
import type { BookingOut } from "../types";
import { api } from "../lib/api";

const STATUS_LABEL: Record<string, string> = {
  queued: "Trong hàng chờ",
  matched: "Đã ghép xe",
  waiting: "Chờ ghép thêm",
  cancelled: "Đã hủy",
};

const DIRECTION_LABEL: Record<string, string> = {
  outbound: "→ Hà Nội",
  return: "→ Bắc Giang",
};

const STATUS_COLOR: Record<string, string> = {
  queued: "var(--mute)",
  matched: "var(--teal)",
  waiting: "var(--amber)",
  cancelled: "var(--coral)",
};

function fmtVnd(n: number) {
  return n.toLocaleString("vi-VN") + "đ";
}

function fmtDateTime(iso: string) {
  const d = new Date(iso);
  return d.toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function BookingsList({
  bookings,
  onChanged,
}: {
  bookings: BookingOut[];
  onChanged: () => void;
}) {
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const handleDeleteCustomer = async (booking: BookingOut) => {
    const confirmed = window.confirm(
      `Xóa vĩnh viễn khách "${booking.customer.full_name}" và toàn bộ lịch sử đặt xe của họ? Hành động này không thể hoàn tác.`
    );
    if (!confirmed) return;

    setDeletingId(booking.id);
    try {
      await api.customers.delete(booking.customer.id);
      onChanged();
    } catch {
      alert("Không thể xóa khách hàng.");
    } finally {
      setDeletingId(null);
    }
  };

  if (bookings.length === 0) {
    return (
      <div
        className="text-sm text-center py-6 border rounded border-dashed"
        style={{ color: "var(--mute)", borderColor: "var(--line)" }}
      >
        Chưa có khách nào.
      </div>
    );
  }

  return (
    <div className="border rounded overflow-hidden" style={{ borderColor: "var(--line)" }}>
      {bookings.map((b) => (
        <div
          key={b.id}
          className="flex items-center justify-between px-4 py-2 text-sm border-b last:border-b-0 bg-white"
          style={{ borderColor: "var(--line)" }}
        >
          <div>
            <div className="font-semibold">{b.customer.full_name}</div>
            <div
              className="text-xs"
              style={{ color: "var(--mute)", fontFamily: "'JetBrains Mono', monospace" }}
            >
              {b.pickup_address} → {b.dropoff_address}
            </div>
            <div
              className="text-xs mt-0.5"
              style={{ color: "var(--mute)", fontFamily: "'JetBrains Mono', monospace" }}
            >
              {fmtDateTime(b.requested_pickup_at)}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span
              className="text-xs border rounded px-2 py-0.5"
              style={{ color: "var(--mute)", borderColor: "var(--line)" }}
            >
              {DIRECTION_LABEL[b.direction]}
            </span>
            {b.is_private && (
              <span
                className="text-xs border rounded px-2 py-0.5"
                style={{ color: "var(--coral)", borderColor: "var(--coral)" }}
              >
                RIÊNG
              </span>
            )}
            <span
              className="text-xs border rounded px-2 py-0.5"
              style={{
                color: STATUS_COLOR[b.status],
                borderColor: STATUS_COLOR[b.status],
                fontFamily: "'JetBrains Mono', monospace",
              }}
            >
              {STATUS_LABEL[b.status]}
            </span>
            <span
              className="text-sm"
              style={{ fontFamily: "'JetBrains Mono', monospace" }}
            >
              {fmtVnd(b.price_vnd)}
            </span>
            <button
              onClick={() => handleDeleteCustomer(b)}
              disabled={deletingId === b.id}
              title="Xóa khách hàng này vĩnh viễn"
              className="text-xs underline"
              style={{ color: "var(--coral)" }}
            >
              {deletingId === b.id ? "..." : "Xóa"}
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
