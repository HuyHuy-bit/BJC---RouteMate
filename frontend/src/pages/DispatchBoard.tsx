import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import BookingForm from "../components/BookingForm";
import BookingsList from "../components/BookingsList";
import TripsPanel from "../components/TripsPanel";

export default function DispatchBoard() {
  const { user, logout } = useAuth();
  const queryClient = useQueryClient();
  const [radius, setRadius] = useState(3000);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  const bookingsQuery = useQuery({
    queryKey: ["bookings"],
    queryFn: () => api.bookings.list(),
  });
  const tripsQuery = useQuery({
    queryKey: ["trips"],
    queryFn: () => api.dispatch.trips(),
  });

  const refreshAll = () => {
    queryClient.invalidateQueries({ queryKey: ["bookings"] });
    queryClient.invalidateQueries({ queryKey: ["trips"] });
  };

  const runMatching = async () => {
    setRunning(true);
    setRunError(null);
    try {
      await api.dispatch.run(radius);
      refreshAll();
    } catch (err: any) {
      setRunError(err?.response?.data?.detail ?? "Không thể ghép chuyến");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="min-h-screen" style={{ background: "var(--paper)" }}>
      <div className="max-w-5xl mx-auto px-6 py-7">
        <div
          className="flex justify-between items-end mb-6 pb-3 border-b-2"
          style={{ borderColor: "var(--ink)" }}
        >
          <div>
            <div
              className="text-xs tracking-widest mb-1"
              style={{ color: "var(--amber)", fontFamily: "'JetBrains Mono', monospace" }}
            >
              BẢNG ĐIỀU PHỐI · NỘI BỘ
            </div>
            <h1
              className="text-2xl font-bold"
              style={{ fontFamily: "'Space Grotesk', sans-serif" }}
            >
              Bắc Giang ⇄ Hà Nội
            </h1>
          </div>
          <div className="text-right text-sm">
            <div style={{ color: "var(--mute)" }}>{user?.full_name}</div>
            <div className="flex gap-3 justify-end">
              {user?.role === "admin" && (
                <Link
                  to="/admin/users/new"
                  className="text-xs underline"
                  style={{ color: "var(--mute)" }}
                >
                  + Tài khoản nhân viên
                </Link>
              )}
              <button
                onClick={logout}
                className="text-xs underline"
                style={{ color: "var(--mute)" }}
              >
                Đăng xuất
              </button>
            </div>
          </div>
        </div>

        <div className="mb-5">
          <BookingForm onCreated={refreshAll} />
        </div>

        <div
          className="flex items-center justify-between mb-5 px-4 py-3 rounded"
          style={{ background: "var(--ink)" }}
        >
          <div className="flex items-center gap-3 text-white">
            <span
              className="text-xs"
              style={{ fontFamily: "'JetBrains Mono', monospace", color: "#D8CFB8" }}
            >
              ĐỘ LỆCH TỐI ĐA CHO PHÉP: {radius}m
            </span>
            <input
              type="range"
              min={500}
              max={10000}
              step={500}
              value={radius}
              onChange={(e) => setRadius(Number(e.target.value))}
            />
          </div>
          <button
            onClick={runMatching}
            disabled={running}
            className="px-4 py-2 rounded text-sm font-semibold text-white"
            style={{ background: "var(--amber)", opacity: running ? 0.6 : 1 }}
          >
            {running ? "Đang ghép..." : "Ghép chuyến"}
          </button>
        </div>
        {runError && (
          <div className="text-sm mb-4" style={{ color: "var(--coral)" }}>
            {runError}
          </div>
        )}

        <div className="mb-6">
          <div
            className="text-sm font-semibold mb-2"
            style={{ fontFamily: "'Space Grotesk', sans-serif" }}
          >
            Danh sách khách ({bookingsQuery.data?.length ?? 0})
          </div>
          {bookingsQuery.isLoading ? (
            <div className="text-sm" style={{ color: "var(--mute)" }}>
              Đang tải...
            </div>
          ) : (
            <BookingsList bookings={bookingsQuery.data ?? []} onChanged={refreshAll} />
          )}
        </div>

        <TripsPanel trips={tripsQuery.data ?? []} />
      </div>
    </div>
  );
}
