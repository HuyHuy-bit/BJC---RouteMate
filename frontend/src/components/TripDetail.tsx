import {
  ArrowDownToLine,
  ArrowUpFromLine,
  Car,
  CircleUser,
  Phone,
  Users,
} from "lucide-react";
import type { TripOut, UserOut, VehicleOut } from "../types";
import { useAuth } from "../context/AuthContext";
import {
  DIRECTION,
  PAYMENT_STATUS,
  TRIP_STATUS,
  fmtDateTime,
  fmtTime,
  fmtVnd,
  seatsTaken,
} from "../lib/format";
import Badge from "./ui/Badge";

/**
 * Everything about one finished ride: which car, which driver, and who
 * was on board.
 *
 * The history table answers "what happened"; this answers the question
 * that actually prompts someone to open it — a customer rings up about
 * a ride last Tuesday and staff need the driver's number and the
 * addresses, fast.
 *
 * Driver and vehicle are resolved from the current rosters, because
 * TripOut carries only their ids. Both fall back gracefully: a driver
 * who has since left or a car that has been deleted still shows
 * *something* rather than a blank, since the trip record outlives them.
 */
export default function TripDetail({
  trip,
  drivers,
  vehicles,
  rostersAvailable,
  rostersLoading = false,
  selfDriver,
}: {
  trip: TripOut;
  drivers: UserOut[];
  vehicles: VehicleOut[];
  /**
   * Whether the driver/vehicle rosters were actually retrieved.
   *
   * GET /users and GET /vehicles are both require_role(admin,
   * dispatcher), so a driver reading their own history gets 403 on
   * both. Without this flag an empty roster is indistinguishable from
   * "this driver was deleted", and the panel would state the latter as
   * fact. When it's false the panel reports only what the trip record
   * itself proves.
   */
  rostersAvailable: boolean;
  /** Rosters are still in flight — distinct from unavailable. */
  rostersLoading?: boolean;
  /** The signed-in driver, when they are viewing their own history. */
  selfDriver?: { id: string; full_name: string; phone: string } | null;
}) {
  const status = TRIP_STATUS[trip.status];
  const direction = trip.bookings[0]?.direction;
  // A driver viewing their own history drove it themselves, so their
  // own account answers the question without needing the roster.
  const rosterDriver = drivers.find((d) => d.id === trip.driver_id);
  const driver =
    rosterDriver ??
    (selfDriver && selfDriver.id === trip.driver_id ? selfDriver : undefined);
  const vehicle = vehicles.find((v) => v.id === trip.vehicle_id);
  // Admin-only. Dispatchers now receive no money at all — not the
  // trip total and not the individual fares below, which arrive null
  // from the server rather than being hidden here.
  const { user } = useAuth();
  // `?? 0` rather than a non-null assertion: this block only renders
  // for admins, who always receive fares, but the sum must not turn
  // into NaN if it is ever reached with a stripped payload.
  const revenue = trip.bookings.reduce((s, b) => s + (b.price_vnd ?? 0), 0);
  const finishedAt = trip.completed_at ?? trip.cancelled_at;

  return (
    <div className="space-y-5">
      <section>
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-lg font-semibold text-ink">
              {direction ? DIRECTION[direction].label : "Chuyến xe"}
            </h3>
            <p className="text-xs text-faint mt-0.5 tnum">
              {finishedAt ? fmtDateTime(finishedAt) : "Chưa có thời gian kết thúc"}
            </p>
          </div>
          <Badge tone={status.tone}>{status.label}</Badge>
        </div>

        <dl className="grid grid-cols-2 gap-x-4 gap-y-3 mt-4">
          <Fact label="Số khách">
            <span className="flex items-center gap-1.5">
              <Users size={13} aria-hidden="true" className="text-faint" />
              {trip.is_private
                ? "Bao xe riêng"
                : `${trip.bookings.length} khách · ${seatsTaken(trip.bookings)} chỗ`}
            </span>
          </Fact>
          {user?.role === "admin" && (
            <Fact label="Doanh thu">
              <span className="tnum font-semibold">{fmtVnd(revenue)}</span>
            </Fact>
          )}
        </dl>
      </section>

      {/* --- Car --- */}
      <section className="border-t border-line pt-4">
        <SectionTitle icon={<Car size={13} aria-hidden="true" />}>Xe</SectionTitle>
        {vehicle ? (
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
            <Fact label="Biển số">
              <span className="tnum font-medium">{vehicle.plate_number}</span>
            </Fact>
            <Fact label="Tên gọi">{vehicle.label ?? "Chưa đặt tên"}</Fact>
            <Fact label="Số chỗ">
              <span className="tnum">{vehicle.seat_capacity}</span>
            </Fact>
          </dl>
        ) : !trip.vehicle_id ? (
          <p className="text-base text-faint">Chuyến này chưa được gán xe</p>
        ) : rostersLoading ? (
          <div className="skeleton h-5 w-40" aria-hidden="true" />
        ) : (
          <p className="text-base text-muted">
            <span className="font-medium">{trip.vehicle_label ?? "Xe"}</span>
            {/* Only claim the car was removed when the roster was
                actually consulted. */}
            {rostersAvailable && (
              <span className="text-faint"> — xe này không còn trong đội xe</span>
            )}
          </p>
        )}
      </section>

      {/* --- Driver --- */}
      <section className="border-t border-line pt-4">
        <SectionTitle icon={<CircleUser size={13} aria-hidden="true" />}>
          Tài xế
        </SectionTitle>
        {driver ? (
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="text-base font-medium truncate">{driver.full_name}</p>
              {rosterDriver && !rosterDriver.is_active && (
                <span className="text-2xs text-faint">Tài khoản đã bị khoá</span>
              )}
            </div>
            <CallLink phone={driver.phone} name={driver.full_name} />
          </div>
        ) : !trip.driver_id ? (
          <p className="text-base text-faint">
            Chuyến này chưa được giao cho tài xế
          </p>
        ) : rostersLoading ? (
          <div className="skeleton h-5 w-40" aria-hidden="true" />
        ) : rostersAvailable ? (
          <p className="text-base text-faint">Tài xế không còn trong hệ thống</p>
        ) : (
          // Assigned to someone we can't name — say exactly that rather
          // than inventing an explanation for the missing name.
          <p className="text-base text-faint">
            Không xem được thông tin tài xế của chuyến này
          </p>
        )}
      </section>

      {/* --- Customers --- */}
      <section className="border-t border-line pt-4">
        <SectionTitle icon={<Users size={13} aria-hidden="true" />}>
          Khách hàng
          <span className="tnum font-normal text-faint ml-1">
            {trip.bookings.length}
          </span>
        </SectionTitle>

        <ol className="space-y-3">
          {trip.bookings.map((b, i) => (
            <li
              key={b.id}
              className="rounded-md border border-line bg-sunken/50 p-3"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-2 min-w-0">
                  <span
                    className="w-5 h-5 rounded-full bg-surface border border-line text-2xs font-semibold flex items-center justify-center shrink-0 mt-0.5 tnum"
                    aria-hidden="true"
                  >
                    {i + 1}
                  </span>
                  <div className="min-w-0">
                    <p className="text-base font-medium truncate">
                      {b.customer.full_name}
                    </p>
                    <p className="text-2xs text-faint tnum">
                      {b.seats} chỗ
                      {b.price_vnd !== null && ` · ${fmtVnd(b.price_vnd)}`}
                    </p>
                  </div>
                </div>
                <CallLink phone={b.customer.phone} name={b.customer.full_name} />
              </div>

              <p className="text-xs text-muted mt-2.5 flex items-start gap-1.5">
                <ArrowUpFromLine
                  size={12}
                  className="mt-0.5 shrink-0 text-cobalt"
                  aria-hidden="true"
                />
                <span className="leading-snug">{b.pickup_address}</span>
              </p>
              <p className="text-xs text-muted mt-1 flex items-start gap-1.5">
                <ArrowDownToLine
                  size={12}
                  className="mt-0.5 shrink-0 text-brand-text"
                  aria-hidden="true"
                />
                <span className="leading-snug">{b.dropoff_address}</span>
              </p>

              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-2.5">
                <span className="text-2xs text-faint tnum">
                  Đón {fmtTime(b.estimated_pickup_at ?? b.requested_pickup_at)}
                  {b.estimated_dropoff_at &&
                    ` → trả ${fmtTime(b.estimated_dropoff_at)}`}
                </span>
                {b.payment && (
                  <Badge tone={PAYMENT_STATUS[b.payment.status].tone}>
                    {PAYMENT_STATUS[b.payment.status].label}
                    {b.payment.status === "collected" &&
                      b.payment.collected_amount_vnd !== null &&
                      ` · ${fmtVnd(b.payment.collected_amount_vnd)}`}
                  </Badge>
                )}
              </div>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}

function SectionTitle({
  icon,
  children,
}: {
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <h4 className="flex items-center gap-1.5 text-2xs font-medium uppercase tracking-wide text-faint mb-2.5">
      <span aria-hidden="true">{icon}</span>
      {children}
    </h4>
  );
}

function Fact({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <dt className="text-2xs text-faint">{label}</dt>
      <dd className="text-base text-ink mt-0.5">{children}</dd>
    </div>
  );
}

/** Tap-to-call: resolving a query about a past ride means phoning someone. */
function CallLink({ phone, name }: { phone: string; name: string }) {
  return (
    <a
      href={`tel:${phone}`}
      aria-label={`Gọi ${name}`}
      className="shrink-0 inline-flex items-center gap-1 text-xs text-cobalt font-medium hover:underline"
    >
      <Phone size={12} aria-hidden="true" />
      <span className="tnum">{phone}</span>
    </a>
  );
}
