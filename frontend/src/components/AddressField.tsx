import { useId, useState } from "react";
import { Check, Loader2, MapPin, Search } from "lucide-react";
import { api } from "../lib/api";
import type { GeocodeResult } from "../types";
import Button from "./ui/Button";
import { getErrorMessage } from "../lib/errors";

interface Props {
  label: string;
  placeholder?: string;
  selected: GeocodeResult | null;
  onSelect: (r: GeocodeResult) => void;
  accentColor: string;
}

/**
 * Search-then-confirm, with results as a real listbox. The map preview
 * moved out to a single shared trip map (see BookingForm) so pickup and
 * dropoff can be judged together rather than in isolation.
 */
export default function AddressField({
  label,
  placeholder = "Ví dụ: 12 Việt Yên, Bắc Giang",
  selected,
  onSelect,
  accentColor,
}: Props) {
  const id = useId();
  const [query, setQuery] = useState(selected?.formatted_address ?? "");
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
        setError("Không tìm thấy địa chỉ này. Thử nhập tên xã hoặc phường.");
      }
      setResults(res.results);
    } catch (err: any) {
      setError(
        getErrorMessage(err, "Không tìm được địa chỉ. Kiểm tra kết nối.")
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <label
        htmlFor={id}
        className="flex items-center gap-1.5 text-xs font-medium mb-1.5 text-muted"
      >
        <span
          className="w-2 h-2 rounded-full shrink-0"
          style={{ background: accentColor }}
          aria-hidden="true"
        />
        {label}
      </label>

      <div className="flex gap-2">
        <input
          id={id}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              search();
            }
          }}
          placeholder={placeholder}
          aria-describedby={error ? `${id}-error` : undefined}
          className="flex-1 h-9 px-3 text-base rounded bg-surface border border-line-strong hover:border-faint focus:border-line-focus transition-colors placeholder:text-faint"
        />
        <Button
          type="button"
          onClick={search}
          disabled={!query.trim() || loading}
          aria-label={`Tìm ${label.toLowerCase()}`}
          className="!px-2.5 shrink-0"
        >
          {loading ? (
            <Loader2 size={15} className="animate-spin" aria-hidden="true" />
          ) : (
            <Search size={15} aria-hidden="true" />
          )}
        </Button>
      </div>

      {error && (
        <p id={`${id}-error`} role="alert" className="mt-1.5 text-xs text-warning">
          {error}
        </p>
      )}

      {results.length > 0 && (
        <ul
          role="listbox"
          aria-label="Kết quả tìm kiếm"
          className="mt-2 border border-line rounded-md overflow-hidden bg-surface shadow-sm animate-slide-up max-h-52 overflow-y-auto"
        >
          {results.map((r) => (
            <li key={r.place_id} role="option" aria-selected={false}>
              <button
                type="button"
                onClick={() => {
                  onSelect(r);
                  setResults([]);
                  setQuery(r.formatted_address);
                }}
                className="w-full text-left px-3 py-2.5 text-sm flex items-start gap-2 hover:bg-sunken transition-colors border-b border-line last:border-b-0"
              >
                <MapPin
                  size={14}
                  className="mt-0.5 shrink-0 text-faint"
                  aria-hidden="true"
                />
                <span className="leading-snug">{r.formatted_address}</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {selected && results.length === 0 && (
        <p className="mt-1.5 text-xs text-success flex items-start gap-1.5">
          <Check size={13} className="mt-0.5 shrink-0" aria-hidden="true" />
          <span className="leading-snug">{selected.formatted_address}</span>
        </p>
      )}
    </div>
  );
}
