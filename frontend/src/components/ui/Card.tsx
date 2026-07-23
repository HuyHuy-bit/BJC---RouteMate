import type { ReactNode } from "react";

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
  accent?: string;
  as?: "div" | "article" | "li";
}) {
  return (
    <Tag
      className={[
        "bg-[var(--surface)] border border-[var(--border)] rounded-[var(--radius-lg)]",
        "shadow-[var(--shadow-xs)]",
        interactive
          ? "transition-shadow duration-[var(--duration)] hover:shadow-[var(--shadow-md)]"
          : "",
        className,
      ].join(" ")}
      style={accent ? { borderLeft: `3px solid ${accent}` } : undefined}
    >
      {children}
    </Tag>
  );
}
