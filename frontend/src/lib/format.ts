import type { BookingStatus, BookingDirection, TripStatus } from "../types";

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
  cancelled: { label: "Đã huỷ", tone: "danger" },
};

export const TRIP_STATUS: Record<TripStatus, { label: string; tone: Tone }> = {
  forming: { label: "Đang gom khách", tone: "neutral" },
  confirmed: { label: "Sẵn sàng chạy", tone: "info" },
  in_progress: { label: "Đang chạy", tone: "warning" },
  completed: { label: "Hoàn thành", tone: "success" },
  cancelled: { label: "Đã huỷ", tone: "danger" },
};

export const DIRECTION: Record<BookingDirection, { label: string; short: string }> = {
  outbound: { label: "Bắc Giang → Hà Nội", short: "→ Hà Nội" },
  return: { label: "Hà Nội → Bắc Giang", short: "→ Bắc Giang" },
};

/** Next allowed forward transition, mirroring the backend state machine. */
export const NEXT_TRIP_ACTION: Partial<
  Record<TripStatus, { label: string; next: TripStatus }>
> = {
  confirmed: { label: "Bắt đầu chuyến", next: "in_progress" },
  in_progress: { label: "Hoàn thành chuyến", next: "completed" },
};
