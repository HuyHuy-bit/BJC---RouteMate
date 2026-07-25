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
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-12 px-6">
      {icon && (
        <div
          className="w-10 h-10 rounded-lg bg-sunken flex items-center justify-center mb-3 text-faint"
          aria-hidden="true"
        >
          {icon}
        </div>
      )}
      <p className="text-base font-medium text-ink">{title}</p>
      {description && (
        <p className="text-xs text-faint mt-1 max-w-[36ch]">
          {description}
        </p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
