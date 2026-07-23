import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import type { TripOut } from "../types";

const NEXT_STATUS: Record<string, { label: string; next: string } | undefined> = {
  confirmed: { label: "Bắt đầu chuyến", next: "in_progress" },
  in_progress: { label: "Hoàn thành chuyến", next: "completed" },
};

function fmtVnd(n: number) {
  return n.toLocaleString("vi-VN") + "đ";
}

function fmtDateTime(iso: string) {
  return new Date(iso).toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function TripCard({ trip, onAdvance }: { trip: TripOut; onAdvance: () => void }) {
  const action = NEXT_STATUS[trip.status];
  const sorted = [...trip.bookings].sort(
    (a, b) => (a.pickup_lng ?? 0) - (b.pickup_lng ?? 0)
  );

  const handleAdvance = async () => {
    if (!action) return;
    await api.dispatch.updateStatus(trip.id, action.next as TripOut["status"]);
    onAdvance();
  };

  return (
    <div
      className="bg-white border rounded p-4 mb-4"
      style={{
        borderColor: "var(--line)",
        borderLeft: `5px solid ${trip.is_private ? "var(--coral)" : "var(--teal)"}`,
      }}
    >
      <div className="flex justify-between items-center mb-3">
        <span
          className="text-xs"
          style={{ color: "var(--teal)", fontFamily: "'JetBrains Mono', monospace" }}
        >
          {trip.status === "confirmed" ? "SẴN SÀNG CHẠY" : "ĐANG CHẠY"}
        </span>
        <span className="text-xs" style={{ color: "var(--mute)" }}>
          {trip.is_private ? "Bao xe riêng" : `${trip.bookings.length}/4 khách`}
        </span>
      </div>

      <ol className="space-y-3 mb-4">
        {sorted.map((b, i) => (
          <li
            key={b.id}
            className="text-sm border-b pb-2 last:border-b-0"
            style={{ borderColor: "var(--line)" }}
          >
            <div className="font-semibold">
              {i + 1}. {b.customer.full_name}{" "}
              <span style={{ color: "var(--mute)", fontWeight: 400 }}>
                — {b.customer.phone}
              </span>
            </div>
            <div className="text-xs mt-1" style={{ color: "var(--mute)" }}>
              Đón: {b.pickup_address}
            </div>
            <div className="text-xs" style={{ color: "var(--mute)" }}>
              Trả: {b.dropoff_address}
            </div>
            <div
              className="text-xs mt-1"
              style={{ fontFamily: "'JetBrains Mono', monospace" }}
            >
              {fmtDateTime(b.requested_pickup_at)} · {fmtVnd(b.price_vnd)}
            </div>
          </li>
        ))}
      </ol>

      {action && (
        <button
          onClick={handleAdvance}
          className="w-full rounded py-2 text-sm font-semibold text-white"
          style={{ background: "var(--ink)" }}
        >
          {action.label}
        </button>
      )}
    </div>
  );
}

export default function DriverDashboard() {
  const { user, logout } = useAuth();
  const queryClient = useQueryClient();

  const tripsQuery = useQuery({
    queryKey: ["my-trips"],
    queryFn: () => api.dispatch.myTrips(),
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["my-trips"] });

  return (
    <div className="min-h-screen" style={{ background: "var(--paper)" }}>
      <div className="max-w-md mx-auto px-4 py-6">
        <div
          className="flex justify-between items-end mb-5 pb-3 border-b-2"
          style={{ borderColor: "var(--ink)" }}
        >
          <div className="flex items-center gap-2">
            <img
              src="/bjc-logo.jpg"
              alt="BJC Group"
              className="w-9 h-9 rounded-full object-cover"
            />
            <div>
              <div
                className="text-xs tracking-widest mb-1"
                style={{ color: "var(--coral)", fontFamily: "'JetBrains Mono', monospace" }}
              >
                THÀNH CÔNG · TÀI XẾ
              </div>
              <h1
                className="text-xl font-bold"
                style={{ fontFamily: "'Sora', sans-serif" }}
              >
                {user?.full_name}
              </h1>
            </div>
          </div>
          <button
            onClick={logout}
            className="text-xs font-medium rounded px-3 py-1.5 border"
            style={{ color: "var(--coral)", borderColor: "var(--coral)" }}
          >
            Đăng xuất
          </button>
        </div>

        {tripsQuery.isLoading && (
          <div className="text-sm" style={{ color: "var(--mute)" }}>
            Đang tải...
          </div>
        )}

        {tripsQuery.data && tripsQuery.data.length === 0 && (
          <div
            className="text-sm text-center py-8 border rounded border-dashed"
            style={{ color: "var(--mute)", borderColor: "var(--line)" }}
          >
            Chưa có chuyến nào được giao cho bạn.
          </div>
        )}

        {tripsQuery.data?.map((trip) => (
          <TripCard key={trip.id} trip={trip} onAdvance={refresh} />
        ))}
      </div>
    </div>
  );
}
