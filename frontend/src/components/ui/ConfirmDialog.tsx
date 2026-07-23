import { useEffect, useRef } from "react";
import Button from "./Button";

/**
 * Replaces window.confirm() for destructive actions. Native confirm
 * can't be styled, can't explain consequences properly, and reads
 * poorly to screen readers. This traps focus and closes on Escape.
 */
export default function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Xoá",
  cancelLabel = "Huỷ",
  loading = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const confirmRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    confirmRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[90] flex items-center justify-center p-4 animate-fade-in"
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-title"
    >
      <div
        className="absolute inset-0 bg-[rgba(16,23,40,0.4)]"
        onClick={onCancel}
        aria-hidden="true"
      />
      <div className="relative bg-[var(--surface)] rounded-[var(--radius-lg)] shadow-[var(--shadow-lg)] w-full max-w-sm p-5 animate-slide-up">
        <h2
          id="confirm-title"
          className="text-base font-semibold text-[var(--text)]"
        >
          {title}
        </h2>
        {description && (
          <p className="text-sm text-[var(--text-secondary)] mt-2 leading-relaxed">
            {description}
          </p>
        )}
        <div className="flex gap-2 justify-end mt-5">
          <Button variant="ghost" onClick={onCancel} disabled={loading}>
            {cancelLabel}
          </Button>
          <Button
            ref={confirmRef}
            variant="danger"
            onClick={onConfirm}
            loading={loading}
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
