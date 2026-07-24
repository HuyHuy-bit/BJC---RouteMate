import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ArrowLeft, Car, History, Lock, Users } from "lucide-react";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { DIRECTION, TRIP_STATUS, fmtDateTime, fmtVnd } from "../lib/format";
import AppShell from "../components/layout/AppShell";
import Badge from "../components/ui/Badge";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import EmptyState from "../components/ui/EmptyState";
import Skeleton from "../components/ui/Skeleton";

export default function HistoryPage() {
  const { user } = useAuth();
  const isDriver = user?.role === "driver";

  const historyQuery = useQuery({
    queryKey: ["history", isDriver ? "mine" : "all"],
    queryFn: () => (isDriver ? api.dispatch.myHistory() : api.dispatch.history()),
  });

  const trips = historyQuery.data ?? [];

  return (
    <AppShell
      title="Lịch sử chuyến"
      subtitle={
        isDriver ? "Các chuyến bạn đã hoàn thành" : "Toàn bộ chuyến đã hoàn thành hoặc huỷ"
      }
      width={isDriver ? "narrow" : "wide"}
      actions={
        <Link to={isDriver ? "/driver" : "/"}>
          <Button variant="ghost" iconLeft={<ArrowLeft size={15} aria-hidden="true" />}>
            Quay lại
          </Button>
        </Link>
      }
    >
      {historyQuery.isLoading && (
        <Skeleton className="h-40 w-full rounded-[var(--radius-lg)] mb-3" count={4} />
      )}

      {!historyQuery.isLoading && trips.length === 0 && (
        <Card>
          <EmptyState
            icon={<History size={18} aria-hidden="true" />}
            title="Chưa có chuyến nào trong lịch sử"
            description="Các chuyến sau khi hoàn thành hoặc bị huỷ sẽ xuất hiện ở đây, cùng danh sách khách và thời gian hoàn tất."
          />
        </Card>
      )}

      <div
        className={
          isDriver
            ? "space-y-3"
            : "grid gap-3 sm:grid-cols-2 xl:grid-cols-3"
        }
      >
        {trips.map((trip) => {
          const status = TRIP_STATUS[trip.status];
          const direction = trip.bookings[0]?.direction;
          const revenue = trip.bookings.reduce((s, b) => s + b.price_vnd, 0);
          const finishedAt = trip.completed_at ?? trip.cancelled_at;

          return (
            <Card
              key={trip.id}
              className="p-4"
              accent={trip.status === "cancelled" ? "var(--danger)" : "var(--success)"}
            >
              <div className="flex items-start justify-between gap-2 mb-2">
                <div>
                  <h3 className="text-sm font-semibold flex items-center gap-1.5">
                    <Car size={13} className="text-[var(--text-tertiary)]" aria-hidden="true" />
                    {trip.vehicle_label ?? "Xe"}
                  </h3>
                  {direction && (
                    <p className="text-[11px] text-[var(--text-tertiary)] mt-0.5">
                      {DIRECTION[direction].label}
                    </p>
                  )}
                </div>
                <Badge tone={status.tone}>{status.label}</Badge>
              </div>

              <p className="text-[11px] text-[var(--text-tertiary)] flex items-center gap-1.5 mb-2 tnum">
                {finishedAt ? fmtDateTime(finishedAt) : "—"}
              </p>

              <p className="text-[11px] text-[var(--text-tertiary)] flex items-center gap-1.5 mb-2">
                {trip.is_private ? (
                  <>
                    <Lock size={11} aria-hidden="true" /> Bao xe riêng
                  </>
                ) : (
                  <>
                    <Users size={11} aria-hidden="true" /> {trip.bookings.length} khách
                  </>
                )}
              </p>

              <ol className="space-y-1 mb-3">
                {trip.bookings.map((b, i) => (
                  <li key={b.id} className="text-[13px] flex items-baseline gap-2">
                    <span className="tnum text-[10px] text-[var(--text-tertiary)] w-3.5 shrink-0">
                      {i + 1}
                    </span>
                    <span className="truncate">{b.customer.full_name}</span>
                  </li>
                ))}
              </ol>

              <div className="flex items-center justify-between pt-2 border-t border-[var(--border)]">
                <span className="text-[11px] text-[var(--text-tertiary)]">Doanh thu</span>
                <span className="text-sm font-semibold tnum">{fmtVnd(revenue)}</span>
              </div>
            </Card>
          );
        })}
      </div>
    </AppShell>
  );
}
