import { useState } from "react";
import { ArrowRight, Inbox, Lock, Trash2, Undo2 } from "lucide-react";
import type { BookingOut } from "../types";
import { api } from "../lib/api";
import { BOOKING_STATUS, DIRECTION, fmtDayLabel, fmtTime, fmtVnd } from "../lib/format";
import Badge from "./ui/Badge";
import Button from "./ui/Button";
import ConfirmDialog from "./ui/ConfirmDialog";
import EmptyState from "./ui/EmptyState";
import Skeleton from "./ui/Skeleton";
import { useToast } from "./ui/Toast";
import { getErrorMessage } from "../lib/errors";

export default function BookingsList({
  bookings,
  loading,
  onChanged,
  onAddBooking,
}: {
  bookings: BookingOut[];
  loading?: boolean;
  onChanged: () => void;
  onAddBooking: () => void;
}) {
  const toast = useToast();
  const [pendingDelete, setPendingDelete] = useState<BookingOut | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [unassigning, setUnassigning] = useState<string | null>(null);

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    setDeleting(true);
    try {
      await api.customers.delete(pendingDelete.customer.id);
      toast(`Đã xoá khách ${pendingDelete.customer.full_name}.`, "success");
      setPendingDelete(null);
      onChanged();
    } catch {
      toast("Không xoá được khách hàng. Thử lại.", "error");
    } finally {
      setDeleting(false);
    }
  };

  const handleUnassign = async (b: BookingOut) => {
    setUnassigning(b.id);
    try {
      await api.bookings.unassign(b.id);
      toast(`Đã đưa ${b.customer.full_name} về hàng chờ.`, "success");
      onChanged();
    } catch (err: any) {
      toast(getErrorMessage(err, "Không bỏ được khách khỏi chuyến."), "error");
    } finally {
      setUnassigning(null);
    }
  };

  if (loading) {
    return (
      <div className="space-y-2 p-3">
        <Skeleton className="h-[72px] w-full" count={3} />
      </div>
    );
  }

  if (bookings.length === 0) {
    return (
      <EmptyState
        icon={<Inbox size={18} aria-hidden="true" />}
        title="Chưa có khách nào trong hàng chờ"
        description="Thêm khách để hệ thống bắt đầu ghép chuyến theo tuyến và ngày đi."
        action={
          <Button variant="primary" size="sm" onClick={onAddBooking}>
            Thêm khách
          </Button>
        }
      />
    );
  }

  return (
    <>
      <ul className="divide-y divide-[var(--border)]">
        {bookings.map((b) => {
          const status = BOOKING_STATUS[b.status];
          // Only a booking still sitting in a FORMING pool makes sense to
          // pull back out manually — once a trip is sealed/assigned the
          // route and vehicle are already committed, so unassigning would
          // just orphan a locked trip instead of freeing anything useful.
          const canUnassign = b.trip_id !== null && b.status === "matched";

          return (
            <li
              key={b.id}
              className="group flex items-start gap-3 px-4 py-3 hover:bg-[var(--surface-sunken)] transition-colors"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-medium text-[var(--text)]">
                    {b.customer.full_name}
                  </span>
                  {b.is_private && (
                    <Badge tone="danger">
                      <Lock size={10} aria-hidden="true" />
                      Bao xe
                    </Badge>
                  )}
                  <Badge tone={status.tone}>{status.label}</Badge>
                </div>

                <p className="text-xs text-[var(--text-secondary)] mt-1 flex items-center gap-1.5 min-w-0">
                  <span className="truncate">{b.pickup_address}</span>
                  <ArrowRight
                    size={11}
                    className="shrink-0 text-[var(--text-tertiary)]"
                    aria-hidden="true"
                  />
                  <span className="truncate">{b.dropoff_address}</span>
                </p>

                <p className="text-[11px] text-[var(--text-tertiary)] mt-1 flex items-center gap-2 flex-wrap">
                  <span className="tnum">
                    {fmtDayLabel(b.requested_pickup_at)} ·{" "}
                    {fmtTime(b.requested_pickup_at)}
                  </span>
                  <span aria-hidden="true">·</span>
                  <span>{DIRECTION[b.direction].short}</span>
                </p>
              </div>

              <div className="flex items-center gap-1 shrink-0">
                <span className="text-sm font-medium tnum text-[var(--text)] mr-1">
                  {fmtVnd(b.price_vnd)}
                </span>

                {canUnassign && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleUnassign(b)}
                    loading={unassigning === b.id}
                    aria-label={`Bỏ ${b.customer.full_name} khỏi chuyến`}
                    title="Đưa về hàng chờ để ghép lại"
                    className="!px-1.5 opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-opacity"
                  >
                    <Undo2 size={14} aria-hidden="true" />
                  </Button>
                )}

                <Button
                  variant="danger-subtle"
                  size="sm"
                  onClick={() => setPendingDelete(b)}
                  aria-label={`Xoá khách ${b.customer.full_name}`}
                  className="!px-1.5 opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-opacity"
                >
                  <Trash2 size={14} aria-hidden="true" />
                </Button>
              </div>
            </li>
          );
        })}
      </ul>

      <ConfirmDialog
        open={pendingDelete !== null}
        title={`Xoá khách ${pendingDelete?.customer.full_name ?? ""}?`}
        description="Toàn bộ lịch sử đặt xe của khách này sẽ bị xoá vĩnh viễn. Nếu chuyến chỉ còn khách này, chuyến cũng sẽ bị huỷ."
        confirmLabel="Xoá vĩnh viễn"
        loading={deleting}
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </>
  );
}
