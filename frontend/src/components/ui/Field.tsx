import { forwardRef, useId, type InputHTMLAttributes, type ReactNode } from "react";

interface Props extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  hint?: string;
  error?: string;
  trailing?: ReactNode;
}

/**
 * Always renders a real <label> bound to the input — placeholder-only
 * fields fail WCAG (the cue vanishes once you type) and hurt everyone
 * who's mid-form and needs to re-check what a box is for.
 */
const Field = forwardRef<HTMLInputElement, Props>(function Field(
  { label, hint, error, trailing, className = "", id: providedId, ...rest },
  ref
) {
  const autoId = useId();
  const id = providedId ?? autoId;
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;

  return (
    <div className={className}>
      <label
        htmlFor={id}
        className="block text-[12px] font-medium mb-1.5 text-[var(--text-secondary)]"
      >
        {label}
      </label>
      <div className="flex gap-2">
        <input
          ref={ref}
          id={id}
          aria-describedby={[hintId, errorId].filter(Boolean).join(" ") || undefined}
          aria-invalid={error ? true : undefined}
          className={[
            "flex-1 h-9 px-3 text-sm rounded-[var(--radius)] bg-[var(--surface)]",
            "border transition-colors duration-[var(--duration-fast)]",
            "placeholder:text-[var(--text-tertiary)]",
            error
              ? "border-[var(--danger)]"
              : "border-[var(--border-strong)] hover:border-[var(--text-tertiary)]",
            "focus:border-[var(--border-focus)]",
          ].join(" ")}
          {...rest}
        />
        {trailing}
      </div>
      {error && (
        <p id={errorId} className="mt-1.5 text-xs text-[var(--danger)]" role="alert">
          {error}
        </p>
      )}
      {hint && !error && (
        <p id={hintId} className="mt-1.5 text-xs text-[var(--text-tertiary)]">
          {hint}
        </p>
      )}
    </div>
  );
});

export default Field;
