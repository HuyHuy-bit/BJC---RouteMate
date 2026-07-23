import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import BookingForm from "../components/BookingForm";
import BookingsList from "../components/BookingsList";
import TripsPanel from "../components/TripsPanel";

// Fixed rather than dispatcher-adjustable — 15km covers this business's
// service area comfortably without needing a technical knob in the UI.
const MAX_DETOUR_METERS = 15000;

export default function DispatchBoard() {
  const { user, logout } = useAuth();
  const queryClient = useQueryClient();
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
      await api.dispatch.run(MAX_DETOUR_METERS);
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
          <div className="flex items-center gap-3">
            <img
              src="/bjc-logo.jpg"
              alt="BJC Group"
              className="w-10 h-10 rounded-full object-cover"
            />
            <div>
              <div
                className="text-xs tracking-widest mb-1"
                style={{ color: "var(--coral)", fontFamily: "'JetBrains Mono', monospace" }}
              >
                THÀNH CÔNG LIMOUSINE · BJC GROUP
              </div>
              <h1
                className="text-2xl font-bold"
                style={{ fontFamily: "'Sora', sans-serif" }}
              >
                Bảng điều phối · Bắc Giang ⇄ Hà Nội
              </h1>
            </div>
          </div>
          <div className="text-right text-sm">
            <div className="mb-2" style={{ color: "var(--mute)" }}>{user?.full_name}</div>
            <div className="flex gap-2 justify-end">
              {user?.role === "admin" && (
                <Link
                  to="/admin/users/new"
                  className="text-xs font-medium rounded px-3 py-1.5 border"
                  style={{ color: "var(--brand-blue)", borderColor: "var(--brand-blue)" }}
                >
                  + Tài khoản nhân viên
                </Link>
              )}
              <button
                onClick={logout}
                className="text-xs font-medium rounded px-3 py-1.5 border"
                style={{ color: "var(--coral)", borderColor: "var(--coral)" }}
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
          className="flex items-center justify-center mb-5 px-4 py-3 rounded"
          style={{ background: "var(--ink)" }}
        >
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
            style={{ fontFamily: "'Sora', sans-serif" }}
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
