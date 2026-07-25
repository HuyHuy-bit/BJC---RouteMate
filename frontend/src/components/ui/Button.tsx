import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "danger-subtle";
type Size = "sm" | "md" | "lg";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  iconLeft?: ReactNode;
  fullWidth?: boolean;
}

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-brand text-white hover:bg-brand-hover active:scale-[0.98] shadow-xs",
  secondary:
    "bg-surface text-ink border border-line-strong hover:bg-sunken active:scale-[0.98]",
  ghost:
    "bg-transparent text-muted hover:bg-sunken hover:text-ink",
  danger:
    "bg-danger text-on-danger hover:brightness-110 active:scale-[0.98]",
  "danger-subtle":
    "bg-transparent text-danger border border-transparent hover:bg-danger-subtle hover:border-danger",
};

const SIZES: Record<Size, string> = {
  sm: "h-7 px-2.5 text-xs gap-1.5 rounded",
  md: "h-9 px-3.5 text-base gap-2 rounded",
  lg: "h-11 px-5 text-base gap-2 rounded-md",
};

const Button = forwardRef<HTMLButtonElement, Props>(function Button(
  {
    variant = "secondary",
    size = "md",
    loading = false,
    iconLeft,
    fullWidth,
    disabled,
    children,
    className = "",
    ...rest
  },
  ref
) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={[
        "inline-flex items-center justify-center font-medium whitespace-nowrap",
        "transition-all duration-fast ease-brand",
        "disabled:opacity-50 disabled:pointer-events-none",
        VARIANTS[variant],
        SIZES[size],
        fullWidth ? "w-full" : "",
        className,
      ].join(" ")}
      {...rest}
    >
      {loading ? (
        <span
          className="w-3.5 h-3.5 rounded-full border-2 border-current border-r-transparent animate-spin"
          aria-hidden="true"
        />
      ) : (
        iconLeft
      )}
      {children}
    </button>
  );
});

export default Button;
