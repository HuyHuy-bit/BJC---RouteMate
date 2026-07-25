import { useEffect, useId, useRef, type ReactNode } from "react";
import { X } from "lucide-react";
import Button from "./Button";
import { useFocusTrap } from "../../lib/useFocusTrap";

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
  const titleId = useId();
  const descId = useId();
  const panelRef = useRef<HTMLDivElement>(null);

  // No initialFocus: the trap falls through to the first focusable
  // element, which is the close button — deliberately not the first
  // text input, since jumping the caret into a field on open makes
  // the panel's own heading easy to miss.
  useFocusTrap(open, panelRef);

  useEffect(() => {
    if (!open) return;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-slideover"
      onKeyDown={(e) => {
        // Scoped rather than document-level so a Select popover inside
        // the panel can consume its own Escape without closing the
        // whole form and discarding what's been typed.
        if (e.key === "Escape") {
          e.stopPropagation();
          onClose();
        }
      }}
    >
      <div
        className="absolute inset-0 bg-scrim animate-fade-in"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descId : undefined}
        className="absolute right-0 top-0 h-full w-full max-w-xl bg-canvas shadow-lg animate-slide-in-right flex flex-col"
      >
        <header className="flex items-start justify-between gap-4 px-5 py-4 bg-surface border-b border-line">
          <div>
            <h2 id={titleId} className="text-lg font-semibold text-ink">
              {title}
            </h2>
            {description && (
              <p id={descId} className="text-xs text-faint mt-0.5">
                {description}
              </p>
            )}
          </div>
          <Button
            variant="ghost"
            onClick={onClose}
            aria-label="Đóng"
            className="!w-touch !h-touch !px-0 shrink-0"
          >
            <X size={18} aria-hidden="true" />
          </Button>
        </header>
        <div className="flex-1 overflow-y-auto p-5">{children}</div>
      </div>
    </div>
  );
}
