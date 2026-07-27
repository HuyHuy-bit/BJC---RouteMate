export type UserRole = "admin" | "dispatcher" | "driver";
export type BookingStatus =
  | "queued"
  | "matched"
  | "waiting"
  | "locked"
  | "onboard"
  | "completed"
  | "no_show"
  | "cancelled";
export type BookingDirection = "outbound" | "return";
export type TripStatus =
  | "forming"
  | "sealed"
  | "assigned"
  | "driver_accepted"
  | "in_progress"
  | "completion_requested"
  | "completed"
  | "cancelled"
  | "reassigning";
export type VehicleStatus =
  | "available"
  | "assigned"
  | "on_trip"
  /** Deadheading back to base, empty. Not dispatchable. */
  | "returning"
  | "maintenance"
  | "offline";

export interface UserOut {
  id: string;
  full_name: string;
  phone: string;
  role: UserRole;
  is_active: boolean;
}

export interface UserUpdate {
  is_active?: boolean;
  role?: UserRole;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

interface CustomerCreate {
  full_name: string;
  phone: string;
}

interface CustomerOut {
  id: string;
  full_name: string;
  phone: string;
  created_at: string;
}

export interface BookingCreate {
  customer: CustomerCreate;
  pickup_address: string;
  pickup_lat: number;
  pickup_lng: number;
  dropoff_address: string;
  dropoff_lat: number;
  dropoff_lng: number;
  requested_pickup_at: string;
  is_private: boolean;
  seats?: number;
}

type PaymentMethod = "cash" | "bank_transfer" | "other";
export type PaymentStatus = "pending" | "collected" | "disputed" | "waived";

export interface PaymentOut {
  id: string;
  booking_id: string;
  method: PaymentMethod;
  expected_amount_vnd: number;
  collected_amount_vnd: number | null;
  status: PaymentStatus;
  collected_by_user_id: string | null;
  collected_at: string | null;
  notes: string | null;
}

export interface PaymentCollect {
  method: PaymentMethod;
  collected_amount_vnd: number;
  notes?: string | null;
}

export interface BookingOut {
  id: string;
  customer: CustomerOut;
  pickup_address: string;
  pickup_lat: number;
  pickup_lng: number;
  dropoff_address: string;
  dropoff_lat: number;
  dropoff_lng: number;
  requested_pickup_at: string;
  estimated_pickup_at: string | null;
  estimated_dropoff_at: string | null;
  direction: BookingDirection;
  is_private: boolean;
  seats: number;
  status: BookingStatus;
  trip_id: string | null;
  created_at: string;
  /**
   * Money. Null for dispatchers — always, and enforced server-side, not
   * by hiding it here. Admins see it everywhere; drivers see it on
   * their own trips because they collect the cash at the door.
   */
  price_vnd: number | null;
  payment: PaymentOut | null;
}

export interface TripOut {
  id: string;
  status: TripStatus;
  driver_id: string | null;
  vehicle_id: string | null;
  vehicle_label: string | null;
  is_private: boolean;
  bookings: BookingOut[];
  created_at: string;
  completed_at: string | null;
  cancelled_at: string | null;
  driver_accepted_at: string | null;
  completion_requested_at: string | null;
  finalized_at: string | null;
  finalized_by_user_id: string | null;
  /**
   * Which transitions the CURRENT user may make on this trip, straight
   * from the backend's transition table. Render actions from this
   * rather than from a local status->buttons map: the old map is how
   * the dispatch board came to show "Bắt đầu chuyến" and "Hoàn thành
   * chuyến" buttons that only a driver is allowed to press.
   */
  available_actions: TripStatus[];
}

export interface MatchingRunResult {
  trips_created: number;
  trips: TripOut[];
}

/**
 * Admin-only money view. Deliberately not part of TripOut or any
 * dispatcher-facing payload — see requirements §3.
 */
export interface DailyRevenuePoint {
  /** Local calendar day, "YYYY-MM-DD". */
  day: string;
  revenue_vnd: number;
  trips: number;
}

export interface AdminDashboard {
  generated_at: string;
  revenue_today_vnd: number;
  revenue_week_vnd: number;
  revenue_month_vnd: number;
  revenue_total_vnd: number;
  daily: DailyRevenuePoint[];
  expected_vnd: number;
  collected_vnd: number;
  outstanding_vnd: number;
  disputed_vnd: number;
  waived_vnd: number;
  trips_finalized: number;
  passengers_carried: number;
  seats_carried: number;
  trips_cancelled: number;
  avg_revenue_per_trip_vnd: number;
  avg_seats_per_trip: number;
}

export interface GeocodeResult {
  formatted_address: string;
  lat: number;
  lng: number;
  place_id: string;
}

export interface GeocodeResponse {
  query: string;
  results: GeocodeResult[];
}

export interface VehicleOut {
  id: string;
  plate_number: string;
  label: string | null;
  seat_capacity: number;
  status: VehicleStatus;
  default_driver_id: string | null;
  home_corridor_id: string | null;
  last_location_at: string | null;
  last_location_lat: number | null;
  last_location_lng: number | null;
  /** Non-null exactly when a return to base is outstanding. */
  return_requested_at: string | null;
}

export interface VehicleLocationPing {
  lat: number;
  lng: number;
}

export interface VehicleCreate {
  plate_number: string;
  label?: string | null;
  seat_capacity: number;
  default_driver_id?: string | null;
  home_corridor_id?: string | null;
}

export interface VehicleUpdate {
  label?: string | null;
  status?: VehicleStatus;
  default_driver_id?: string | null;
  home_corridor_id?: string | null;
  last_location_lat?: number | null;
  last_location_lng?: number | null;
}

export type TripReportIssueReason =
  | "breakdown"
  | "accident"
  | "driver_unavailable"
  | "other";

export interface TripReportIssue {
  reason: TripReportIssueReason;
  notes?: string | null;
}

export interface AttentionItem {
  kind: "escalated" | "no_vehicle" | "vehicle_down" | "idle_away";
  reason: string;
  minutes_overdue: number;
  /** Null for `idle_away`, which is about a car with no trip at all. */
  trip_id: string | null;
  direction: BookingDirection | null;
  passenger_count: number;
  options: string[] | null;
  bookings: BookingOut[];
  /** Set for `idle_away`, where the car is the subject. */
  vehicle_id: string | null;
  vehicle_label: string | null;
}

export interface MergeTripsResult {
  target: TripOut;
}

export interface NotificationOut {
  id: string;
  booking_id: string;
  customer_name: string;
  customer_phone: string;
  event: string;
  message: string;
  status: string;
  created_at: string;
}
