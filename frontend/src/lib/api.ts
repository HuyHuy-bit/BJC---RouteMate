import { apiClient } from "./apiClient";
import type {
  BookingCreate,
  BookingOut,
  BookingStatus,
  GeocodeResponse,
  MatchingRunResult,
  TokenPair,
  TripOut,
  TripStatus,
  UserOut,
  UserRole,
} from "../types";

export const api = {
  auth: {
    login: (phone: string, password: string) =>
      apiClient
        .post<TokenPair>("/auth/login", { phone, password })
        .then((r) => r.data),
    me: () => apiClient.get<UserOut>("/auth/me").then((r) => r.data),
    register: (payload: {
      full_name: string;
      phone: string;
      password: string;
      role: UserRole;
    }) => apiClient.post<UserOut>("/auth/register", payload).then((r) => r.data),
  },
  users: {
    list: (role?: UserRole) =>
      apiClient
        .get<UserOut[]>("/users", { params: role ? { role } : undefined })
        .then((r) => r.data),
  },
  customers: {
    delete: (id: string) => apiClient.delete(`/customers/${id}`),
  },
  bookings: {
    list: (statusFilter?: BookingStatus) =>
      apiClient
        .get<BookingOut[]>("/bookings", {
          params: statusFilter ? { status_filter: statusFilter } : undefined,
        })
        .then((r) => r.data),
    create: (payload: BookingCreate) =>
      apiClient.post<BookingOut>("/bookings", payload).then((r) => r.data),
    cancel: (id: string) => apiClient.delete(`/bookings/${id}`),
  },
  dispatch: {
    run: (radiusMeters = 3000) =>
      apiClient
        .post<MatchingRunResult>("/dispatch/run", null, {
          params: { radius_meters: radiusMeters },
        })
        .then((r) => r.data),
    trips: () =>
      apiClient.get<TripOut[]>("/dispatch/trips").then((r) => r.data),
    myTrips: () =>
      apiClient.get<TripOut[]>("/dispatch/my-trips").then((r) => r.data),
    assignDriver: (tripId: string, driverId: string) =>
      apiClient
        .patch<TripOut>(`/dispatch/trips/${tripId}/driver`, {
          driver_id: driverId,
        })
        .then((r) => r.data),
    updateStatus: (tripId: string, status: TripStatus) =>
      apiClient
        .patch<TripOut>(`/dispatch/trips/${tripId}/status`, { status })
        .then((r) => r.data),
  },
  geocode: (address: string) =>
    apiClient
      .get<GeocodeResponse>("/geocode", { params: { address } })
      .then((r) => r.data),
};
