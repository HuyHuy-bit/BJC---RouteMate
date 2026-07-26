import type { ReactNode } from "react";

/**
 * `accent` is a semantic token name rather than a free-form colour
 * string. It used to accept any CSS value, which is how brand red
 * ended up marking private hires — spending the primary-action colour
 * on a content attribute. Restricting it to outcome tones keeps the
 * rail meaning "the state of this thing", not "a colour I liked".
 */
type Accent = "success" | "danger" | "warning" | "info";

const ACCENT_CLASS: Record<Accent, string> = {
  success: "border-l-[3px] border-l-success",
  danger: "border-l-[3px] border-l-danger",
  warning: "border-l-[3px] border-l-warning",
  info: "border-l-[3px] border-l-cobalt",
};

export default function Card({
  children,
  className = "",
  interactive = false,
  accent,
  as: Tag = "div",
}: {
  children: ReactNode;
  className?: string;
  interactive?: boolean;
  accent?: Accent;
  as?: "div" | "article" | "li";
}) {
  return (
    <Tag
      className={[
        "bg-surface border border-line rounded-md",
        "shadow-xs",
        interactive ? "transition-shadow duration-base hover:shadow-md" : "",
        accent ? ACCENT_CLASS[accent] : "",
        className,
      ].join(" ")}
    >
      {children}
    </Tag>
  );
}
