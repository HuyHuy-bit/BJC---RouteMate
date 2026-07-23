import { useEffect, useRef } from "react";
import goongjs from "@goongmaps/goong-js";
import type { Map as GoongMap, Marker as GoongMarker } from "@goongmaps/goong-js";
import "@goongmaps/goong-js/dist/goong-js.css";

interface Pin {
  lat: number;
  lng: number;
  color?: string;
}

interface Props {
  center: { lat: number; lng: number };
  pins: Pin[];
  zoom?: number;
  height?: number;
}

const MAPTILES_KEY = import.meta.env.VITE_GOONG_MAPTILES_KEY as
  | string
  | undefined;

export default function MapView({ center, pins, zoom = 14, height = 180 }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<GoongMap | null>(null);
  const markersRef = useRef<GoongMarker[]>([]);

  useEffect(() => {
    if (!MAPTILES_KEY || !containerRef.current) return;

    goongjs.accessToken = MAPTILES_KEY;
    const map = new goongjs.Map({
      container: containerRef.current,
      style: "https://tiles.goong.io/assets/goong_map_web.json",
      center: [center.lng, center.lat],
      zoom,
    });
    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
    // Intentionally only re-init on mount — pan/marker updates below handle
    // subsequent prop changes without tearing the whole map down.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!mapRef.current) return;
    mapRef.current.setCenter([center.lng, center.lat]);
  }, [center.lat, center.lng]);

  useEffect(() => {
    if (!mapRef.current) return;
    markersRef.current.forEach((m) => m.remove());
    markersRef.current = pins.map((p) => {
      const marker = new goongjs.Marker({ color: p.color ?? "#c97a2b" })
        .setLngLat([p.lng, p.lat])
        .addTo(mapRef.current!);
      return marker;
    });
  }, [pins]);

  if (!MAPTILES_KEY) {
    return (
      <div
        className="flex items-center justify-center text-xs rounded border"
        style={{
          height,
          color: "var(--mute)",
          borderColor: "var(--line)",
          background: "var(--paper-dim)",
        }}
      >
        Bản đồ chưa khả dụng — cần cấu hình VITE_GOONG_MAPTILES_KEY
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="rounded border overflow-hidden"
      style={{ height, borderColor: "var(--line)" }}
    />
  );
}
