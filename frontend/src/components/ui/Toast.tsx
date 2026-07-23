import {
  createContext,
  useCallback,
  useContext,
  useState,
  type ReactNode,
} from "react";

type Tone = "success" | "error" | "info";
interface Toast {
  id: number;
  tone: Tone;
  message: string;
}

const ToastContext = createContext<{
  toast: (message: string, tone?: Tone) => void;
} | null>(null);

const TONE_STYLES: Record<Tone, string> = {
  success: "border-l-[var(--success)]",
  error: "border-l-[var(--danger)]",
  info: "border-l-[var(--brand-blue)]",
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const toast = useCallback((message: string, tone: Tone = "info") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, tone, message }]);
    setTimeout(() => {
      setToasts((t) => t.filter((x) => x.id !== id));
    }, 4200);
  }, []);

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      {/* aria-live so screen readers announce async results that
          otherwise only exist as a visual flash */}
      <div
        aria-live="polite"
        aria-atomic="false"
        className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2 pointer-events-none"
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            role="status"
            className={[
              "animate-slide-up pointer-events-auto",
              "bg-[var(--surface)] border border-[var(--border)] border-l-[3px]",
              "rounded-[var(--radius-md)] shadow-[var(--shadow-lg)]",
              "px-4 py-3 text-sm max-w-[min(22rem,calc(100vw-2rem))]",
              TONE_STYLES[t.tone],
            ].join(" ")}
          >
            {t.message}
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
