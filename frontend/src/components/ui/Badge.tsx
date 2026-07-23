import type { ReactNode } from "react";

type Tone = "neutral" | "success" | "warning" | "danger" | "info";

const TONES: Record<Tone, string> = {
  neutral:
    "bg-[var(--surface-sunken)] text-[var(--text-secondary)] border-[var(--border)]",
  success: "bg-[var(--success-subtle)] text-[var(--success)] border-transparent",
  warning: "bg-[var(--warning-subtle)] text-[var(--warning)] border-transparent",
  danger: "bg-[var(--danger-subtle)] text-[var(--danger)] border-transparent",
  info: "bg-[var(--info-subtle)] text-[var(--info)] border-transparent",
};

export default function Badge({
  tone = "neutral",
  children,
  className = "",
}: {
  tone?: Tone;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={[
        "inline-flex items-center gap-1 px-2 h-[22px] rounded-[var(--radius-full)]",
        "text-[11px] font-medium border whitespace-nowrap",
        TONES[tone],
        className,
      ].join(" ")}
    >
      {children}
    </span>
  );
}
