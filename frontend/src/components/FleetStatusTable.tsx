import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Car, MapPin, Navigation, TriangleAlert } from "lucide-react";
import { api } from "../lib/api";
import type { TripOut } from "../types";
import {
  DIRECTION,
  fmtTime,
  tripLocationState,
  type FleetPlace,
} from "../lib/format";
import Badge from "./ui/Badge";
import Card from "./ui/Card";
import EmptyState from "./ui/EmptyState";
import Skeleton from "./ui/Skeleton";

const PLACE_SUMMARY: {
  place: FleetPlace;
  label: string;
  icon: JSX.Element;
}[] = [
  {
    place: "bac_giang",
    label: "Tại Bắc Giang",
    icon: <MapPin size={13} aria-hidden="true" />,
  },
  {
    place: "ha_noi",
    label: "Tại Hà Nội",
    icon: <MapPin size={13} aria-hidden="true" />,
  },
  {
    place: "running",
    label: "Đang chạy",
    icon: <Navigation size={13} aria-hidden="true" />,
  },
  {
    place: "issue",
    label: "Cần xử lý",
    icon: <TriangleAlert size={13} aria-hidden="true" />,
  },
];

export default function FleetStatusTable({
  trips,
  loading,
}: {
  trips: TripOut[];
  loading?: boolean;
}) {
  // Driver names aren't on TripOut (only driver_id), so resolve them
  // from the roster the dispatcher already loads elsewhere.
  const driversQuery = useQuery({
    queryKey: ["drivers"],
    queryFn: () => api.users.list("driver"),
  });

  const rows = useMemo(
    () =>
      trips.map((trip) => {
        const direction = trip.bookings[0]?.direction;
        const state = tripLocationState(trip.status, direction);
        const seats = trip.bookings.reduce((n, b) => n + (b.seats ?? 1), 0);
        // Earliest pickup and latest dropoff bound the whole trip.
        const pickups = trip.bookings
          .map((b) => b.estimated_pickup_at ?? b.requested_pickup_at)
          .filter(Boolean)
          .sort();
        const dropoffs = trip.bookings
          .map((b) => b.estimated_dropoff_at)
          .filter((v): v is string => Boolean(v))
          .sort();
        return {
          trip,
          direction,
          state,
          seats,
          departsAt: pickups[0],
          arrivesAt: dropoffs[dropoffs.length - 1],
          driverName:
            driversQuery.data?.find((d) => d.id === trip.driver_id)?.full_name ??
            null,
        };
      }),
    [trips, driversQuery.data]
  );

  const counts = useMemo(() => {
    const c: Record<FleetPlace, number> = {
      bac_giang: 0,
      ha_noi: 0,
      running: 0,
      issue: 0,
    };
    for (const r of rows) c[r.state.place] += 1;
    return c;
  }, [rows]);

  if (loading) {
    return <Skeleton className="h-56 w-full rounded-[var(--radius-lg)]" />;
  }

  return (
    <Card className="overflow-hidden">
      <div className="px-4 py-3 border-b border-[var(--border)]">
        <h2 className="text-sm font-semibold">Tình trạng đội xe</h2>
        <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2">
          {PLACE_SUMMARY.map((s) => (
            <span
              key={s.place}
              className="inline-flex items-center gap-1.5 text-[11px] text-[var(--text-tertiary)]"
            >
              {s.icon}
              {s.label}
              <span className="tnum font-semibold text-[var(--text)]">
                {counts[s.place]}
              </span>
            </span>
          ))}
        </div>
      </div>

      {rows.length === 0 ? (
        <EmptyState
          icon={<Car size={18} aria-hidden="true" />}
          title="Chưa có chuyến nào đang hoạt động"
          description="Khi có chuyến được ghép, tình trạng từng xe sẽ hiện ở đây."
        />
      ) : (
        // Wide table scrolls inside its own container so the page body
        // never scrolls sideways on a narrow screen.
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse min-w-[640px]">
            <thead>
              <tr className="text-[11px] text-[var(--text-tertiary)]">
                <th scope="col" className="font-medium px-4 py-2">
                  Xe
                </th>
                <th scope="col" className="font-medium px-4 py-2">
                  Tài xế
                </th>
                <th scope="col" className="font-medium px-4 py-2">
                  Tuyến
                </th>
                <th scope="col" className="font-medium px-4 py-2">
                  Vị trí hiện tại
                </th>
                <th scope="col" className="font-medium px-4 py-2">
                  Khách
                </th>
                <th scope="col" className="font-medium px-4 py-2 whitespace-nowrap">
                  Đi / đến
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={r.trip.id}
                  className="border-t border-[var(--border)] hover:bg-[var(--surface-sunken)] transition-colors"
                >
                  <td className="px-4 py-2.5 text-[13px] font-medium whitespace-nowrap">
                    {r.trip.vehicle_label ?? (
                      <span className="text-[var(--text-tertiary)] font-normal">
                        Chưa gán
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-[13px] whitespace-nowrap">
                    {r.driverName ?? (
                      <span className="text-[var(--text-tertiary)]">Chưa gán</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-[13px] whitespace-nowrap">
                    {r.direction ? DIRECTION[r.direction].short : "—"}
                  </td>
                  <td className="px-4 py-2.5">
                    <Badge tone={r.state.tone}>{r.state.label}</Badge>
                  </td>
                  <td className="px-4 py-2.5 text-[13px] tnum whitespace-nowrap">
                    {r.seats} chỗ
                  </td>
                  <td className="px-4 py-2.5 text-[13px] tnum whitespace-nowrap text-[var(--text-secondary)]">
                    {r.departsAt ? fmtTime(r.departsAt) : "—"}
                    {r.arrivesAt ? ` → ${fmtTime(r.arrivesAt)}` : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
