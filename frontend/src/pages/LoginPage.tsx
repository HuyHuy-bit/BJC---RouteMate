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
      const me = await login(phone, password);
      navigate(me.role === "driver" ? "/driver" : "/");
    } catch {
      setError("Sai số điện thoại hoặc mật khẩu");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="min-h-screen flex items-center justify-center"
      style={{ background: "var(--brand-blue)" }}
    >
      <form
        onSubmit={handleSubmit}
        className="bg-white border rounded p-8 w-full max-w-sm"
        style={{ borderColor: "var(--line)" }}
      >
        <div className="flex items-center gap-3 mb-5">
          <img
            src="/bjc-logo.jpg"
            alt="BJC Group"
            className="w-12 h-12 rounded-full object-cover"
          />
          <div>
            <div
              className="text-sm font-bold leading-tight"
              style={{ color: "var(--coral)", fontFamily: "'Sora', sans-serif" }}
            >
              THÀNH CÔNG LIMOUSINE
            </div>
            <div
              className="text-xs"
              style={{ color: "var(--mute)", fontFamily: "'JetBrains Mono', monospace" }}
            >
              BJC GROUP · BẮC GIANG
            </div>
          </div>
        </div>

        <h1
          className="text-2xl font-semibold mb-6"
          style={{ fontFamily: "'Sora', sans-serif" }}
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
          style={{ background: "var(--amber)", opacity: submitting ? 0.6 : 1 }}
        >
          {submitting ? "Đang đăng nhập..." : "Đăng nhập"}
        </button>

        <div
          className="text-center text-xs mt-5 pt-4 border-t"
          style={{ color: "var(--mute)", borderColor: "var(--line)" }}
        >
          Hotline: <span style={{ color: "var(--coral)", fontWeight: 600 }}>1900 8293</span>
        </div>
      </form>
    </div>
  );
}
