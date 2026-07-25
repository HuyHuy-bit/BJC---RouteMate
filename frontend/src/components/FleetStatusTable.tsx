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

// Loading and error states belong to the QueryState wrapper at the
// call site, so this component only ever renders real data.
export default function FleetStatusTable({ trips }: { trips: TripOut[] }) {
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

  return (
    <Card className="overflow-hidden">
      <div className="px-4 py-3 border-b border-line">
        <h2 className="text-base font-semibold">Tình trạng đội xe</h2>
        <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2">
          {PLACE_SUMMARY.map((s) => (
            <span
              key={s.place}
              className="inline-flex items-center gap-1.5 text-2xs text-faint"
            >
              {s.icon}
              {s.label}
              <span className="tnum font-semibold text-ink">
                {counts[s.place]}
              </span>
            </span>
          ))}
        </div>
      </div>

      {rows.length === 0 ? (
        <EmptyState
          compact
          icon={<Car size={16} aria-hidden="true" />}
          title="Chưa có chuyến nào đang hoạt động"
          description="Khi có chuyến được ghép, tình trạng từng xe sẽ hiện ở đây."
        />
      ) : (
        // Wide table scrolls inside its own container so the page body
        // never scrolls sideways on a narrow screen.
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse min-w-[640px]">
            <thead>
              <tr className="text-2xs text-faint">
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
                  className="border-t border-line hover:bg-sunken transition-colors"
                >
                  <td className="px-4 py-2.5 text-sm font-medium whitespace-nowrap">
                    {r.trip.vehicle_label ?? (
                      <span className="text-faint font-normal">
                        Chưa gán
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-sm whitespace-nowrap">
                    {r.driverName ?? (
                      <span className="text-faint">Chưa gán</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-sm whitespace-nowrap">
                    {r.direction ? DIRECTION[r.direction].short : "—"}
                  </td>
                  <td className="px-4 py-2.5">
                    <Badge tone={r.state.tone}>{r.state.label}</Badge>
                  </td>
                  <td className="px-4 py-2.5 text-sm tnum whitespace-nowrap">
                    {r.seats} chỗ
                  </td>
                  <td className="px-4 py-2.5 text-sm tnum whitespace-nowrap text-muted">
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
