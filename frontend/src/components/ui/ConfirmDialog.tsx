import { useId, useRef } from "react";
import Button from "./Button";
import { useFocusTrap } from "../../lib/useFocusTrap";

/**
 * Replaces window.confirm() for destructive actions. Native confirm
 * can't be styled, can't explain consequences properly, and reads
 * poorly to screen readers.
 *
 * Focus opens on Cancel, not Confirm. Every dialog using this deletes
 * a customer, locks an employee out, or merges two trips — pre-focusing
 * the destructive button means a stray Enter (or the Enter that
 * submitted the form which opened this) carries it out.
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
  const titleId = useId();
  const descId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);

  useFocusTrap(open, panelRef, cancelRef);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-dialog flex items-center justify-center p-4 animate-fade-in"
      onKeyDown={(e) => {
        // Scoped to the dialog rather than the document, so a nested
        // popover can swallow its own Escape first.
        if (e.key === "Escape" && !loading) {
          e.stopPropagation();
          onCancel();
        }
      }}
    >
      <div
        className="absolute inset-0 bg-scrim"
        onClick={loading ? undefined : onCancel}
        aria-hidden="true"
      />
      {/* aria-modal and the label live on the panel, not the fullscreen
          wrapper — the wrapper contains the scrim, which is
          aria-hidden, and nesting hidden content inside the dialog
          node confuses assistive tech about the dialog's bounds. IDs
          come from useId because two of these can be mounted on one
          screen (EmployeesPage has deactivate and delete), and a
          hardcoded id="confirm-title" would collide. */}
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descId : undefined}
        className="relative bg-surface rounded-lg shadow-lg w-full max-w-sm p-5 animate-slide-up"
      >
        <h2 id={titleId} className="text-lg font-semibold text-ink">
          {title}
        </h2>
        {description && (
          <p id={descId} className="text-base text-muted mt-2 leading-relaxed">
            {description}
          </p>
        )}
        <div className="flex gap-2 justify-end mt-5">
          <Button
            ref={cancelRef}
            variant="ghost"
            onClick={onCancel}
            disabled={loading}
          >
            {cancelLabel}
          </Button>
          <Button variant="danger" onClick={onConfirm} loading={loading}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
