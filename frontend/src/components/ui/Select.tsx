import { useId } from "react";
import { ChevronDown, Loader2 } from "lucide-react";

interface SelectOption {
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
 * A styled native <select>.
 *
 * This was 260 lines of listbox — roving focus, aria-activedescendant,
 * a type-ahead buffer — to avoid two things. One was cosmetic: the OS
 * dropdown looks like Windows inside a designed interface. On a
 * driver's phone that "flaw" is the OS picker, which is better than
 * anything reimplemented here.
 *
 * The other was real: a native select fires `change` on keyboard
 * highlight, which is dangerous for "merge these two trips". But the
 * merge call site already stages the choice and commits it from a
 * confirm dialog (see TripsPanel), so a stray arrow-key opens a dialog
 * rather than merging anything. The argument was answered elsewhere.
 *
 * Option `detail` folds into the option text — a native <option> is one
 * line, and "Chuyến X · 3 chỗ đã đặt" says the same thing.
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
  const isDisabled = disabled || pending;
  const hasEmptyOption = options.some((o) => o.value === "");

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

      <div className="relative">
        <select
          id={id}
          value={value}
          aria-label={accessibleName}
          disabled={isDisabled}
          onChange={(e) => onChange(e.target.value)}
          className={[
            "w-full h-9 pl-3 pr-8 rounded appearance-none truncate",
            "bg-surface border border-line-strong text-base",
            value === "" && !hasEmptyOption ? "text-faint" : "text-ink",
            "transition-colors duration-fast",
            "hover:border-faint focus:border-line-focus",
            "disabled:opacity-60 disabled:pointer-events-none",
          ].join(" ")}
        >
          {!hasEmptyOption && (
            <option value="" disabled>
              {placeholder}
            </option>
          )}
          {options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.detail ? `${o.label} · ${o.detail}` : o.label}
            </option>
          ))}
        </select>

        {/* The arrow the appearance-none reset removed. pointer-events
            off so clicking it still opens the select underneath. */}
        <span className="absolute inset-y-0 right-2 flex items-center pointer-events-none">
          {pending ? (
            <Loader2
              size={14}
              className="animate-spin text-faint"
              aria-hidden="true"
            />
          ) : (
            <ChevronDown size={14} className="text-faint" aria-hidden="true" />
          )}
        </span>
      </div>
    </div>
  );
}
