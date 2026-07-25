import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";

type Tone = "success" | "error" | "info";

interface Toast {
  id: number;
  tone: Tone;
  message: string;
}

const ToastContext = createContext<{
  toast: (message: string, tone?: Tone) => void;
} | null>(null);

/**
 * How long each tone survives.
 *
 * Errors do not expire. Previously everything vanished after a fixed
 * 4.2s with no close button, so an error raised while the dispatcher
 * was looking at their phone was unrecoverable — they'd learn
 * something had failed only by noticing the data never changed. A
 * failure needs to wait to be read; a success does not.
 */
const DURATION: Record<Tone, number | null> = {
  success: 4000,
  info: 5000,
  error: null,
};

const TONE: Record<Tone, { rail: string; icon: ReactNode; label: string }> = {
  success: {
    rail: "border-l-success",
    icon: <CheckCircle2 size={16} className="text-success" aria-hidden="true" />,
    label: "Thành công",
  },
  error: {
    rail: "border-l-danger",
    icon: <AlertCircle size={16} className="text-danger" aria-hidden="true" />,
    label: "Lỗi",
  },
  info: {
    rail: "border-l-cobalt",
    icon: <Info size={16} className="text-cobalt" aria-hidden="true" />,
    label: "Thông báo",
  },
};

// Beyond this the stack becomes a wall covering the board it's
// reporting on.
const MAX_VISIBLE = 4;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  // Hovering or focusing the stack pauses expiry — reading a message
  // shouldn't be a race against it disappearing.
  const [paused, setPaused] = useState(false);
  const nextId = useRef(0);

  const dismiss = useCallback((id: number) => {
    setToasts((t) => t.filter((x) => x.id !== id));
  }, []);

  const toast = useCallback((message: string, tone: Tone = "info") => {
    setToasts((current) => {
      const next = [...current, { id: nextId.current++, tone, message }];
      if (next.length <= MAX_VISIBLE) return next;
      // Drop the oldest dismissible entry rather than plainly slicing,
      // so a burst of successes can't push an error off screen.
      const victim = next.findIndex((t) => t.tone !== "error");
      return victim === -1
        ? next.slice(next.length - MAX_VISIBLE)
        : next.filter((_, i) => i !== victim);
    });
  }, []);

  // One timer per expiring toast, suspended while the stack is hovered.
  useEffect(() => {
    if (paused) return;
    const timers = toasts
      .map((t) => {
        const ms = DURATION[t.tone];
        return ms === null ? null : window.setTimeout(() => dismiss(t.id), ms);
      })
      .filter((id): id is number => id !== null);
    return () => timers.forEach(clearTimeout);
  }, [toasts, paused, dismiss]);

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      {/* aria-live so screen readers announce async results that
          otherwise only exist as a visual flash. Errors are assertive
          because they interrupt the task; successes stay polite. */}
      <div
        className="fixed bottom-4 right-4 z-toast flex flex-col gap-2 pointer-events-none"
        onMouseEnter={() => setPaused(true)}
        onMouseLeave={() => setPaused(false)}
        onFocus={() => setPaused(true)}
        onBlur={() => setPaused(false)}
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            role={t.tone === "error" ? "alert" : "status"}
            aria-live={t.tone === "error" ? "assertive" : "polite"}
            className={[
              "animate-slide-up pointer-events-auto flex items-start gap-2.5",
              "bg-surface border border-line border-l-[3px]",
              "rounded-md shadow-lg py-3 pl-3 pr-2",
              "text-base max-w-[min(24rem,calc(100vw-2rem))]",
              TONE[t.tone].rail,
            ].join(" ")}
          >
            <span className="shrink-0 mt-0.5">{TONE[t.tone].icon}</span>
            <span className="min-w-0 flex-1 leading-snug">{t.message}</span>
            <button
              type="button"
              onClick={() => dismiss(t.id)}
              aria-label={`Đóng thông báo: ${TONE[t.tone].label}`}
              className="shrink-0 w-7 h-7 -mt-0.5 inline-flex items-center justify-center rounded text-faint hover:text-ink hover:bg-sunken transition-colors"
            >
              <X size={14} aria-hidden="true" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside ToastProvider");
  return ctx.toast;
}
