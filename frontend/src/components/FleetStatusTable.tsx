import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Car, MapPin, Navigation, TriangleAlert, Wrench } from "lucide-react";
import { api } from "../lib/api";
import type { TripOut, VehicleOut } from "../types";
import {
  DIRECTION,
  VEHICLE_STATUS,
  fmtTime,
  placeFromLatLng,
  tripLocationState,
  type FleetPlace,
} from "../lib/format";
import Badge from "./ui/Badge";
import Card from "./ui/Card";
import DataTable, { type Column } from "./ui/DataTable";
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
  {
    place: "off_duty",
    label: "Nghỉ / bảo dưỡng",
    icon: <Wrench size={13} aria-hidden="true" />,
  },
];

/**
 * Every car in the fleet, always.
 *
 * This table used to be built from the list of ACTIVE TRIPS, which
 * meant a car existed on the board only while it was mid-trip. The
 * moment its trip finished, its row vanished — reported as "Car 1
 * disappeared from the available vehicle pool" — even though the
 * vehicle was perfectly fine, parked at its destination, and eligible
 * for the next dispatch.
 *
 * It is now built from the VEHICLE ROSTER, with the active trip (if
 * any) joined on. An idle car is a row saying where it is and that
 * it's free, which is exactly what a dispatcher needs in order to send
 * it somewhere.
 */
export default function FleetStatusTable({ trips }: { trips: TripOut[] }) {
  const vehiclesQuery = useQuery({
    queryKey: ["vehicles"],
    queryFn: () => api.vehicles.list(),
  });
  // Driver names aren't on TripOut (only driver_id), so resolve them
  // from the roster the dispatcher already loads elsewhere.
  const driversQuery = useQuery({
    queryKey: ["drivers"],
    queryFn: () => api.users.list("driver"),
  });

  const rows = useMemo(() => {
    const vehicles: VehicleOut[] = vehiclesQuery.data ?? [];
    // One live trip per car — a vehicle committed to two active trips
    // at once is exactly what the FOR UPDATE lock now prevents, but
    // take the first either way rather than rendering a duplicate row.
    const tripByVehicle = new Map<string, TripOut>();
    for (const t of trips) {
      if (t.vehicle_id && !tripByVehicle.has(t.vehicle_id)) {
        tripByVehicle.set(t.vehicle_id, t);
      }
    }

    return vehicles.map((v) => {
      const trip = tripByVehicle.get(v.id) ?? null;
      const direction = trip?.bookings[0]?.direction;

      // On a trip: derive the picture from where the trip has got to.
      // Otherwise fall back to the car's own last confirmed position,
      // which finalization keeps up to date.
      const state = trip
        ? tripLocationState(trip.status, direction)
        : idleState(v);

      const pickups = (trip?.bookings ?? [])
        .map((b) => b.estimated_pickup_at ?? b.requested_pickup_at)
        .filter(Boolean)
        .sort();
      const dropoffs = (trip?.bookings ?? [])
        .map((b) => b.estimated_dropoff_at)
        .filter((x): x is string => Boolean(x))
        .sort();

      return {
        vehicle: v,
        trip,
        direction,
        state,
        seats: (trip?.bookings ?? []).reduce((n, b) => n + (b.seats ?? 1), 0),
        departsAt: pickups[0],
        arrivesAt: dropoffs[dropoffs.length - 1],
        driverName:
          driversQuery.data?.find((d) => d.id === trip?.driver_id)?.full_name ??
          null,
      };
    });
  }, [trips, vehiclesQuery.data, driversQuery.data]);

  // The plate leads, not the nickname. "Xe 1" is what the office calls
  // it; the plate is what a dispatcher reads out on the phone, matches
  // against paperwork, and can identify a car by when two of them are
  // both called "Xe". The label stays underneath so this still
  // cross-references the trip cards, which are labelled.
  const columns: Column<(typeof rows)[number]>[] = [
    {
      header: "Xe",
      className: "whitespace-nowrap",
      cell: (r) => (
        <>
          <span className="block text-sm font-medium tnum">
            {r.vehicle.plate_number}
          </span>
          {r.vehicle.label && (
            <span className="block text-2xs text-faint">{r.vehicle.label}</span>
          )}
        </>
      ),
    },
    {
      header: "Tài xế",
      className: "whitespace-nowrap",
      cell: (r) => r.driverName ?? <span className="text-faint">—</span>,
    },
    {
      header: "Tuyến",
      className: "whitespace-nowrap",
      cell: (r) => (r.direction ? DIRECTION[r.direction].short : "—"),
    },
    {
      header: "Vị trí hiện tại",
      cell: (r) => <Badge tone={r.state.tone}>{r.state.label}</Badge>,
    },
    {
      header: "Khách",
      className: "tnum whitespace-nowrap",
      cell: (r) => (r.trip ? `${r.seats} chỗ` : "—"),
    },
    {
      header: "Đi / đến",
      className: "tnum whitespace-nowrap text-muted",
      cell: (r) =>
        `${r.departsAt ? fmtTime(r.departsAt) : "—"}${
          r.arrivesAt ? ` → ${fmtTime(r.arrivesAt)}` : ""
        }`,
    },
  ];

  const counts = useMemo(() => {
    const c: Record<FleetPlace, number> = {
      bac_giang: 0,
      ha_noi: 0,
      running: 0,
      issue: 0,
      off_duty: 0,
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
          title="Chưa có xe nào trong đội"
          description="Thêm xe ở trang Đội xe để bắt đầu điều phối."
        />
      ) : (
        <DataTable
          columns={columns}
          rows={rows}
          rowKey={(r) => r.vehicle.id}
          caption="Trạng thái từng xe trong đội"
        />
      )}
    </Card>
  );
}

/**
 * A car with no active trip. Maintenance and offline are about the car
 * itself and outrank where it happens to be parked; anything else is
 * free, and the useful fact is which end of the corridor it's at.
 */
function idleState(v: VehicleOut) {
  if (v.status === "maintenance" || v.status === "offline") {
    return {
      place: "off_duty" as FleetPlace,
      label: VEHICLE_STATUS[v.status].label,
      tone: VEHICLE_STATUS[v.status].tone,
    };
  }

  const place = placeFromLatLng(v.last_location_lat, v.last_location_lng);
  const where =
    place === "ha_noi" ? "Hà Nội" : place === "bac_giang" ? "Bắc Giang" : null;

  return {
    place: place ?? ("issue" as FleetPlace),
    label: where ? `Sẵn sàng tại ${where}` : "Sẵn sàng — chưa rõ vị trí",
    tone: where ? ("success" as const) : ("neutral" as const),
  };
}
