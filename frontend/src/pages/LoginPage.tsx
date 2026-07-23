import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(phone, password);
      navigate("/");
    } catch {
      setError("Sai số điện thoại hoặc mật khẩu");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center">
      <form
        onSubmit={handleSubmit}
        className="bg-white border rounded p-8 w-full max-w-sm"
        style={{ borderColor: "var(--line)" }}
      >
        <div
          className="text-xs tracking-widest mb-1"
          style={{
            color: "var(--amber)",
            fontFamily: "'JetBrains Mono', monospace",
          }}
        >
          XE GHÉP
        </div>
        <h1
          className="text-2xl font-semibold mb-6"
          style={{ fontFamily: "'Space Grotesk', sans-serif" }}
        >
          Đăng nhập
        </h1>

        <label className="block text-sm mb-1" style={{ color: "var(--mute)" }}>
          Số điện thoại
        </label>
        <input
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          className="w-full border rounded px-3 py-2 mb-4 text-sm"
          style={{ borderColor: "var(--line)" }}
          autoComplete="username"
        />

        <label className="block text-sm mb-1" style={{ color: "var(--mute)" }}>
          Mật khẩu
        </label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full border rounded px-3 py-2 mb-4 text-sm"
          style={{ borderColor: "var(--line)" }}
          autoComplete="current-password"
        />

        {error && (
          <div className="text-sm mb-4" style={{ color: "var(--coral)" }}>
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded py-2 text-sm font-semibold text-white"
          style={{ background: "var(--ink)", opacity: submitting ? 0.6 : 1 }}
        >
          {submitting ? "Đang đăng nhập..." : "Đăng nhập"}
        </button>
      </form>
    </div>
  );
}
