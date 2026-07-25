import { useEffect, type RefObject } from "react";

const FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

/**
 * Keeps Tab inside an open dialog and hands focus back where it came
 * from on close.
 *
 * ConfirmDialog's docstring already claimed to do this; it actually
 * just called `.focus()` once on the confirm button, so a second Tab
 * walked straight out into the page behind — where the user could
 * keep operating a surface the modal was supposedly blocking.
 * SlideOver did not even do that much, so opening the booking form
 * left focus on the trigger button behind the overlay.
 *
 * `initialFocus` picks what gets focus on open. Destructive dialogs
 * point it at cancel rather than confirm: pre-focusing the button that
 * deletes a customer means Enter deletes them.
 */
export function useFocusTrap(
  open: boolean,
  containerRef: RefObject<HTMLElement | null>,
  initialFocus?: RefObject<HTMLElement | null>
) {
  useEffect(() => {
    if (!open) return;

    const previouslyFocused = document.activeElement as HTMLElement | null;
    const container = containerRef.current;
    if (!container) return;

    const focusables = () =>
      Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
        (el) => el.offsetParent !== null
      );

    // Defer so the dialog's children are mounted and measurable.
    const id = requestAnimationFrame(() => {
      (initialFocus?.current ?? focusables()[0] ?? container).focus();
    });

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Tab") return;
      const items = focusables();
      if (items.length === 0) {
        e.preventDefault();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const activeEl = document.activeElement;

      // Wrap at both ends, and pull focus back in if it has already
      // escaped (which happens when the browser restores focus to
      // <body> after the trigger unmounts).
      if (!container.contains(activeEl)) {
        e.preventDefault();
        first.focus();
      } else if (e.shiftKey && activeEl === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && activeEl === last) {
        e.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      cancelAnimationFrame(id);
      document.removeEventListener("keydown", onKeyDown, true);
      // Only restore if focus is still somewhere in the dialog we're
      // tearing down — otherwise the user has deliberately clicked
      // elsewhere and yanking focus back would be hostile.
      if (
        previouslyFocused?.isConnected &&
        (!document.activeElement ||
          document.activeElement === document.body ||
          container.contains(document.activeElement))
      ) {
        previouslyFocused.focus();
      }
    };
  }, [open, containerRef, initialFocus]);
}
