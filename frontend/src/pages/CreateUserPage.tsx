import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, Car, Headphones, ShieldCheck } from "lucide-react";
import { api } from "../lib/api";
import type { UserRole } from "../types";
import AppShell from "../components/layout/AppShell";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import Field from "../components/ui/Field";
import { useToast } from "../components/ui/Toast";
import { getErrorMessage } from "../lib/errors";

const ROLES: {
  value: UserRole;
  label: string;
  description: string;
  icon: React.ReactNode;
}[] = [
  {
    value: "dispatcher",
    label: "Điều phối viên",
    description: "Thêm khách, ghép chuyến, giao xe cho tài xế",
    icon: <Headphones size={16} aria-hidden="true" />,
  },
  {
    value: "driver",
    label: "Tài xế",
    description: "Chỉ xem chuyến được giao cho mình",
    icon: <Car size={16} aria-hidden="true" />,
  },
  {
    value: "admin",
    label: "Quản trị",
    description: "Toàn quyền, kể cả tạo tài khoản nhân viên",
    icon: <ShieldCheck size={16} aria-hidden="true" />,
  },
];

export default function CreateUserPage() {
  const toast = useToast();
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<UserRole>("dispatcher");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const created = await api.auth.register({
        full_name: fullName.trim(),
        phone: phone.trim(),
        password,
        role,
      });
      toast(`Đã tạo tài khoản cho ${created.full_name}.`, "success");
      setFullName("");
      setPhone("");
      setPassword("");
      setRole("dispatcher");
    } catch (err: any) {
      setError(getErrorMessage(err, "Không tạo được tài khoản."));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AppShell
      title="Thêm nhân viên"
      subtitle="Tạo tài khoản đăng nhập cho điều phối viên, tài xế hoặc quản trị viên."
      width="narrow"
      actions={
        <Link to="/">
          <Button variant="ghost" iconLeft={<ArrowLeft size={15} aria-hidden="true" />}>
            Về bảng điều phối
          </Button>
        </Link>
      }
    >
      <Card className="p-5 sm:p-6">
        <form onSubmit={handleSubmit} className="space-y-5" noValidate>
          <div className="grid sm:grid-cols-2 gap-4">
            <Field
              label="Họ và tên"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              required
            />
            <Field
              label="Số điện thoại"
              type="tel"
              inputMode="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              hint="Dùng để đăng nhập"
              required
            />
          </div>

          <Field
            label="Mật khẩu tạm thời"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={8}
            hint="Tối thiểu 8 ký tự. Nhân viên nên đổi sau lần đăng nhập đầu."
            error={error ?? undefined}
            required
          />

          <fieldset className="border-0 p-0 m-0">
            <legend className="text-[12px] font-medium mb-2 text-[var(--text-secondary)]">
              Vai trò
            </legend>
            <div className="space-y-2">
              {ROLES.map((r) => (
                <button
                  key={r.value}
                  type="button"
                  onClick={() => setRole(r.value)}
                  aria-pressed={role === r.value}
                  className={[
                    "w-full text-left p-3 rounded-[var(--radius-md)] border flex items-start gap-3",
                    "transition-all duration-[var(--duration-fast)]",
                    role === r.value
                      ? "border-[var(--brand-blue)] bg-[var(--brand-blue-subtle)]"
                      : "border-[var(--border-strong)] bg-[var(--surface)] hover:border-[var(--text-tertiary)]",
                  ].join(" ")}
                >
                  <span
                    className={
                      role === r.value
                        ? "text-[var(--brand-blue)] mt-0.5"
                        : "text-[var(--text-tertiary)] mt-0.5"
                    }
                  >
                    {r.icon}
                  </span>
                  <span>
                    <span className="block text-sm font-medium">{r.label}</span>
                    <span className="block text-xs text-[var(--text-tertiary)] mt-0.5">
                      {r.description}
                    </span>
                  </span>
                </button>
              ))}
            </div>
          </fieldset>

          <div className="flex justify-end pt-1">
            <Button type="submit" variant="primary" size="lg" loading={submitting}>
              Tạo tài khoản
            </Button>
          </div>
        </form>
      </Card>
    </AppShell>
  );
}
