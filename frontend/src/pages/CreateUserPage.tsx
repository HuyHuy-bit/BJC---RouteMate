import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import type { UserRole } from "../types";

const ROLE_LABEL: Record<UserRole, string> = {
  admin: "Quản trị viên",
  dispatcher: "Điều phối viên",
  driver: "Tài xế",
};

export default function CreateUserPage() {
  const navigate = useNavigate();
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<UserRole>("dispatcher");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    setSubmitting(true);
    try {
      const created = await api.auth.register({
        full_name: fullName.trim(),
        phone: phone.trim(),
        password,
        role,
      });
      setSuccess(`Đã tạo tài khoản cho ${created.full_name} (${ROLE_LABEL[created.role]}).`);
      setFullName("");
      setPhone("");
      setPassword("");
      setRole("dispatcher");
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Không thể tạo tài khoản");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen" style={{ background: "var(--paper)" }}>
      <div className="max-w-md mx-auto px-6 py-8">
        <button
          onClick={() => navigate("/")}
          className="text-xs underline mb-4"
          style={{ color: "var(--mute)" }}
        >
          ← Quay lại bảng điều phối
        </button>

        <div
          className="text-xs tracking-widest mb-1"
          style={{ color: "var(--amber)", fontFamily: "'JetBrains Mono', monospace" }}
        >
          QUẢN TRỊ
        </div>
        <h1
          className="text-2xl font-bold mb-6"
          style={{ fontFamily: "'Sora', sans-serif" }}
        >
          Tạo tài khoản nhân viên
        </h1>

        <form
          onSubmit={handleSubmit}
          className="bg-white border rounded p-6 space-y-4"
          style={{ borderColor: "var(--line)" }}
        >
          <div>
            <label className="block text-xs mb-1" style={{ color: "var(--mute)" }}>
              Họ tên
            </label>
            <input
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="w-full border rounded px-3 py-2 text-sm"
              style={{ borderColor: "var(--line)" }}
              required
            />
          </div>

          <div>
            <label className="block text-xs mb-1" style={{ color: "var(--mute)" }}>
              Số điện thoại
            </label>
            <input
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              className="w-full border rounded px-3 py-2 text-sm"
              style={{ borderColor: "var(--line)" }}
              required
            />
          </div>

          <div>
            <label className="block text-xs mb-1" style={{ color: "var(--mute)" }}>
              Mật khẩu tạm thời
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full border rounded px-3 py-2 text-sm"
              style={{ borderColor: "var(--line)" }}
              minLength={8}
              required
            />
          </div>

          <div>
            <label className="block text-xs mb-1" style={{ color: "var(--mute)" }}>
              Vai trò
            </label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as UserRole)}
              className="w-full border rounded px-3 py-2 text-sm"
              style={{ borderColor: "var(--line)" }}
            >
              <option value="dispatcher">Điều phối viên</option>
              <option value="driver">Tài xế</option>
              <option value="admin">Quản trị viên</option>
            </select>
          </div>

          {error && (
            <div className="text-sm" style={{ color: "var(--coral)" }}>
              {error}
            </div>
          )}
          {success && (
            <div className="text-sm" style={{ color: "var(--teal)" }}>
              ✓ {success}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded py-2 text-sm font-semibold text-white"
            style={{ background: "var(--ink)", opacity: submitting ? 0.6 : 1 }}
          >
            {submitting ? "Đang tạo..." : "Tạo tài khoản"}
          </button>
        </form>
      </div>
    </div>
  );
}
