import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Phone } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import Button from "../components/ui/Button";
import Field from "../components/ui/Field";

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
      navigate(me.role === "driver" ? "/driver" : "/", { replace: true });
    } catch {
      setError("Số điện thoại hoặc mật khẩu không đúng.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-[1.1fr_1fr]">
      {/* Brand panel — the fleet photo is the most characteristic thing
          this company owns, so it leads. Hidden on mobile where vertical
          space is scarce and the form is the only job. */}
      <aside className="relative hidden lg:block overflow-hidden bg-photo-ground">
        <img
          src="/thanh-cong-fleet.jpg"
          alt=""
          className="absolute inset-0 w-full h-full object-cover opacity-45"
        />
        <div
          className="absolute inset-0"
          style={{
            background:
              "linear-gradient(135deg, rgba(16,23,40,0.92) 0%, rgba(27,95,168,0.72) 55%, rgba(214,51,31,0.55) 100%)",
          }}
        />
        <div className="relative h-full flex flex-col justify-between p-10 xl:p-14 text-white">
          <img
            src="/bjc-logo.jpg"
            alt="BJC Group"
            className="w-12 h-12 rounded-md object-cover"
          />
          <div>
            <p className="text-2xs tracking-[0.18em] text-white/70 mb-3 font-mono">
              HỆ THỐNG ĐIỀU PHỐI NỘI BỘ
            </p>
            <h1 className="text-3xl xl:text-4xl font-semibold leading-[1.08] max-w-[14ch]">
              Bắc Giang
              <br />
              <span className="text-white/55">⇄</span> Hà Nội
            </h1>
            <p className="text-base text-white/75 mt-5 max-w-[42ch] leading-relaxed">
              Ghép khách theo quãng đường thực tế, đón và trả tận nơi.
            </p>
          </div>
          <div className="flex items-center gap-2 text-base text-white/80">
            <Phone size={14} aria-hidden="true" />
            <span>Hotline 1900 8293</span>
          </div>
        </div>
      </aside>

      {/* Form panel */}
      <div className="flex items-center justify-center p-6 sm:p-10 bg-canvas">
        <div className="w-full max-w-[380px] animate-slide-up">
          <div className="lg:hidden flex items-center gap-2.5 mb-8">
            <img
              src="/bjc-logo.jpg"
              alt=""
              className="w-9 h-9 rounded object-cover"
            />
            <div>
              <div className="text-base font-semibold font-display">
                Thành Công Limousine
              </div>
              <div className="text-2xs text-faint tracking-wide">
                BJC GROUP
              </div>
            </div>
          </div>

          <h2 className="text-2xl font-semibold text-ink">Đăng nhập</h2>
          <p className="text-base text-faint mt-1.5 mb-7">
            Dành cho nhân viên điều phối và tài xế.
          </p>

          <form onSubmit={handleSubmit} noValidate>
            <div className="space-y-4">
              <Field
                label="Số điện thoại"
                type="tel"
                inputMode="tel"
                autoComplete="username"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                required
              />
              <Field
                label="Mật khẩu"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                error={error ?? undefined}
                required
              />
            </div>

            <Button
              type="submit"
              variant="primary"
              size="lg"
              fullWidth
              loading={submitting}
              className="mt-6"
            >
              {submitting ? "Đang đăng nhập" : "Đăng nhập"}
            </Button>
          </form>

          <p className="text-xs text-faint mt-8 text-center lg:hidden">
            Hotline 1900 8293
          </p>
        </div>
      </div>
    </div>
  );
}
