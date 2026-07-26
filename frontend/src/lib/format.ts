import type {
  BookingOut,
  BookingStatus,
  BookingDirection,
  PaymentStatus,
  TripOut,
  TripStatus,
  VehicleStatus,
} from "../types";

export function fmtVnd(n: number): string {
  return n.toLocaleString("vi-VN") + "đ";
}

export function fmtDateTime(iso: string): string {
  return new Date(iso).toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function fmtDayLabel(iso: string): string {
  const d = new Date(iso);
  const today = new Date();
  const tomorrow = new Date(today);
  tomorrow.setDate(today.getDate() + 1);

  const sameDay = (a: Date, b: Date) =>
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate();

  if (sameDay(d, today)) return "Hôm nay";
  if (sameDay(d, tomorrow)) return "Ngày mai";
  return d.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" });
}

/**
 * When this trip leaves — the earliest pickup across its bookings,
 * preferring the solver's computed ETA over the customer's request.
 */
export function tripDeparture(trip: TripOut): string | undefined {
  return trip.bookings
    .map((b) => b.estimated_pickup_at ?? b.requested_pickup_at)
    .filter(Boolean)
    .sort()[0];
}

/**
 * A stable, speakable name for a trip.
 *
 * This replaces `Xe ${idx + 1}`, which numbered cars by their position
 * in whatever array the last refetch happened to produce. "Xe 3" meant
 * a different vehicle after every poll — and it is the label a
 * dispatcher reads down the phone to a driver.
 *
 * Once a real vehicle is attached, its plate/label IS the identity, and
 * it matches what FleetStatusTable shows for the same car. Before then
 * there is no car to name, so the trip is identified by the two things
 * that actually distinguish it and don't move: where it's going and
 * when it leaves.
 */
export function tripIdentity(trip: TripOut): string {
  if (trip.vehicle_label) return trip.vehicle_label;

  const direction = trip.bookings[0]?.direction;
  const departs = tripDeparture(trip);
  const route = direction ? DIRECTION[direction].short : "Chuyến";
  return departs ? `${route} · ${fmtTime(departs)}` : route;
}

/** Seats taken, not bookings — one booking can be a family of four. */
export function seatsTaken(bookings: BookingOut[]): number {
  return bookings.reduce((n, b) => n + (b.seats ?? 1), 0);
}

type Tone = "neutral" | "success" | "warning" | "danger" | "info";

export const BOOKING_STATUS: Record<
  BookingStatus,
  { label: string; tone: Tone }
> = {
  queued: { label: "Chờ ghép", tone: "neutral" },
  matched: { label: "Đã ghép xe", tone: "success" },
  waiting: { label: "Chưa đủ khách", tone: "warning" },
  locked: { label: "Đã chốt xe", tone: "info" },
  onboard: { label: "Đang trên xe", tone: "info" },
  completed: { label: "Hoàn thành", tone: "success" },
  no_show: { label: "Khách không đến", tone: "danger" },
  cancelled: { label: "Đã huỷ", tone: "danger" },
};

export const VEHICLE_STATUS: Record<
  VehicleStatus,
  { label: string; tone: Tone }
> = {
  available: { label: "Sẵn sàng", tone: "success" },
  assigned: { label: "Đã phân chuyến", tone: "info" },
  on_trip: { label: "Đang chạy", tone: "info" },
  returning: { label: "Đang về Bắc Giang", tone: "warning" },
  maintenance: { label: "Bảo dưỡng", tone: "warning" },
  offline: { label: "Ngừng hoạt động", tone: "neutral" },
};

export const TRIP_STATUS: Record<TripStatus, { label: string; tone: Tone }> = {
  forming: { label: "Đang gom khách", tone: "neutral" },
  sealed: { label: "Đã chốt, chờ xe", tone: "warning" },
  assigned: { label: "Chờ tài xế nhận", tone: "info" },
  driver_accepted: { label: "Tài xế đã nhận", tone: "info" },
  in_progress: { label: "Đang chạy", tone: "warning" },
  completion_requested: { label: "Chờ duyệt hoàn thành", tone: "warning" },
  completed: { label: "Hoàn thành", tone: "success" },
  cancelled: { label: "Đã huỷ", tone: "danger" },
  reassigning: { label: "Đang đổi xe", tone: "danger" },
};

export const PAYMENT_STATUS: Record<
  PaymentStatus,
  { label: string; tone: Tone }
> = {
  pending: { label: "Chưa thu", tone: "warning" },
  collected: { label: "Đã thu tiền", tone: "success" },
  disputed: { label: "Thiếu tiền", tone: "danger" },
  waived: { label: "Đã miễn", tone: "neutral" },
};

export const ROLE_LABEL: Record<string, string> = {
  admin: "Quản trị",
  dispatcher: "Điều phối",
  driver: "Tài xế",
};

export const DIRECTION: Record<BookingDirection, { label: string; short: string }> = {
  outbound: { label: "Bắc Giang → Hà Nội", short: "→ Hà Nội" },
  return: { label: "Hà Nội → Bắc Giang", short: "→ Bắc Giang" },
};

/** Next allowed forward transition, mirroring the backend state machine. */
/**
 * What each workflow action is called, and which endpoint performs it.
 *
 * Keyed by the TARGET status rather than the current one, because the
 * backend hands us `available_actions` as a list of reachable statuses
 * — so a caller looks up what it was told it may do, instead of
 * re-deriving it from the current status and hoping the two agree.
 *
 * This replaces a single NEXT_TRIP_ACTION map shared by every role,
 * which is precisely why the dispatch board rendered "Bắt đầu chuyến"
 * and "Hoàn thành chuyến" — driver-only actions — to dispatchers.
 */
export const TRIP_ACTION: Partial<
  Record<TripStatus, { label: string; path: string; tone?: "primary" | "danger" }>
> = {
  driver_accepted: { label: "Nhận chuyến", path: "accept", tone: "primary" },
  in_progress: { label: "Bắt đầu chuyến", path: "start", tone: "primary" },
  completion_requested: {
    label: "Hoàn thành chuyến",
    path: "request-completion",
    tone: "primary",
  },
  completed: { label: "Duyệt hoàn thành", path: "finalize", tone: "primary" },
  reassigning: { label: "Không nhận chuyến", path: "reject", tone: "danger" },
};

/**
 * `completion_requested -> in_progress` is the dispatcher sending a
 * completion claim back, but `in_progress` already maps to the
 * driver's "Bắt đầu chuyến" above. The action depends on where you
 * are, not only where you're going, so this one case is looked up by
 * (from, to) instead.
 */
export function tripActionFor(
  from: TripStatus,
  to: TripStatus
): { label: string; path: string; tone?: "primary" | "danger" } | undefined {
  if (from === "completion_requested" && to === "in_progress") {
    return { label: "Trả lại tài xế", path: "reject-completion", tone: "danger" };
  }
  return TRIP_ACTION[to];
}

/**
 * Where a car physically is right now, derived from its trip state.
 *
 * There's no live GPS feed driving this — it reads the two things that
 * genuinely determine a car's whereabouts operationally: which way it's
 * going, and how far through the trip lifecycle it is. A trip that
 * hasn't departed is still at its origin hub; one in progress is on the
 * road between hubs; a finished one is at its destination. That's
 * exactly the "at Bắc Giang / at Hà Nội / running" picture a dispatcher
 * needs to see at a glance.
 *
 * `place` is the coarse bucket used for the summary counts; `label` is
 * what the operator reads.
 */
export type FleetPlace =
  | "bac_giang"
  | "ha_noi"
  | "running"
  | "issue"
  | "off_duty";

/** Rough hub coordinates, used only to bucket a parked car to one end
 *  of the corridor for the fleet summary. Not a routing input. */
const HUBS: { place: FleetPlace; lat: number; lng: number }[] = [
  { place: "bac_giang", lat: 21.2731, lng: 106.1946 },
  { place: "ha_noi", lat: 21.0278, lng: 105.8342 },
];

/**
 * Which end of the corridor a car is parked at, from its last confirmed
 * position. Nearest hub wins; there are only two, and they are ~50km
 * apart, so plain squared distance is more than precise enough and
 * avoids pulling in a geo library for a badge label.
 */
export function placeFromLatLng(
  lat: number | null,
  lng: number | null
): FleetPlace | null {
  if (lat == null || lng == null) return null;
  let best: FleetPlace | null = null;
  let bestD = Infinity;
  for (const h of HUBS) {
    const d = (h.lat - lat) ** 2 + (h.lng - lng) ** 2;
    if (d < bestD) {
      bestD = d;
      best = h.place;
    }
  }
  return best;
}

export function tripLocationState(
  status: TripStatus,
  direction: BookingDirection | undefined
): { place: FleetPlace; label: string; tone: Tone } {
  // Outbound leaves Bắc Giang for Hà Nội; return is the reverse.
  const origin: FleetPlace = direction === "return" ? "ha_noi" : "bac_giang";
  const destination: FleetPlace = direction === "return" ? "bac_giang" : "ha_noi";
  const originName = origin === "ha_noi" ? "Hà Nội" : "Bắc Giang";
  const destName = destination === "ha_noi" ? "Hà Nội" : "Bắc Giang";

  switch (status) {
    case "forming":
      return { place: origin, label: `Gom khách tại ${originName}`, tone: "neutral" };
    case "sealed":
      return { place: origin, label: `Chờ xe tại ${originName}`, tone: "warning" };
    case "assigned":
      return { place: origin, label: `Chờ tài xế nhận tại ${originName}`, tone: "info" };
    case "driver_accepted":
      return { place: origin, label: `Sắp khởi hành từ ${originName}`, tone: "info" };
    case "in_progress":
      return { place: "running", label: `Đang chạy → ${destName}`, tone: "warning" };
    // The car has physically arrived; only the paperwork is outstanding,
    // so it belongs at the destination rather than still "running".
    case "completion_requested":
      return { place: destination, label: `Đã đến ${destName}, chờ duyệt`, tone: "warning" };
    case "completed":
      return { place: destination, label: `Đã đến ${destName}`, tone: "success" };
    case "reassigning":
      return { place: "issue", label: "Sự cố — chờ xe thay thế", tone: "danger" };
    case "cancelled":
      return { place: "issue", label: "Đã huỷ", tone: "danger" };
  }
}
