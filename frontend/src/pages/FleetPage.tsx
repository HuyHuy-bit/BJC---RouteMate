import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Car, Plus, Trash2 } from "lucide-react";
import { api } from "../lib/api";
import { VEHICLE_STATUS } from "../lib/format";
import type { VehicleOut, VehicleStatus } from "../types";
import AppShell from "../components/layout/AppShell";
import Badge from "../components/ui/Badge";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import ConfirmDialog from "../components/ui/ConfirmDialog";
import EmptyState from "../components/ui/EmptyState";
import Field from "../components/ui/Field";
import Skeleton from "../components/ui/Skeleton";
import SlideOver from "../components/ui/SlideOver";
import { useToast } from "../components/ui/Toast";
import { getErrorMessage } from "../lib/errors";

const STATUS_OPTIONS: VehicleStatus[] = [
  "available",
  "on_trip",
  "maintenance",
  "inactive",
];

export default function FleetPage() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [formOpen, setFormOpen] = useState(false);

  const vehiclesQuery = useQuery({
    queryKey: ["vehicles"],
    queryFn: () => api.vehicles.list(),
  });

  const driversQuery = useQuery({
    queryKey: ["drivers"],
    queryFn: () => api.users.list("driver"),
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["vehicles"] });

  const updateStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: VehicleStatus }) =>
      api.vehicles.update(id, { status }),
    onSuccess: (v) => {
      toast(`${v.plate_number}: ${VEHICLE_STATUS[v.status].label}.`, "success");
      refresh();
    },
    onError: () => toast("Không cập nhật được xe.", "error"),
  });

  const assignDriver = useMutation({
    mutationFn: ({ id, driverId }: { id: string; driverId: string | null }) =>
      api.vehicles.update(id, { default_driver_id: driverId }),
    onSuccess: () => {
      toast("Đã cập nhật tài xế mặc định.", "success");
      refresh();
    },
    onError: () => toast("Không gán được tài xế.", "error"),
  });

  const [pendingDelete, setPendingDelete] = useState<VehicleOut | null>(null);
  const deleteVehicle = useMutation({
    mutationFn: (id: string) => api.vehicles.delete(id),
    onSuccess: () => {
      toast(`Đã xoá xe ${pendingDelete?.plate_number}.`, "success");
      setPendingDelete(null);
      refresh();
    },
    onError: (err) => {
      // A 409 here means the car is actively out on a trip -- the
      // backend refuses to delete a vehicle real passengers depend on
      // right now, so surface exactly why rather than a generic failure.
      toast(getErrorMessage(err, "Không xoá được xe."), "error");
      setPendingDelete(null);
    },
  });

  const vehicles = vehiclesQuery.data ?? [];
  const availableCount = vehicles.filter((v) => v.status === "available").length;

  return (
    <AppShell
      title="Đội xe"
      subtitle={
        vehicles.length > 0
          ? `${availableCount}/${vehicles.length} xe sẵn sàng`
          : undefined
      }
      width="narrow"
      actions={
        <>
          <Link to="/">
            <Button variant="ghost" iconLeft={<ArrowLeft size={15} aria-hidden="true" />}>
              Về bảng điều phối
            </Button>
          </Link>
          <Button
            variant="primary"
            iconLeft={<Plus size={15} aria-hidden="true" />}
            onClick={() => setFormOpen(true)}
          >
            Thêm xe
          </Button>
        </>
      }
    >
      {/* The dispatch engine will not seal a pool it cannot put a real car
          under, so an empty fleet means nothing ever departs. Say that
          plainly rather than letting it look like a bug. */}
      {!vehiclesQuery.isLoading && vehicles.length === 0 && (
        <Card>
          <EmptyState
            icon={<Car size={18} aria-hidden="true" />}
            title="Chưa có xe nào trong hệ thống"
            description="Hệ thống chỉ chốt chuyến khi có xe thật để giao. Thêm xe của công ty để bắt đầu điều phối tự động."
            action={
              <Button variant="primary" size="sm" onClick={() => setFormOpen(true)}>
                Thêm xe đầu tiên
              </Button>
            }
          />
        </Card>
      )}

      {vehiclesQuery.isLoading && (
        <Skeleton className="h-20 w-full rounded-[var(--radius-lg)] mb-3" count={3} />
      )}

      <div className="space-y-3">
        {vehicles.map((v) => (
          <VehicleRow
            key={v.id}
            vehicle={v}
            drivers={driversQuery.data ?? []}
            onStatusChange={(status) =>
              updateStatus.mutate({ id: v.id, status })
            }
            onDriverChange={(driverId) =>
              assignDriver.mutate({ id: v.id, driverId })
            }
            onDelete={() => setPendingDelete(v)}
          />
        ))}
      </div>

      <ConfirmDialog
        open={pendingDelete !== null}
        title={`Xoá xe ${pendingDelete?.plate_number ?? ""}?`}
        description="Xe sẽ bị xoá khỏi đội xe. Các chuyến đã hoàn thành hoặc đã huỷ liên quan đến xe này vẫn được giữ lại, chỉ mất liên kết với xe. Nếu xe đang chạy chuyến, thao tác này sẽ bị từ chối."
        confirmLabel="Xoá xe"
        loading={deleteVehicle.isPending}
        onConfirm={() => pendingDelete && deleteVehicle.mutate(pendingDelete.id)}
        onCancel={() => setPendingDelete(null)}
      />

      <SlideOver
        open={formOpen}
        title="Thêm xe mới"
        description="Biển số và số chỗ ngồi của xe trong đội."
        onClose={() => setFormOpen(false)}
      >
        <VehicleForm
          onCreated={() => {
            refresh();
            setFormOpen(false);
          }}
        />
      </SlideOver>
    </AppShell>
  );
}

function VehicleRow({
  vehicle,
  drivers,
  onStatusChange,
  onDriverChange,
  onDelete,
}: {
  vehicle: VehicleOut;
  drivers: { id: string; full_name: string }[];
  onStatusChange: (s: VehicleStatus) => void;
  onDriverChange: (driverId: string | null) => void;
  onDelete: () => void;
}) {
  const status = VEHICLE_STATUS[vehicle.status];
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold tnum">
              {vehicle.plate_number}
            </span>
            <Badge tone={status.tone}>{status.label}</Badge>
          </div>
          <p className="text-xs text-[var(--text-tertiary)] mt-0.5">
            {vehicle.label ?? "Chưa đặt tên"} · {vehicle.seat_capacity} chỗ
          </p>
        </div>
        <Button
          variant="danger-subtle"
          size="sm"
          onClick={onDelete}
          aria-label={`Xoá xe ${vehicle.plate_number}`}
          className="!px-1.5 shrink-0"
        >
          <Trash2 size={14} aria-hidden="true" />
        </Button>
      </div>

      <div className="grid sm:grid-cols-2 gap-3">
        <label className="block">
          <span className="block text-[11px] text-[var(--text-tertiary)] mb-1">
            Trạng thái
          </span>
          <select
            value={vehicle.status}
            onChange={(e) => onStatusChange(e.target.value as VehicleStatus)}
            className="w-full h-8 px-2 text-xs rounded-[var(--radius)] bg-[var(--surface)] border border-[var(--border-strong)] hover:border-[var(--text-tertiary)] focus:border-[var(--border-focus)] transition-colors"
          >
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {VEHICLE_STATUS[s].label}
              </option>
            ))}
          </select>
        </label>

        <label className="block">
          <span className="block text-[11px] text-[var(--text-tertiary)] mb-1">
            Tài xế mặc định
          </span>
          <select
            value={vehicle.default_driver_id ?? ""}
            onChange={(e) => onDriverChange(e.target.value || null)}
            className="w-full h-8 px-2 text-xs rounded-[var(--radius)] bg-[var(--surface)] border border-[var(--border-strong)] hover:border-[var(--text-tertiary)] focus:border-[var(--border-focus)] transition-colors"
          >
            <option value="">Chưa gán</option>
            {drivers.map((d) => (
              <option key={d.id} value={d.id}>
                {d.full_name}
              </option>
            ))}
          </select>
        </label>
      </div>
    </Card>
  );
}

function VehicleForm({ onCreated }: { onCreated: () => void }) {
  const toast = useToast();
  const [plate, setPlate] = useState("");
  const [label, setLabel] = useState("");
  const [seats, setSeats] = useState(4);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const created = await api.vehicles.create({
        plate_number: plate.trim(),
        label: label.trim() || null,
        seat_capacity: seats,
      });
      toast(`Đã thêm xe ${created.plate_number}.`, "success");
      setPlate("");
      setLabel("");
      setSeats(4);
      onCreated();
    } catch (err: any) {
      setError(getErrorMessage(err, "Không thêm được xe."));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      <Field
        label="Biển số xe"
        value={plate}
        onChange={(e) => setPlate(e.target.value)}
        placeholder="98A-12345"
        error={error ?? undefined}
        required
      />
      <Field
        label="Tên gọi"
        value={label}
        onChange={(e) => setLabel(e.target.value)}
        placeholder="Xe 1"
        hint="Tên ngắn để điều phối viên dễ nhận ra."
      />
      <Field
        label="Số chỗ cho khách"
        type="number"
        min={1}
        max={16}
        value={seats}
        onChange={(e) => setSeats(Number(e.target.value))}
        hint="Không tính ghế lái."
        required
        className="max-w-[12rem]"
      />
      <div className="flex justify-end pt-1">
        <Button type="submit" variant="primary" size="lg" loading={submitting}>
          Thêm xe
        </Button>
      </div>
    </form>
  );
}
