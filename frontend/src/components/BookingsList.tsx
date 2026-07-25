import { useState } from "react";
import { ArrowRight, Filter, Inbox, Lock, Trash2, Undo2 } from "lucide-react";
import type { BookingOut } from "../types";
import { api } from "../lib/api";
import { BOOKING_STATUS, DIRECTION, fmtDayLabel, fmtTime, fmtVnd } from "../lib/format";
import Badge from "./ui/Badge";
import Button from "./ui/Button";
import ConfirmDialog from "./ui/ConfirmDialog";
import EmptyState from "./ui/EmptyState";
import { useToast } from "./ui/Toast";
import { getErrorMessage } from "../lib/errors";

export default function BookingsList({
  bookings,
  filtered = false,
  onChanged,
  onAddBooking,
  onClearFilter,
}: {
  bookings: BookingOut[];
  /** True when a status filter is narrowing the list, so an empty
   *  result means "none match" rather than "no customers at all". */
  filtered?: boolean;
  onChanged: () => void;
  onAddBooking: () => void;
  onClearFilter?: () => void;
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

  if (bookings.length === 0) {
    // An active filter hiding everything is a different situation from
    // an empty queue, and offering "Thêm khách" for it would be a
    // non-sequitur — the customers may well already be there.
    return filtered ? (
      <EmptyState
        icon={<Filter size={18} aria-hidden="true" />}
        title="Không có khách nào ở trạng thái này"
        description="Bộ lọc đang thu hẹp danh sách. Bỏ lọc để xem toàn bộ hàng chờ."
        action={
          onClearFilter && (
            <Button variant="secondary" size="sm" onClick={onClearFilter}>
              Xem tất cả
            </Button>
          )
        }
      />
    ) : (
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
      <ul className="divide-y divide-line">
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
              className="group flex items-start gap-3 px-4 py-3 hover:bg-sunken transition-colors"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-base font-medium text-ink">
                    {b.customer.full_name}
                  </span>
                  {b.is_private && (
                    <Badge tone="danger">
                      <Lock size={10} aria-hidden="true" />
                      Bao xe
                    </Badge>
                  )}
                  {!b.is_private && b.seats > 1 && (
                    <Badge tone="neutral">{b.seats} chỗ</Badge>
                  )}
                  <Badge tone={status.tone}>{status.label}</Badge>
                </div>

                <p className="text-xs text-muted mt-1 flex items-center gap-1.5 min-w-0">
                  <span className="truncate">{b.pickup_address}</span>
                  <ArrowRight
                    size={11}
                    className="shrink-0 text-faint"
                    aria-hidden="true"
                  />
                  <span className="truncate">{b.dropoff_address}</span>
                </p>

                <p className="text-2xs text-faint mt-1 flex items-center gap-2 flex-wrap">
                  <span className="tnum">
                    {fmtDayLabel(b.requested_pickup_at)} ·{" "}
                    {fmtTime(b.requested_pickup_at)}
                  </span>
                  <span aria-hidden="true">·</span>
                  <span>{DIRECTION[b.direction].short}</span>
                </p>
              </div>

              {/* These controls used to be `opacity-0` until hover.
                  Touch devices have no hover, so on the tablet a
                  dispatcher keeps on the desk they were simply
                  invisible — and at ~26x28px they were a poor target
                  even once revealed. Now they are always present, in a
                  quiet tone that lifts on hover, at 44px. */}
              <div className="flex items-center gap-0.5 shrink-0">
                <span className="text-base font-medium tnum text-ink mr-1.5">
                  {fmtVnd(b.price_vnd)}
                </span>

                {canUnassign && (
                  <Button
                    variant="ghost"
                    onClick={() => handleUnassign(b)}
                    loading={unassigning === b.id}
                    aria-label={`Bỏ ${b.customer.full_name} khỏi chuyến`}
                    title="Đưa về hàng chờ để ghép lại"
                    className="!w-touch !h-touch !px-0 text-faint hover:text-ink"
                  >
                    <Undo2 size={16} aria-hidden="true" />
                  </Button>
                )}

                <Button
                  variant="ghost"
                  onClick={() => setPendingDelete(b)}
                  aria-label={`Xoá khách ${b.customer.full_name}`}
                  className="!w-touch !h-touch !px-0 text-faint hover:!text-danger hover:!bg-danger-subtle"
                >
                  <Trash2 size={16} aria-hidden="true" />
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
