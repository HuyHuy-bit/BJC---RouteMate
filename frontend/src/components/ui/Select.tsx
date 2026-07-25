import { useEffect, useId, useRef, useState } from "react";
import { Check, ChevronDown, Loader2 } from "lucide-react";
import { useDismiss } from "../../lib/useDismiss";

export interface SelectOption {
  value: string;
  label: string;
  /** Secondary line, e.g. how many passengers a merge candidate has. */
  detail?: string;
}

interface Props {
  label: string;
  /** Hide the label visually but keep it for screen readers. */
  labelHidden?: boolean;
  /**
   * Overrides the accessible name when the visible label is too terse
   * to stand alone. "Trạng thái" repeated down a fleet list is fine to
   * look at and useless to hear — this lets the row say
   * "Trạng thái xe 98A-12345" instead.
   */
  accessibleName?: string;
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  placeholder?: string;
  /** Shows a spinner and blocks input while a mutation is in flight. */
  pending?: boolean;
  disabled?: boolean;
  icon?: React.ReactNode;
  className?: string;
}

/**
 * Replaces the raw <select> elements this app used for driver
 * assignment, vehicle status, and trip merging.
 *
 * Two reasons, one cosmetic and one not. Cosmetically, a native select
 * renders the operating system's own dropdown — Windows chrome inside
 * an otherwise carefully built interface, and the single loudest signal
 * that a product was assembled rather than designed.
 *
 * Functionally, the native control fires `change` the instant an option
 * is highlighted with the keyboard, which is fine for choosing a filter
 * and dangerous for "merge these two trips". Here, moving through the
 * list changes nothing; only Enter or a click commits, and the caller
 * can still stage that commit behind a confirmation.
 */
export default function Select({
  label,
  labelHidden = false,
  accessibleName,
  value,
  options,
  onChange,
  placeholder = "Chọn...",
  pending = false,
  disabled = false,
  icon,
  className = "",
}: Props) {
  const id = useId();
  const listId = `${id}-list`;
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  // Type-to-filter buffer, cleared after a short pause.
  const typed = useRef({ text: "", at: 0 });

  const selected = options.find((o) => o.value === value);
  const isDisabled = disabled || pending;

  useDismiss(open, rootRef, () => setOpen(false));

  // Open at the current selection, not at the top of the list.
  useEffect(() => {
    if (open) {
      const i = options.findIndex((o) => o.value === value);
      setActive(i >= 0 ? i : 0);
    }
  }, [open, value, options]);

  // Keep the highlighted option in view when arrowing through a long list.
  useEffect(() => {
    if (!open) return;
    listRef.current
      ?.querySelector(`[data-index="${active}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [open, active]);

  const commit = (i: number) => {
    const opt = options[i];
    if (!opt) return;
    setOpen(false);
    triggerRef.current?.focus();
    if (opt.value !== value) onChange(opt.value);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (isDisabled) return;

    if (!open) {
      if (["ArrowDown", "ArrowUp", "Enter", " "].includes(e.key)) {
        e.preventDefault();
        setOpen(true);
      }
      return;
    }

    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        setActive((i) => Math.min(i + 1, options.length - 1));
        break;
      case "ArrowUp":
        e.preventDefault();
        setActive((i) => Math.max(i - 1, 0));
        break;
      case "Home":
        e.preventDefault();
        setActive(0);
        break;
      case "End":
        e.preventDefault();
        setActive(options.length - 1);
        break;
      case "Enter":
      case " ":
        e.preventDefault();
        commit(active);
        break;
      case "Tab":
        setOpen(false);
        break;
      default: {
        if (e.key.length !== 1) break;
        const now = Date.now();
        typed.current.text =
          now - typed.current.at > 600 ? e.key : typed.current.text + e.key;
        typed.current.at = now;
        const q = typed.current.text.toLowerCase();
        const hit = options.findIndex((o) =>
          o.label.toLowerCase().startsWith(q)
        );
        if (hit >= 0) setActive(hit);
      }
    }
  };

  return (
    <div className={className}>
      <label
        htmlFor={id}
        className={
          labelHidden
            ? "sr-only"
            : "flex items-center gap-1.5 text-xs font-medium mb-1.5 text-muted"
        }
      >
        {icon && (
          <span className="shrink-0" aria-hidden="true">
            {icon}
          </span>
        )}
        {label}
      </label>

      <div ref={rootRef} className="relative">
        <button
          ref={triggerRef}
          id={id}
          type="button"
          role="combobox"
          aria-controls={listId}
          aria-expanded={open}
          aria-haspopup="listbox"
          aria-label={accessibleName}
          aria-activedescendant={open ? `${id}-opt-${active}` : undefined}
          disabled={isDisabled}
          onClick={() => setOpen((o) => !o)}
          onKeyDown={onKeyDown}
          className={[
            "w-full h-9 pl-3 pr-2 flex items-center justify-between gap-2 rounded",
            "bg-surface border border-line-strong text-base text-left",
            "transition-colors duration-fast",
            "hover:border-faint focus:border-line-focus",
            "disabled:opacity-60 disabled:pointer-events-none",
          ].join(" ")}
        >
          <span
            className={`truncate ${selected ? "text-ink" : "text-faint"}`}
          >
            {selected?.label ?? placeholder}
          </span>
          {pending ? (
            <Loader2
              size={14}
              className="shrink-0 animate-spin text-faint"
              aria-hidden="true"
            />
          ) : (
            <ChevronDown
              size={14}
              className={`shrink-0 text-faint transition-transform duration-fast ${
                open ? "rotate-180" : ""
              }`}
              aria-hidden="true"
            />
          )}
        </button>

        {open && (
          <ul
            ref={listRef}
            id={listId}
            role="listbox"
            aria-label={label}
            className={[
              "absolute z-dropdown left-0 right-0 mt-1 py-1 max-h-60 overflow-y-auto",
              "bg-surface border border-line rounded-md shadow-lg animate-slide-up",
            ].join(" ")}
          >
            {options.map((o, i) => {
              const isSelected = o.value === value;
              return (
                <li
                  key={o.value}
                  id={`${id}-opt-${i}`}
                  data-index={i}
                  role="option"
                  aria-selected={isSelected}
                  onClick={() => commit(i)}
                  onMouseEnter={() => setActive(i)}
                  className={[
                    "px-3 py-2 flex items-start gap-2 cursor-pointer text-base",
                    i === active ? "bg-sunken" : "",
                  ].join(" ")}
                >
                  <span className="w-3.5 shrink-0 mt-0.5" aria-hidden="true">
                    {isSelected && <Check size={13} className="text-cobalt" />}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate">{o.label}</span>
                    {o.detail && (
                      <span className="block text-xs text-faint">
                        {o.detail}
                      </span>
                    )}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
