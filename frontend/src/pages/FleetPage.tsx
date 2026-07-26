import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Car, Home, MapPin, Plus, Trash2 } from "lucide-react";
import { api } from "../lib/api";
import { VEHICLE_STATUS, placeFromLatLng } from "../lib/format";
import type { VehicleOut, VehicleStatus } from "../types";
import AppShell from "../components/layout/AppShell";
import Badge from "../components/ui/Badge";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import ConfirmDialog from "../components/ui/ConfirmDialog";
import EmptyState from "../components/ui/EmptyState";
import Field from "../components/ui/Field";
import QueryState from "../components/ui/QueryState";
import Select from "../components/ui/Select";
import Skeleton from "../components/ui/Skeleton";
import SlideOver from "../components/ui/SlideOver";
import { useToast } from "../components/ui/Toast";
import { getErrorMessage } from "../lib/errors";

// `returning` is deliberately absent: it owns paired columns
// (return_requested_at / requested_by) that only the return endpoints
// maintain, so setting it from a plain status dropdown would produce a
// car that is "returning" with no request behind it — exactly the
// inconsistent state this workflow exists to avoid. Use the call-home
// button instead.
const STATUS_OPTIONS: VehicleStatus[] = [
  "available",
  "assigned",
  "on_trip",
  "maintenance",
  "offline",
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

  const callHome = useMutation({
    mutationFn: (id: string) => api.vehicleReturn.request(id),
    onSuccess: (v) => {
      toast(`Đã yêu cầu ${v.plate_number} quay về Bắc Giang.`, "success");
      refresh();
    },
    // The server refuses a car that's busy or already home, and its
    // message says which — surface that rather than a generic failure.
    onError: (err: any) =>
      toast(getErrorMessage(err, "Không gọi được xe về."), "error"),
  });

  const cancelReturn = useMutation({
    mutationFn: (id: string) => api.vehicleReturn.cancel(id),
    onSuccess: (v) => {
      toast(`Đã huỷ yêu cầu quay về cho ${v.plate_number}.`, "success");
      refresh();
    },
    onError: (err: any) =>
      toast(getErrorMessage(err, "Không huỷ được yêu cầu."), "error"),
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
      <QueryState
        query={vehiclesQuery}
        errorTitle="Không tải được đội xe"
        skeleton={
          <div className="space-y-3">
            <Skeleton className="h-20 w-full rounded-md" count={3} />
          </div>
        }
        empty={
          /* The dispatch engine will not seal a pool it cannot put a real
             car under, so an empty fleet means nothing ever departs. Say
             that plainly rather than letting it look like a bug. */
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
        }
      >
        {(vehicleList) => (
          <div className="space-y-3">
            {vehicleList.map((v) => (
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
                onRequestReturn={() => callHome.mutate(v.id)}
                onCancelReturn={() => cancelReturn.mutate(v.id)}
                statusPending={
                  updateStatus.isPending && updateStatus.variables?.id === v.id
                }
                driverPending={
                  assignDriver.isPending && assignDriver.variables?.id === v.id
                }
                returnPending={
                  (callHome.isPending && callHome.variables === v.id) ||
                  (cancelReturn.isPending && cancelReturn.variables === v.id)
                }
              />
            ))}
          </div>
        )}
      </QueryState>

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
  onRequestReturn,
  onCancelReturn,
  statusPending = false,
  driverPending = false,
  returnPending = false,
}: {
  vehicle: VehicleOut;
  drivers: { id: string; full_name: string }[];
  onStatusChange: (s: VehicleStatus) => void;
  onDriverChange: (driverId: string | null) => void;
  onDelete: () => void;
  onRequestReturn: () => void;
  onCancelReturn: () => void;
  statusPending?: boolean;
  driverPending?: boolean;
  returnPending?: boolean;
}) {
  const status = VEHICLE_STATUS[vehicle.status];

  const place = placeFromLatLng(
    vehicle.last_location_lat,
    vehicle.last_location_lng
  );
  const atBase = place === "bac_giang";
  const locationLabel = place
    ? `Đang ở ${place === "ha_noi" ? "Hà Nội" : "Bắc Giang"}`
    : "Chưa rõ vị trí";

  // Only offer to call a car home when doing so would actually be
  // accepted: a car that's busy, already home, or of unknown position
  // would be refused by the server anyway. Showing a button that only
  // ever produces an error is worse than showing none.
  const canCallHome = vehicle.status === "available" && place !== null && !atBase;

  return (
    <Card
      className="p-4"
      // Neutral (offline) gets no rail — same "nothing to flag" rule
      // the dispatch stats use, rather than inventing a grey accent.
      accent={status.tone !== "neutral" ? status.tone : undefined}
    >
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-base font-semibold tnum">
              {vehicle.plate_number}
            </span>
            <Badge tone={status.tone}>{status.label}</Badge>
          </div>
          <p className="text-xs text-faint mt-0.5">
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

      {/* Where the car actually is, and whether it needs to come home.
          Home base is Bắc Giang for every vehicle; a car that finished
          its last run in Hà Nội has to get back before the next
          morning, or dispatch starts the day from a stale position. */}
      <div className="mb-3">
        {vehicle.status === "returning" ? (
          <div className="flex flex-wrap items-center gap-2 rounded border border-line bg-sunken px-3 py-2">
            <Home size={14} aria-hidden="true" className="text-faint shrink-0" />
            <span className="text-xs text-muted flex-1 min-w-0">
              Đã yêu cầu xe quay về Bắc Giang. Chờ tài xế xác nhận đã về.
            </span>
            <Button
              variant="ghost"
              size="sm"
              loading={returnPending}
              onClick={onCancelReturn}
            >
              Huỷ yêu cầu
            </Button>
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-2">
            <MapPin size={14} aria-hidden="true" className="text-faint shrink-0" />
            <span className="text-xs text-muted flex-1 min-w-0">
              {locationLabel}
            </span>
            {canCallHome && (
              <Button
                variant="secondary"
                size="sm"
                iconLeft={<Home size={14} aria-hidden="true" />}
                loading={returnPending}
                onClick={onRequestReturn}
              >
                Gọi xe về
              </Button>
            )}
          </div>
        )}
      </div>

      <div className="grid sm:grid-cols-2 gap-3">
        <Select
          label="Trạng thái"
          accessibleName={`Trạng thái xe ${vehicle.plate_number}`}
          value={vehicle.status}
          pending={statusPending}
          // A returning car's status isn't in the option list, so the
          // control would silently misrepresent it. Locked while the
          // return is outstanding; cancel it to change status.
          disabled={vehicle.status === "returning"}
          options={STATUS_OPTIONS.map((s) => ({
            value: s,
            label: VEHICLE_STATUS[s].label,
          }))}
          onChange={(s) => onStatusChange(s as VehicleStatus)}
        />

        <Select
          label="Tài xế mặc định"
          accessibleName={`Tài xế mặc định cho xe ${vehicle.plate_number}`}
          value={vehicle.default_driver_id ?? ""}
          placeholder="Chưa gán"
          pending={driverPending}
          options={[
            { value: "", label: "Chưa gán" },
            ...drivers.map((d) => ({ value: d.id, label: d.full_name })),
          ]}
          onChange={(driverId) => onDriverChange(driverId || null)}
        />
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
