import { useEffect, type ReactNode } from "react";
import { X } from "lucide-react";
import Button from "./Button";

/**
 * Booking entry lives here instead of permanently occupying the top of
 * the dispatch board. Monitoring is the dispatcher's default state;
 * data entry is an interruption, so it gets an overlay, not real estate.
 */
export default function SlideOver({
  open,
  title,
  description,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  description?: string;
  onClose: () => void;
  children: ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[80]"
      role="dialog"
      aria-modal="true"
      aria-labelledby="slideover-title"
    >
      <div
        className="absolute inset-0 bg-[rgba(16,23,40,0.35)] animate-fade-in"
        onClick={onClose}
        aria-hidden="true"
      />
      <div className="absolute right-0 top-0 h-full w-full max-w-xl bg-[var(--bg)] shadow-[var(--shadow-lg)] animate-slide-in-right flex flex-col">
        <header className="flex items-start justify-between gap-4 px-5 py-4 bg-[var(--surface)] border-b border-[var(--border)]">
          <div>
            <h2
              id="slideover-title"
              className="text-base font-semibold text-[var(--text)]"
            >
              {title}
            </h2>
            {description && (
              <p className="text-xs text-[var(--text-tertiary)] mt-0.5">
                {description}
              </p>
            )}
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={onClose}
            aria-label="Đóng"
            className="!px-1.5 shrink-0"
          >
            <X size={16} aria-hidden="true" />
          </Button>
        </header>
        <div className="flex-1 overflow-y-auto p-5">{children}</div>
      </div>
    </div>
  );
}
