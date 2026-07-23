export type UserRole = "admin" | "dispatcher" | "driver";
export type BookingStatus = "queued" | "matched" | "waiting" | "cancelled";
export type BookingDirection = "outbound" | "return";
export type TripStatus =
  | "forming"
  | "confirmed"
  | "in_progress"
  | "completed"
  | "cancelled";

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
