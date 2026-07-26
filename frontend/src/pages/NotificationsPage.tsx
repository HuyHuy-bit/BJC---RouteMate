import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Check, Copy, MessageSquareText } from "lucide-react";
import { api } from "../lib/api";
import type { NotificationOut } from "../types";
import AppShell from "../components/layout/AppShell";
import Badge from "../components/ui/Badge";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import EmptyState from "../components/ui/EmptyState";
import QueryState from "../components/ui/QueryState";
import Skeleton from "../components/ui/Skeleton";
import { fmtDateTime } from "../lib/format";

const EVENT_LABEL: Record<string, string> = {
  sealed: "Xếp xe",
  driver_assigned: "Gán tài xế",
  cancelled: "Huỷ chuyến",
};

export default function NotificationsPage() {
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const notificationsQuery = useQuery({
    queryKey: ["notifications"],
    queryFn: () => api.notifications.list(),
    refetchInterval: 30_000,
  });

  const copy = async (n: NotificationOut) => {
    try {
      await navigator.clipboard.writeText(n.message);
      setCopiedId(n.id);
      setTimeout(() => setCopiedId((id) => (id === n.id ? null : id)), 2000);
    } catch {
      // Clipboard API can fail without permission/HTTPS — the message is
      // still fully visible on screen either way, so this fails quietly.
    }
  };

  return (
    <AppShell
      title="Thông báo khách hàng"
      subtitle="Chưa kết nối SMS/Zalo — sao chép và gửi thủ công cho khách"
      width="narrow"
      actions={
        <Link to="/">
          <Button variant="ghost" iconLeft={<ArrowLeft size={15} aria-hidden="true" />}>
            Về bảng điều phối
          </Button>
        </Link>
      }
    >
      <QueryState
        query={notificationsQuery}
        errorTitle="Không tải được thông báo"
        skeleton={
          <div className="space-y-3">
            <Skeleton className="h-24 w-full rounded-md" count={4} />
          </div>
        }
        empty={
          <Card>
            <EmptyState
              icon={<MessageSquareText size={18} aria-hidden="true" />}
              title="Chưa có thông báo nào"
              description="Khi một chuyến được xếp xe hoặc gán tài xế, tin nhắn dành cho khách sẽ xuất hiện ở đây."
            />
          </Card>
        }
      >
        {(notes) => (
          <div className="space-y-2">
            {notes.map((n) => (
          <Card key={n.id} className="p-4">
            <div className="flex items-start justify-between gap-3 mb-2">
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-base font-medium">{n.customer_name}</span>
                  <Badge tone="neutral">{EVENT_LABEL[n.event] ?? n.event}</Badge>
                </div>
                <p className="text-xs text-faint tnum mt-0.5">
                  {n.customer_phone} · {fmtDateTime(n.created_at)}
                </p>
              </div>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => copy(n)}
                iconLeft={
                  copiedId === n.id ? (
                    <Check size={13} aria-hidden="true" />
                  ) : (
                    <Copy size={13} aria-hidden="true" />
                  )
                }
                className="shrink-0"
              >
                {copiedId === n.id ? "Đã chép" : "Sao chép"}
              </Button>
            </div>
            <p className="text-base text-muted leading-relaxed bg-sunken rounded p-3">
              {n.message}
            </p>
          </Card>
            ))}
          </div>
        )}
      </QueryState>
    </AppShell>
  );
}
