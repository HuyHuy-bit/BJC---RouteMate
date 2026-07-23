import { type ReactNode } from "react";
import { Link } from "react-router-dom";
import { Car, LogOut, UserPlus } from "lucide-react";
import { useAuth } from "../../context/AuthContext";
import Button from "../ui/Button";

const ROLE_LABEL: Record<string, string> = {
  admin: "Quản trị",
  dispatcher: "Điều phối",
  driver: "Tài xế",
};

/**
 * One shell for every authenticated screen. Previously each page
 * re-implemented its own header markup, so the logo, spacing, and
 * logout button drifted apart between them.
 */
export default function AppShell({
  title,
  subtitle,
  actions,
  children,
  width = "wide",
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
  width?: "wide" | "narrow";
}) {
  const { user, logout } = useAuth();

  return (
    <div className="min-h-screen bg-[var(--bg)]">
      <header className="sticky top-0 z-40 bg-[var(--surface)]/85 backdrop-blur-md border-b border-[var(--border)]">
        <div
          className={`mx-auto px-4 sm:px-6 ${
            width === "wide" ? "max-w-[1400px]" : "max-w-3xl"
          }`}
        >
          <div className="flex items-center justify-between h-14 gap-4">
            <Link to="/" className="flex items-center gap-2.5 min-w-0 shrink-0">
              <img
                src="/bjc-logo.jpg"
                alt=""
                className="w-8 h-8 rounded-[var(--radius)] object-cover shrink-0"
              />
              <div className="min-w-0 hidden sm:block">
                <div className="text-[13px] font-semibold leading-tight truncate font-[family-name:var(--font-display)]">
                  Thành Công Limousine
                </div>
                <div className="text-[10px] text-[var(--text-tertiary)] leading-tight tracking-wide">
                  BJC GROUP
                </div>
              </div>
            </Link>

            <div className="flex items-center gap-2 shrink-0">
              {(user?.role === "admin" || user?.role === "dispatcher") && (
                <Link to="/fleet" aria-label="Đội xe">
                  <Button
                    variant="ghost"
                    size="sm"
                    iconLeft={<Car size={14} aria-hidden="true" />}
                    className="!px-2 sm:!px-2.5"
                  >
                    {/* Label collapses on narrow screens rather than the
                        whole control disappearing — a button you cannot
                        reach on a phone may as well not exist. */}
                    <span className="hidden sm:inline">Đội xe</span>
                  </Button>
                </Link>
              )}

              {user?.role === "admin" && (
                <Link to="/admin/users/new" aria-label="Thêm nhân viên">
                  <Button
                    variant="ghost"
                    size="sm"
                    iconLeft={<UserPlus size={14} aria-hidden="true" />}
                    className="!px-2 sm:!px-2.5"
                  >
                    <span className="hidden sm:inline">Thêm nhân viên</span>
                  </Button>
                </Link>
              )}

              <div className="hidden md:flex flex-col items-end leading-tight mr-1">
                <span className="text-xs font-medium text-[var(--text)]">
                  {user?.full_name}
                </span>
                <span className="text-[10px] text-[var(--text-tertiary)]">
                  {ROLE_LABEL[user?.role ?? ""]}
                </span>
              </div>

              <Button
                variant="ghost"
                size="sm"
                onClick={logout}
                aria-label="Đăng xuất"
                className="!px-2"
              >
                <LogOut size={15} aria-hidden="true" />
              </Button>
            </div>
          </div>
        </div>
      </header>

      <main
        className={`mx-auto px-4 sm:px-6 py-6 ${
          width === "wide" ? "max-w-[1400px]" : "max-w-3xl"
        }`}
      >
        <div className="flex flex-wrap items-end justify-between gap-3 mb-6">
          <div>
            <h1 className="text-[22px] sm:text-[26px] font-semibold text-[var(--text)]">
              {title}
            </h1>
            {subtitle && (
              <p className="text-sm text-[var(--text-tertiary)] mt-1">{subtitle}</p>
            )}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
        {children}
      </main>
    </div>
  );
}
