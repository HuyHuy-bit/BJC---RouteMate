import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { MoreVertical } from "lucide-react";
import { useDismiss } from "../../lib/useDismiss";

interface MenuItem {
  label: string;
  icon?: ReactNode;
  onSelect: () => void;
  /** Destructive items get danger styling and sort visually last. */
  danger?: boolean;
  disabled?: boolean;
}

/**
 * Overflow menu for secondary row actions.
 *
 * Exists mainly for the driver screen, where actions like "khách không
 * đến" and "báo sự cố" used to be 12px underlined text sitting inches
 * from the payment control — tapped one-handed, outdoors, sometimes in
 * a hurry. Collecting them behind a 44px trigger does two things: it
 * makes them reachable, and it makes reaching them deliberate.
 */
export default function Menu({
  items,
  label = "Thao tác khác",
  align = "right",
}: {
  items: MenuItem[];
  label?: string;
  align?: "left" | "right";
}) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const close = useCallback(() => {
    setOpen(false);
    triggerRef.current?.focus();
  }, []);

  useDismiss(open, rootRef, () => setOpen(false));

  // Move real DOM focus with the active index so screen readers and
  // sighted keyboard users stay in agreement about where they are.
  useEffect(() => {
    if (open) itemRefs.current[active]?.focus();
  }, [open, active]);

  const enabled = items.filter((i) => !i.disabled);
  if (enabled.length === 0) return null;

  const step = (delta: number) => {
    setActive((cur) => {
      let next = cur;
      for (let i = 0; i < items.length; i++) {
        next = (next + delta + items.length) % items.length;
        if (!items[next].disabled) break;
      }
      return next;
    });
  };

  return (
    <div ref={rootRef} className="relative shrink-0">
      <button
        ref={triggerRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={label}
        onClick={() => {
          setOpen((o) => !o);
          setActive(items.findIndex((i) => !i.disabled));
        }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" || e.key === "ArrowUp") {
            e.preventDefault();
            setOpen(true);
            setActive(
              e.key === "ArrowDown"
                ? items.findIndex((i) => !i.disabled)
                : items.length - 1
            );
          }
        }}
        className="w-touch h-touch inline-flex items-center justify-center rounded text-faint hover:bg-sunken hover:text-ink transition-colors"
      >
        <MoreVertical size={18} aria-hidden="true" />
      </button>

      {open && (
        <div
          role="menu"
          aria-label={label}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              step(1);
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              step(-1);
            } else if (e.key === "Tab") {
              // Tabbing out of a menu means leaving it.
              setOpen(false);
            }
          }}
          className={[
            "absolute z-dropdown mt-1 min-w-[13rem] py-1",
            "bg-surface border border-line rounded-md shadow-lg animate-slide-up",
            align === "right" ? "right-0" : "left-0",
          ].join(" ")}
        >
          {items.map((item, i) => (
            <button
              key={item.label}
              ref={(el) => {
                itemRefs.current[i] = el;
              }}
              role="menuitem"
              type="button"
              disabled={item.disabled}
              tabIndex={i === active ? 0 : -1}
              onClick={() => {
                close();
                item.onSelect();
              }}
              className={[
                "w-full min-h-touch px-3 flex items-center gap-2.5 text-base text-left",
                "transition-colors disabled:opacity-40 disabled:pointer-events-none",
                item.danger
                  ? "text-danger hover:bg-danger-subtle"
                  : "text-ink hover:bg-sunken",
              ].join(" ")}
            >
              {item.icon && (
                <span className="shrink-0" aria-hidden="true">
                  {item.icon}
                </span>
              )}
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
