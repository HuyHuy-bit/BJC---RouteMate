import type { TripOut } from "../types";

function fmtVnd(n: number) {
  return n.toLocaleString("vi-VN") + "đ";
}

export default function TripsPanel({ trips }: { trips: TripOut[] }) {
  if (trips.length === 0) return null;

  return (
    <div>
      <div
        className="text-sm font-semibold mb-2"
        style={{ fontFamily: "'Space Grotesk', sans-serif" }}
      >
        Xe được ghép ({trips.length})
      </div>
      <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))" }}>
        {trips.map((trip, idx) => {
          const revenue = trip.bookings.reduce((sum, b) => sum + b.price_vnd, 0);
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
                  style={{ fontFamily: "'Space Grotesk', sans-serif" }}
                >
                  Xe {idx + 1}
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
              <ol className="text-sm space-y-1">
                {trip.bookings.map((b, i) => (
                  <li key={b.id}>
                    {i + 1}. {b.customer.full_name}
                  </li>
                ))}
              </ol>
              <div
                className="text-sm font-semibold mt-2 pt-2 border-t"
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
