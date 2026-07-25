import type {
  BookingStatus,
  BookingDirection,
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
  on_trip: { label: "Đang chạy", tone: "info" },
  maintenance: { label: "Bảo dưỡng", tone: "warning" },
  inactive: { label: "Ngừng hoạt động", tone: "neutral" },
};

export const TRIP_STATUS: Record<TripStatus, { label: string; tone: Tone }> = {
  forming: { label: "Đang gom khách", tone: "neutral" },
  sealed: { label: "Đã chốt, chờ xe", tone: "warning" },
  assigned: { label: "Sẵn sàng chạy", tone: "info" },
  in_progress: { label: "Đang chạy", tone: "warning" },
  completed: { label: "Hoàn thành", tone: "success" },
  cancelled: { label: "Đã huỷ", tone: "danger" },
  reassigning: { label: "Đang đổi xe", tone: "danger" },
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
export const NEXT_TRIP_ACTION: Partial<
  Record<TripStatus, { label: string; next: TripStatus }>
> = {
  sealed: { label: "Xác nhận xe", next: "assigned" },
  assigned: { label: "Bắt đầu chuyến", next: "in_progress" },
  in_progress: { label: "Hoàn thành chuyến", next: "completed" },
};

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
export type FleetPlace = "bac_giang" | "ha_noi" | "running" | "issue";

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
      return { place: origin, label: `Sắp khởi hành từ ${originName}`, tone: "info" };
    case "in_progress":
      return { place: "running", label: `Đang chạy → ${destName}`, tone: "warning" };
    case "completed":
      return { place: destination, label: `Đã đến ${destName}`, tone: "success" };
    case "reassigning":
      return { place: "issue", label: "Sự cố — chờ xe thay thế", tone: "danger" };
    case "cancelled":
      return { place: "issue", label: "Đã huỷ", tone: "danger" };
  }
}
