import { useState } from "react";
import AddressField from "./AddressField";
import { api } from "../lib/api";
import type { GeocodeResult } from "../types";

function defaultDateTimeLocal() {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  return now.toISOString().slice(0, 16);
}

export default function BookingForm({ onCreated }: { onCreated: () => void }) {
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [pickup, setPickup] = useState<GeocodeResult | null>(null);
  const [dropoff, setDropoff] = useState<GeocodeResult | null>(null);
  const [pickupAt, setPickupAt] = useState(defaultDateTimeLocal());
  const [isPrivate, setIsPrivate] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = fullName.trim() && phone.trim() && pickup && dropoff && pickupAt;

  const reset = () => {
    setFullName("");
    setPhone("");
    setPickup(null);
    setDropoff(null);
    setPickupAt(defaultDateTimeLocal());
    setIsPrivate(false);
  };

  const submit = async () => {
    if (!canSubmit || !pickup || !dropoff) return;
    setSubmitting(true);
    setError(null);
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
      });
      reset();
      onCreated();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Không thể tạo chuyến");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="bg-white border rounded p-4 space-y-4"
      style={{ borderColor: "var(--line)" }}
    >
      <div className="grid grid-cols-2 gap-3">
        <div>
          <div
            className="text-xs mb-1"
            style={{ color: "var(--mute)", fontFamily: "'JetBrains Mono', monospace" }}
          >
            TÊN KHÁCH HÀNG
          </div>
          <input
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            className="w-full border rounded px-3 py-2 text-sm"
            style={{ borderColor: "var(--line)" }}
          />
        </div>
        <div>
          <div
            className="text-xs mb-1"
            style={{ color: "var(--mute)", fontFamily: "'JetBrains Mono', monospace" }}
          >
            SỐ ĐIỆN THOẠI
          </div>
          <input
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            className="w-full border rounded px-3 py-2 text-sm"
            style={{ borderColor: "var(--line)" }}
          />
        </div>
      </div>

      <AddressField label="ĐỊA CHỈ ĐÓN" selected={pickup} onSelect={setPickup} />
      <AddressField label="ĐỊA CHỈ TRẢ" selected={dropoff} onSelect={setDropoff} />

      <div>
        <div
          className="text-xs mb-1"
          style={{ color: "var(--mute)", fontFamily: "'JetBrains Mono', monospace" }}
        >
          NGÀY GIỜ ĐÓN
        </div>
        <input
          type="datetime-local"
          value={pickupAt}
          onChange={(e) => setPickupAt(e.target.value)}
          className="border rounded px-3 py-2 text-sm"
          style={{ borderColor: "var(--line)" }}
        />
        <div className="text-xs mt-1" style={{ color: "var(--mute)" }}>
          Chỉ những khách cùng ngày mới được ghép chung xe.
        </div>
      </div>

      <div className="flex items-center justify-between">
        <label
          className="flex items-center gap-2 text-sm"
          style={{ color: isPrivate ? "var(--coral)" : "var(--ink)" }}
        >
          <input
            type="checkbox"
            checked={isPrivate}
            onChange={(e) => setIsPrivate(e.target.checked)}
          />
          Bao xe riêng (x4)
        </label>
        <button
          type="button"
          onClick={submit}
          disabled={!canSubmit || submitting}
          className="px-4 py-2 rounded text-sm font-semibold text-white"
          style={{
            background: canSubmit ? "var(--ink)" : "var(--paper-dim)",
            color: canSubmit ? "#fff" : "var(--mute)",
          }}
        >
          {submitting ? "Đang thêm..." : "Thêm khách"}
        </button>
      </div>

      {error && (
        <div className="text-sm" style={{ color: "var(--coral)" }}>
          {error}
        </div>
      )}
    </div>
  );
}
