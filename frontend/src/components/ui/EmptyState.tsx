import type { ReactNode } from "react";

/**
 * An empty screen is an invitation to act, not a dead end — so this
 * always takes an action slot rather than just saying "nothing here".
 */
export default function EmptyState({
  icon,
  title,
  description,
  action,
  compact = false,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
  /**
   * For empty states filling a secondary panel rather than a whole
   * screen. The default padding is sized for a page; inside the
   * fleet-status card it produced ~300px of blank white for one
   * sentence, and three of those stacked made a working board look
   * broken.
   */
  compact?: boolean;
}) {
  return (
    <div
      className={`flex flex-col items-center justify-center text-center px-6 ${
        compact ? "py-7" : "py-12"
      }`}
    >
      {icon && (
        <div
          className={`rounded-lg bg-sunken flex items-center justify-center text-faint ${
            compact ? "w-8 h-8 mb-2" : "w-10 h-10 mb-3"
          }`}
          aria-hidden="true"
        >
          {icon}
        </div>
      )}
      <p className="text-base font-medium text-ink">{title}</p>
      {description && (
        <p className="text-xs text-faint mt-1 max-w-[40ch] leading-relaxed">
          {description}
        </p>
      )}
      {action && <div className={compact ? "mt-3" : "mt-4"}>{action}</div>}
    </div>
  );
}
