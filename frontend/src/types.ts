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
  | "in_progress"
  | "completed"
  | "cancelled"
  | "reassigning";
export type VehicleStatus =
  | "available"
  | "on_trip"
  | "maintenance"
  | "inactive";

export interface UserOut {
  id: string;
  full_name: string;
  phone: string;
  role: UserRole;
  is_active: boolean;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface CustomerCreate {
  full_name: string;
  phone: string;
}

export interface CustomerOut {
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
  direction: BookingDirection;
  is_private: boolean;
  price_vnd: number;
  status: BookingStatus;
  trip_id: string | null;
  created_at: string;
}

export interface TripOut {
  id: string;
  status: TripStatus;
  driver_id: string | null;
  vehicle_label: string | null;
  is_private: boolean;
  bookings: BookingOut[];
  created_at: string;
  completed_at: string | null;
  cancelled_at: string | null;
}

export interface MatchingRunResult {
  trips_created: number;
  trips: TripOut[];
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
}

export interface VehicleCreate {
  plate_number: string;
  label?: string | null;
  seat_capacity: number;
  default_driver_id?: string | null;
}

export interface VehicleUpdate {
  label?: string | null;
  status?: VehicleStatus;
  default_driver_id?: string | null;
}

export interface AttentionItem {
  kind: "escalated" | "no_vehicle";
  trip_id: string;
  direction: BookingDirection;
  passenger_count: number;
  minutes_overdue: number;
  reason: string;
  options: string[] | null;
  bookings: BookingOut[];
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
