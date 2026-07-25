import { useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { Car, History, LogOut, Moon, Sun, UserPlus } from "lucide-react";
import { useAuth } from "../../context/AuthContext";
import Button from "../ui/Button";
import { ROLE_LABEL } from "../../lib/format";
import { getTheme, setTheme, type Theme } from "../../lib/theme";

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
    <div className="min-h-screen bg-canvas">
      <header className="sticky top-0 z-header bg-surface/85 backdrop-blur-md border-b border-line">
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
                className="w-8 h-8 rounded object-cover shrink-0"
              />
              <div className="min-w-0 hidden sm:block">
                <div className="text-sm font-semibold leading-tight truncate font-display">
                  Thành Công Limousine
                </div>
                <div className="text-2xs text-faint leading-tight tracking-wide">
                  BJC GROUP
                </div>
              </div>
            </Link>

            <nav className="flex items-center gap-1 shrink-0">
              {/* Lịch sử is visible to every role — admin, dispatcher,
                  and driver all asked to see past rides, unlike the
                  fleet/staff links which are staff-only.

                  Each link now reports whether it is the current page.
                  Before, every nav item looked identical regardless of
                  where you were, so the cheapest orientation cue in the
                  app was simply missing. */}
              <NavLink to="/history" icon={<History size={15} />} label="Lịch sử" />

              {(user?.role === "admin" || user?.role === "dispatcher") && (
                <NavLink to="/fleet" icon={<Car size={15} />} label="Đội xe" />
              )}

              {user?.role === "admin" && (
                <NavLink
                  to="/employees"
                  icon={<UserPlus size={15} />}
                  label="Nhân viên"
                />
              )}

              <div className="hidden md:flex flex-col items-end leading-tight mx-2">
                <span className="text-xs font-medium text-ink">
                  {user?.full_name}
                </span>
                <span className="text-2xs text-faint">
                  {ROLE_LABEL[user?.role ?? ""]}
                </span>
              </div>

              <ThemeToggle />

              <Button
                variant="ghost"
                onClick={logout}
                aria-label="Đăng xuất"
                className="!w-touch !h-touch !px-0"
              >
                <LogOut size={16} aria-hidden="true" />
              </Button>
            </nav>
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
            <h1 className="text-xl sm:text-2xl font-semibold text-ink">
              {title}
            </h1>
            {subtitle && (
              <p className="text-base text-faint mt-1">{subtitle}</p>
            )}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
        {children}
      </main>
    </div>
  );
}

/**
 * Nav item that knows whether it is the current page.
 *
 * The label collapses below `sm` rather than the whole control
 * disappearing — a button you cannot reach on a phone may as well not
 * exist — but the icon target stays 44px either way.
 */
function NavLink({
  to,
  icon,
  label,
}: {
  to: string;
  icon: ReactNode;
  label: string;
}) {
  const { pathname } = useLocation();
  const active = pathname === to;

  return (
    <Link
      to={to}
      aria-label={label}
      aria-current={active ? "page" : undefined}
      className={[
        "h-touch px-2 sm:px-3 inline-flex items-center gap-2 rounded",
        "text-base font-medium transition-colors",
        active
          ? "text-ink bg-sunken"
          : "text-muted hover:text-ink hover:bg-sunken",
      ].join(" ")}
    >
      <span aria-hidden="true" className="shrink-0">
        {icon}
      </span>
      <span className="hidden sm:inline">{label}</span>
    </Link>
  );
}

/**
 * Light/dark switch. Dispatch runs into the evening, and the tokens
 * were already structured for a second theme — this is the control
 * that reaches them. The initial value is read back off the <html>
 * element, which the boot script in index.html has already set from
 * localStorage or the OS preference.
 */
function ThemeToggle() {
  const [theme, setLocal] = useState<Theme>(() => getTheme());
  const next: Theme = theme === "dark" ? "light" : "dark";

  return (
    <Button
      variant="ghost"
      onClick={() => {
        setTheme(next);
        setLocal(next);
      }}
      aria-label={next === "dark" ? "Chuyển sang chế độ tối" : "Chuyển sang chế độ sáng"}
      title={next === "dark" ? "Chế độ tối" : "Chế độ sáng"}
      className="!w-touch !h-touch !px-0"
    >
      {theme === "dark" ? (
        <Sun size={16} aria-hidden="true" />
      ) : (
        <Moon size={16} aria-hidden="true" />
      )}
    </Button>
  );
}
