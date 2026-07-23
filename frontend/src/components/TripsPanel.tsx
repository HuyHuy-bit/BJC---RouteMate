import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { TripOut } from "../types";

const DIRECTION_LABEL: Record<string, string> = {
  outbound: "→ Hà Nội",
  return: "→ Bắc Giang",
};

function fmtVnd(n: number) {
  return n.toLocaleString("vi-VN") + "đ";
}

const NEXT_STATUS: Record<string, { label: string; next: string } | undefined> = {
  confirmed: { label: "Bắt đầu chuyến", next: "in_progress" },
  in_progress: { label: "Hoàn thành", next: "completed" },
};

export default function TripsPanel({ trips }: { trips: TripOut[] }) {
  const queryClient = useQueryClient();
  const driversQuery = useQuery({
    queryKey: ["drivers"],
    queryFn: () => api.users.list("driver"),
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["trips"] });
  };

  const handleAssign = async (tripId: string, driverId: string) => {
    if (!driverId) return;
    await api.dispatch.assignDriver(tripId, driverId);
    refresh();
  };

  const handleAdvanceStatus = async (tripId: string, nextStatus: string) => {
    await api.dispatch.updateStatus(tripId, nextStatus as TripOut["status"]);
    refresh();
  };

  if (trips.length === 0) return null;

  return (
    <div>
      <div
        className="text-sm font-semibold mb-2"
        style={{ fontFamily: "'Sora', sans-serif" }}
      >
        Xe được ghép ({trips.length})
      </div>
      <div
        className="grid gap-3"
        style={{ gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))" }}
      >
        {trips.map((trip, idx) => {
          const revenue = trip.bookings.reduce((sum, b) => sum + b.price_vnd, 0);
          const action = NEXT_STATUS[trip.status];
          const assignedDriver = driversQuery.data?.find(
            (d) => d.id === trip.driver_id
          );

          return (
            <div
              key={trip.id}
              className="bg-white border rounded p-3"
              style={{
                borderColor: "var(--line)",
                borderLeft: `5px solid ${trip.is_private ? "var(--coral)" : "var(--teal)"}`,
              }}
            >
              <div className="flex justify-between items-center mb-2">
                <div
                  className="text-sm font-semibold"
                  style={{ fontFamily: "'Sora', sans-serif" }}
                >
                  Xe {idx + 1}{" "}
                  <span style={{ fontWeight: 400, color: "var(--mute)", fontSize: 11 }}>
                    {DIRECTION_LABEL[trip.bookings[0]?.direction]}
                  </span>
                </div>
                <span
                  className="text-xs"
                  style={{ color: "var(--teal)", fontFamily: "'JetBrains Mono', monospace" }}
                >
                  {trip.status.toUpperCase()}
                </span>
              </div>
              <div className="text-xs mb-2" style={{ color: "var(--mute)" }}>
                {trip.is_private ? "Bao xe riêng" : `${trip.bookings.length}/4 chỗ`}
              </div>
              <ol className="text-sm space-y-1 mb-2">
                {trip.bookings.map((b, i) => (
                  <li key={b.id}>
                    {i + 1}. {b.customer.full_name}
                  </li>
                ))}
              </ol>

              <div className="text-xs mb-1" style={{ color: "var(--mute)" }}>
                Tài xế
              </div>
              <select
                className="w-full border rounded px-2 py-1 text-xs mb-2"
                style={{ borderColor: "var(--line)" }}
                value={trip.driver_id ?? ""}
                onChange={(e) => handleAssign(trip.id, e.target.value)}
              >
                <option value="">
                  {assignedDriver ? assignedDriver.full_name : "-- Chưa gán --"}
                </option>
                {driversQuery.data
                  ?.filter((d) => d.id !== trip.driver_id)
                  .map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.full_name}
                    </option>
                  ))}
              </select>

              {action && (
                <button
                  onClick={() => handleAdvanceStatus(trip.id, action.next)}
                  className="w-full text-xs rounded py-1.5 font-semibold text-white mb-2"
                  style={{ background: "var(--ink)" }}
                >
                  {action.label}
                </button>
              )}

              <div
                className="text-sm font-semibold pt-2 border-t"
                style={{ borderColor: "var(--line)", fontFamily: "'JetBrains Mono', monospace" }}
              >
                {fmtVnd(revenue)}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
