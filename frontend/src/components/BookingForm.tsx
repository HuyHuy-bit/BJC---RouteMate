import { useState } from "react";
import { Lock, Users } from "lucide-react";
import { api } from "../lib/api";
import type { GeocodeResult } from "../types";
import Button from "./ui/Button";
import Field from "./ui/Field";
import MapView, { MAP_COLORS } from "./MapView";
import AddressField from "./AddressField";
import { useToast } from "./ui/Toast";
import { getErrorMessage } from "../lib/errors";

const PICKUP_COLOR = MAP_COLORS.pickup;
const DROPOFF_COLOR = MAP_COLORS.dropoff;

function defaultDateTimeLocal() {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  return now.toISOString().slice(0, 16);
}

export default function BookingForm({ onCreated }: { onCreated: () => void }) {
  const toast = useToast();
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [pickup, setPickup] = useState<GeocodeResult | null>(null);
  const [dropoff, setDropoff] = useState<GeocodeResult | null>(null);
  const [pickupAt, setPickupAt] = useState(defaultDateTimeLocal());
  const [isPrivate, setIsPrivate] = useState(false);
  const [seats, setSeats] = useState(1);
  const [submitting, setSubmitting] = useState(false);

  const canSubmit = Boolean(
    fullName.trim() && phone.trim() && pickup && dropoff && pickupAt
  );

  const pins = [
    ...(pickup ? [{ lat: pickup.lat, lng: pickup.lng, color: PICKUP_COLOR }] : []),
    ...(dropoff ? [{ lat: dropoff.lat, lng: dropoff.lng, color: DROPOFF_COLOR }] : []),
  ];

  const submit = async () => {
    if (!canSubmit || !pickup || !dropoff) return;
    setSubmitting(true);
    try {
      await api.bookings.create({
        customer: { full_name: fullName.trim(), phone: phone.trim() },
        pickup_address: pickup.formatted_address,
        pickup_lat: pickup.lat,
        pickup_lng: pickup.lng,
        dropoff_address: dropoff.formatted_address,
        dropoff_lat: dropoff.lat,
        dropoff_lng: dropoff.lng,
        requested_pickup_at: new Date(pickupAt).toISOString(),
        is_private: isPrivate,
        // A private hire books the whole car regardless of headcount,
        // so seats only means something for a shared ride.
        seats: isPrivate ? 1 : seats,
      });
      toast(`Đã thêm khách ${fullName.trim()}.`, "success");
      setFullName("");
      setPhone("");
      setPickup(null);
      setDropoff(null);
      setPickupAt(defaultDateTimeLocal());
      setIsPrivate(false);
      setSeats(1);
      onCreated();
    } catch (err: any) {
      toast(
        getErrorMessage(err, "Không thêm được khách. Thử lại."),
        "error"
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
      className="space-y-5"
      noValidate
    >
      <div className="grid sm:grid-cols-2 gap-4">
        <Field
          label="Tên khách hàng"
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          required
        />
        <Field
          label="Số điện thoại"
          type="tel"
          inputMode="tel"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          required
        />
      </div>

      <div className="space-y-4">
        <AddressField
          label="Địa chỉ đón"
          selected={pickup}
          onSelect={setPickup}
          accentColor={PICKUP_COLOR}
        />
        <AddressField
          label="Địa chỉ trả"
          selected={dropoff}
          onSelect={setDropoff}
          accentColor={DROPOFF_COLOR}
        />
      </div>

      {pins.length > 0 && (
        <div className="animate-fade-in">
          <MapView pins={pins} height={200} />
          <div className="flex items-center gap-4 mt-2 text-[11px] text-[var(--text-tertiary)]">
            <span className="flex items-center gap-1.5">
              <span
                className="w-2 h-2 rounded-full"
                style={{ background: PICKUP_COLOR }}
                aria-hidden="true"
              />
              Điểm đón
            </span>
            <span className="flex items-center gap-1.5">
              <span
                className="w-2 h-2 rounded-full"
                style={{ background: DROPOFF_COLOR }}
                aria-hidden="true"
              />
              Điểm trả
            </span>
          </div>
        </div>
      )}

      <Field
        label="Ngày giờ đón"
        type="datetime-local"
        value={pickupAt}
        onChange={(e) => setPickupAt(e.target.value)}
        hint="Chỉ khách đi cùng ngày, cùng chiều mới được ghép chung xe."
        required
        className="max-w-[16rem]"
      />

      <fieldset className="border-0 p-0 m-0">
        <legend className="text-[12px] font-medium mb-2 text-[var(--text-secondary)]">
          Hình thức
        </legend>
        <div className="grid sm:grid-cols-2 gap-2">
          <RideTypeOption
            selected={!isPrivate}
            onSelect={() => setIsPrivate(false)}
            icon={<Users size={15} aria-hidden="true" />}
            title="Ghép xe"
            description="Đi chung tối đa 4 khách"
          />
          <RideTypeOption
            selected={isPrivate}
            onSelect={() => setIsPrivate(true)}
            icon={<Lock size={15} aria-hidden="true" />}
            title="Bao xe riêng"
            description="Giá gấp 4 lần, đi một mình"
          />
        </div>
      </fieldset>

      {/* Seats only matter for a shared ride — a private hire is the
          whole car however many people travel in it. */}
      {!isPrivate && (
        <fieldset className="border-0 p-0 m-0">
          <legend className="text-[12px] font-medium mb-2 text-[var(--text-secondary)]">
            Số khách đi cùng
          </legend>
          <div className="flex items-center gap-2">
            {[1, 2, 3, 4].map((n) => (
              <button
                key={n}
                type="button"
                aria-pressed={seats === n}
                onClick={() => setSeats(n)}
                className={[
                  "w-10 h-10 rounded-[var(--radius)] text-sm font-medium tnum transition-colors",
                  "border",
                  seats === n
                    ? "bg-[var(--surface-inverse)] text-white border-transparent"
                    : "bg-[var(--surface)] text-[var(--text-secondary)] border-[var(--border-strong)] hover:bg-[var(--surface-sunken)]",
                ].join(" ")}
              >
                {n}
              </button>
            ))}
            <span className="text-xs text-[var(--text-tertiary)] ml-1">
              {seats > 1
                ? `${seats} chỗ trên cùng một xe`
                : "1 chỗ"}
            </span>
          </div>
        </fieldset>
      )}

      <div className="flex justify-end pt-1">
        <Button
          type="submit"
          variant="primary"
          size="lg"
          disabled={!canSubmit}
          loading={submitting}
        >
          Thêm khách
        </Button>
      </div>
    </form>
  );
}

function RideTypeOption({
  selected,
  onSelect,
  icon,
  title,
  description,
}: {
  selected: boolean;
  onSelect: () => void;
  icon: React.ReactNode;
  title: string;
  description: string;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={[
        "text-left p-3 rounded-[var(--radius-md)] border transition-all duration-[var(--duration-fast)]",
        selected
          ? "border-[var(--brand-red)] bg-[var(--brand-red-subtle)]"
          : "border-[var(--border-strong)] bg-[var(--surface)] hover:border-[var(--text-tertiary)]",
      ].join(" ")}
    >
      <div className="flex items-center gap-2">
        <span
          className={
            selected ? "text-[var(--brand-red)]" : "text-[var(--text-tertiary)]"
          }
        >
          {icon}
        </span>
        <span className="text-sm font-medium">{title}</span>
      </div>
      <p className="text-xs text-[var(--text-tertiary)] mt-1">{description}</p>
    </button>
  );
}
