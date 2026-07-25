import { useEffect, type RefObject } from "react";

/**
 * Closes a popover on Escape, on outside pointer-down, and on scroll
 * of an ancestor — the three ways a user signals "I'm done with this"
 * without clicking the trigger again.
 *
 * Shared by Menu and Select so the two behave identically; a popover
 * that closes on outside click in one place and not another is the
 * kind of inconsistency people feel without being able to name.
 *
 * Uses pointerdown rather than click so the menu closes before the
 * underlying element's click handler fires — otherwise dismissing the
 * menu by clicking a button behind it also activates that button.
 */
export function useDismiss(
  open: boolean,
  ref: RefObject<HTMLElement | null>,
  onDismiss: () => void
) {
  useEffect(() => {
    if (!open) return;

    const onPointerDown = (e: PointerEvent) => {
      if (!ref.current?.contains(e.target as Node)) onDismiss();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onDismiss();
      }
    };

    document.addEventListener("pointerdown", onPointerDown, true);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown, true);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, ref, onDismiss]);
}
