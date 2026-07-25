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
        className="block text-xs font-medium mb-1.5 text-muted"
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
            "flex-1 h-9 px-3 text-base rounded bg-surface",
            "border transition-colors duration-fast",
            "placeholder:text-faint",
            error
              ? "border-danger"
              : "border-line-strong hover:border-faint",
            "focus:border-line-focus",
          ].join(" ")}
          {...rest}
        />
        {trailing}
      </div>
      {error && (
        <p id={errorId} className="mt-1.5 text-xs text-danger" role="alert">
          {error}
        </p>
      )}
      {hint && !error && (
        <p id={hintId} className="mt-1.5 text-xs text-faint">
          {hint}
        </p>
      )}
    </div>
  );
});

export default Field;
