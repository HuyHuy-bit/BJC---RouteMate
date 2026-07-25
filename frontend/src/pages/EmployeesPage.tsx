import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Phone, Power, Trash2, UserPlus, Users } from "lucide-react";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import type { UserOut } from "../types";
import { ROLE_LABEL } from "../lib/format";
import { getErrorMessage } from "../lib/errors";
import AppShell from "../components/layout/AppShell";
import Badge from "../components/ui/Badge";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import ConfirmDialog from "../components/ui/ConfirmDialog";
import EmptyState from "../components/ui/EmptyState";
import QueryState from "../components/ui/QueryState";
import Skeleton from "../components/ui/Skeleton";
import { useToast } from "../components/ui/Toast";

const ROLE_ORDER = ["admin", "dispatcher", "driver"] as const;

export default function EmployeesPage() {
  const toast = useToast();
  const { user: currentUser } = useAuth();
  const queryClient = useQueryClient();
  const [pendingDeactivate, setPendingDeactivate] = useState<UserOut | null>(null);
  const [pendingDelete, setPendingDelete] = useState<UserOut | null>(null);

  const usersQuery = useQuery({
    queryKey: ["all-users"],
    queryFn: () => api.users.list(),
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["all-users"] });

  const toggleActive = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      api.users.update(id, { is_active }),
    onSuccess: (u) => {
      toast(
        u.is_active
          ? `Đã mở lại tài khoản ${u.full_name}.`
          : `Đã khoá tài khoản ${u.full_name}.`,
        "success"
      );
      setPendingDeactivate(null);
      refresh();
    },
    onError: (err) => {
      toast(getErrorMessage(err, "Không cập nhật được tài khoản."), "error");
      setPendingDeactivate(null);
    },
  });

  const deleteUser = useMutation({
    mutationFn: (id: string) => api.users.delete(id),
    onSuccess: () => {
      toast(`Đã xoá tài khoản ${pendingDelete?.full_name}.`, "success");
      setPendingDelete(null);
      refresh();
    },
    onError: (err) => {
      toast(getErrorMessage(err, "Không xoá được tài khoản."), "error");
      setPendingDelete(null);
    },
  });

  const users = usersQuery.data ?? [];
  const grouped = useMemo(() => {
    const by: Record<string, UserOut[]> = { admin: [], dispatcher: [], driver: [] };
    for (const u of users) (by[u.role] ??= []).push(u);
    return by;
  }, [users]);

  return (
    <AppShell
      title="Nhân viên"
      subtitle={`${users.length} tài khoản`}
      width="narrow"
      actions={
        <>
          <Link to="/">
            <Button variant="ghost" iconLeft={<ArrowLeft size={15} aria-hidden="true" />}>
              Về bảng điều phối
            </Button>
          </Link>
          <Link to="/admin/users/new">
            <Button variant="primary" iconLeft={<UserPlus size={15} aria-hidden="true" />}>
              Thêm nhân viên
            </Button>
          </Link>
        </>
      }
    >
      <QueryState
        query={usersQuery}
        errorTitle="Không tải được danh sách nhân viên"
        skeleton={
          <div className="space-y-2">
            <Skeleton className="h-16 w-full rounded-lg" count={5} />
          </div>
        }
        empty={
          <Card>
            <EmptyState
              icon={<Users size={18} aria-hidden="true" />}
              title="Chưa có nhân viên nào"
              description="Thêm tài khoản cho điều phối viên, tài xế hoặc quản trị viên khác."
            />
          </Card>
        }
      >
        {() => (
      <div className="space-y-6">
        {ROLE_ORDER.map((role) => {
          const list = grouped[role];
          if (!list || list.length === 0) return null;
          return (
            <section key={role}>
              <h2 className="text-xs font-medium text-faint mb-2 tracking-wide uppercase">
                {ROLE_LABEL[role]}
                <span className="ml-1.5 tnum">({list.length})</span>
              </h2>
              <div className="space-y-2">
                {list.map((u) => {
                  const isSelf = u.id === currentUser?.id;
                  return (
                    <Card
                      key={u.id}
                      className="p-3 flex items-center justify-between gap-3"
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-base font-medium truncate">
                            {u.full_name}
                          </span>
                          {isSelf && <Badge tone="info">Bạn</Badge>}
                          {!u.is_active && <Badge tone="danger">Đã khoá</Badge>}
                        </div>
                        <p className="text-xs text-faint mt-0.5 flex items-center gap-1 tnum">
                          <Phone size={11} aria-hidden="true" />
                          {u.phone}
                        </p>
                      </div>

                      <div className="flex items-center gap-1.5 shrink-0">
                        <Button
                          variant={u.is_active ? "danger-subtle" : "secondary"}
                          size="sm"
                          iconLeft={<Power size={13} aria-hidden="true" />}
                          disabled={isSelf}
                          title={
                            isSelf
                              ? "Không thể tự khoá tài khoản của chính mình"
                              : undefined
                          }
                          onClick={() => {
                            if (u.is_active) {
                              setPendingDeactivate(u);
                            } else {
                              toggleActive.mutate({ id: u.id, is_active: true });
                            }
                          }}
                        >
                          {u.is_active ? "Khoá" : "Mở lại"}
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={isSelf}
                          title={
                            isSelf
                              ? "Không thể tự xoá tài khoản của chính mình"
                              : "Xoá vĩnh viễn"
                          }
                          aria-label={`Xoá ${u.full_name}`}
                          onClick={() => setPendingDelete(u)}
                          className="!px-1.5 !text-faint hover:!text-danger"
                        >
                          <Trash2 size={13} aria-hidden="true" />
                        </Button>
                      </div>
                    </Card>
                  );
                })}
              </div>
            </section>
          );
        })}
      </div>
        )}
      </QueryState>

      <ConfirmDialog
        open={pendingDeactivate !== null}
        title={`Khoá tài khoản ${pendingDeactivate?.full_name ?? ""}?`}
        description="Nhân viên này sẽ không thể đăng nhập cho đến khi được mở lại. Lịch sử chuyến và dữ liệu liên quan vẫn được giữ nguyên."
        confirmLabel="Khoá tài khoản"
        loading={toggleActive.isPending}
        onConfirm={() =>
          pendingDeactivate &&
          toggleActive.mutate({ id: pendingDeactivate.id, is_active: false })
        }
        onCancel={() => setPendingDeactivate(null)}
      />

      <ConfirmDialog
        open={pendingDelete !== null}
        title={`Xoá vĩnh viễn ${pendingDelete?.full_name ?? ""}?`}
        description="Chỉ xoá được nếu nhân viên này không đang điều hành và chưa chạy chuyến nào trong 3 ngày qua — hệ thống sẽ từ chối nếu không đủ điều kiện. Hành động này không thể hoàn tác; nếu chỉ muốn tạm ngừng, hãy dùng nút Khoá."
        confirmLabel="Xoá vĩnh viễn"
        loading={deleteUser.isPending}
        onConfirm={() => pendingDelete && deleteUser.mutate(pendingDelete.id)}
        onCancel={() => setPendingDelete(null)}
      />
    </AppShell>
  );
}
