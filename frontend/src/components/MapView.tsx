import { useEffect, useRef } from "react";
import goongjs from "@goongmaps/goong-js";
import type { Map as GoongMap, Marker as GoongMarker } from "@goongmaps/goong-js";
import "@goongmaps/goong-js/dist/goong-js.css";

export interface Pin {
  lat: number;
  lng: number;
  /** Must be a literal color — Goong renders markers to a WebGL canvas,
   *  which cannot resolve CSS custom properties. */
  color?: string;
}

/** Literal mirrors of the brand tokens, for canvas-rendered contexts. */
export const MAP_COLORS = {
  pickup: "#1b5fa8",
  dropoff: "#d6331f",
} as const;

interface Props {
  pins: Pin[];
  zoom?: number;
  height?: number;
  className?: string;
}

const MAPTILES_KEY = import.meta.env.VITE_GOONG_MAPTILES_KEY as string | undefined;

/**
 * Renders every supplied pin and auto-frames them. Previously each
 * address had its own separate map, which meant you could never see the
 * pickup and dropoff in relation to each other — the one thing a
 * dispatcher actually needs to judge.
 */
export default function MapView({ pins, zoom = 12, height = 200, className = "" }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<GoongMap | null>(null);
  const markersRef = useRef<GoongMarker[]>([]);

  const center = pins.length
    ? {
        lat: pins.reduce((s, p) => s + p.lat, 0) / pins.length,
        lng: pins.reduce((s, p) => s + p.lng, 0) / pins.length,
      }
    : { lat: 21.15, lng: 106.02 };

  useEffect(() => {
    if (!MAPTILES_KEY || !containerRef.current) return;
    goongjs.accessToken = MAPTILES_KEY;
    const map = new goongjs.Map({
      container: containerRef.current,
      style: "https://tiles.goong.io/assets/goong_map_web.json",
      center: [center.lng, center.lat],
      zoom: pins.length > 1 ? 9 : zoom,
    });
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!mapRef.current || !pins.length) return;
    mapRef.current.setCenter([center.lng, center.lat]);
    mapRef.current.setZoom(pins.length > 1 ? 9 : zoom);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [center.lat, center.lng, pins.length]);

  useEffect(() => {
    if (!mapRef.current) return;
    markersRef.current.forEach((m) => m.remove());
    markersRef.current = pins.map((p) =>
      new goongjs.Marker({ color: p.color ?? MAP_COLORS.dropoff })
        .setLngLat([p.lng, p.lat])
        .addTo(mapRef.current!)
    );
  }, [pins]);

  if (!MAPTILES_KEY) {
    return (
      <div
        className={`flex items-center justify-center text-xs rounded-[var(--radius-md)] bg-[var(--surface-sunken)] border border-dashed border-[var(--border-strong)] text-[var(--text-tertiary)] ${className}`}
        style={{ height }}
      >
        Chưa cấu hình bản đồ
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      role="img"
      aria-label={`Bản đồ hiển thị ${pins.length} điểm`}
      className={`rounded-[var(--radius-md)] overflow-hidden border border-[var(--border)] ${className}`}
      style={{ height }}
    />
  );
}
