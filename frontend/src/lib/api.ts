import { apiClient } from "./apiClient";
import type {
  AttentionItem,
  BookingCreate,
  BookingOut,
  BookingStatus,
  GeocodeResponse,
  MatchingRunResult,
  MergeTripsResult,
  NotificationOut,
  TokenPair,
  TripOut,
  TripStatus,
  UserOut,
  UserRole,
  UserUpdate,
  VehicleCreate,
  VehicleOut,
  VehicleUpdate,
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
    update: (id: string, payload: UserUpdate) =>
      apiClient.patch<UserOut>(`/users/${id}`, payload).then((r) => r.data),
    delete: (id: string) => apiClient.delete(`/users/${id}`),
  },
  customers: {
    delete: (id: string) => apiClient.delete(`/customers/${id}`),
  },
  vehicles: {
    list: () => apiClient.get<VehicleOut[]>("/vehicles").then((r) => r.data),
    create: (payload: VehicleCreate) =>
      apiClient.post<VehicleOut>("/vehicles", payload).then((r) => r.data),
    update: (id: string, payload: VehicleUpdate) =>
      apiClient.patch<VehicleOut>(`/vehicles/${id}`, payload).then((r) => r.data),
    delete: (id: string) => apiClient.delete(`/vehicles/${id}`),
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
    noShow: (id: string) =>
      apiClient.post<BookingOut>(`/bookings/${id}/no-show`).then((r) => r.data),
    unassign: (id: string) =>
      apiClient.post<BookingOut>(`/bookings/${id}/unassign`).then((r) => r.data),
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
    history: () =>
      apiClient.get<TripOut[]>("/dispatch/history").then((r) => r.data),
    myHistory: () =>
      apiClient.get<TripOut[]>("/dispatch/my-history").then((r) => r.data),
    attention: () =>
      apiClient.get<AttentionItem[]>("/dispatch/attention").then((r) => r.data),
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
    sealTrip: (tripId: string) =>
      apiClient.post<TripOut>(`/dispatch/trips/${tripId}/seal`).then((r) => r.data),
    mergeTrips: (sourceId: string, targetId: string) =>
      apiClient
        .post<MergeTripsResult>(`/dispatch/trips/${sourceId}/merge/${targetId}`)
        .then((r) => r.data),
  },
  notifications: {
    list: () =>
      apiClient.get<NotificationOut[]>("/notifications").then((r) => r.data),
  },
  geocode: (address: string) =>
    apiClient
      .get<GeocodeResponse>("/geocode", { params: { address } })
      .then((r) => r.data),
};
