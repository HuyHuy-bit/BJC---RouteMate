import { useState } from "react";
import { api } from "../lib/api";
import type { GeocodeResult } from "../types";

interface Props {
  label: string;
  onSelect: (result: GeocodeResult) => void;
  selected: GeocodeResult | null;
}

export default function AddressField({ label, onSelect, selected }: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<GeocodeResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const search = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    setResults([]);
    try {
      const res = await api.geocode(query);
      if (res.results.length === 0) {
        setError("Không tìm thấy địa chỉ này");
      }
      setResults(res.results);
    } catch (err: any) {
      setError(
        err?.response?.data?.detail ??
          "Không thể tìm địa chỉ — kiểm tra kết nối Goong Maps"
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div
        className="text-xs mb-1"
        style={{ color: "var(--mute)", fontFamily: "'JetBrains Mono', monospace" }}
      >
        {label}
      </div>
      <div className="flex gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && search()}
          placeholder="Nhập địa chỉ..."
          className="flex-1 border rounded px-3 py-2 text-sm"
          style={{ borderColor: "var(--line)" }}
        />
        <button
          type="button"
          onClick={search}
          disabled={loading || !query.trim()}
          className="px-3 border rounded text-sm"
          style={{ borderColor: "var(--line)" }}
        >
          {loading ? "..." : "Tìm"}
        </button>
      </div>

      {error && (
        <div className="text-xs mt-1" style={{ color: "var(--amber)" }}>
          {error}
        </div>
      )}

      {results.length > 0 && (
        <div
          className="mt-2 border rounded overflow-hidden"
          style={{ borderColor: "var(--line)" }}
        >
          {results.map((r) => (
            <button
              type="button"
              key={r.place_id}
              onClick={() => {
                onSelect(r);
                setResults([]);
                setQuery(r.formatted_address);
              }}
              className="block w-full text-left px-3 py-2 text-sm hover:bg-gray-50 border-b last:border-b-0"
              style={{ borderColor: "var(--line)" }}
            >
              {r.formatted_address}
            </button>
          ))}
        </div>
      )}

      {selected && (
        <div className="text-xs mt-1" style={{ color: "var(--teal)" }}>
          ✓ Đã chọn: {selected.formatted_address} ({selected.lat.toFixed(5)},{" "}
          {selected.lng.toFixed(5)})
        </div>
      )}
    </div>
  );
}
