import type { ReactNode } from "react";
import type { UseQueryResult } from "@tanstack/react-query";
import { RotateCw, WifiOff } from "lucide-react";
import Button from "./Button";
import { getErrorMessage } from "../../lib/errors";

/**
 * Loading, failed, and empty are three different things, and every
 * screen in this app used to collapse the first two into the third.
 *
 * Because each query fell back to `data ?? []`, a dead API rendered
 * as "Chưa có khách nào trong hàng chờ" — complete with an inviting
 * "Thêm khách" button. A dispatcher would read that as a quiet
 * evening and go make tea while bookings piled up unseen. For a
 * dispatch system that is the worst possible failure: it doesn't
 * look like a failure.
 *
 * So the error branch here is deliberately NOT reassuring. It is
 * the only place in the product that uses a danger tone for a
 * whole panel, it names what broke, and it offers a retry that
 * doesn't require reloading the page.
 */
interface Props<T> {
  query: UseQueryResult<T>;
  /** Shown while the first fetch is in flight. Should echo the real
   *  content's shape — see the callers for examples. */
  skeleton: ReactNode;
  children: (data: T) => ReactNode;
  /** Rendered when the fetch succeeded but there is genuinely nothing
   *  to show. A node rather than a config object so the caller keeps
   *  control of the wrapper — some of these sit inside an existing
   *  Card and must not nest a second one. Omit to always render
   *  children. */
  empty?: ReactNode;
  isEmpty?: (data: T) => boolean;
  /** What failed, in the user's terms: "Không tải được hàng chờ". */
  errorTitle?: string;
}

export default function QueryState<T>({
  query,
  skeleton,
  children,
  empty,
  isEmpty,
  errorTitle = "Không tải được dữ liệu",
}: Props<T>) {
  // isPending covers the first load; a background refetch of data we
  // already have must not blank the screen out from under someone.
  if (query.isPending) return <>{skeleton}</>;

  if (query.isError) {
    return (
      <ErrorState
        title={errorTitle}
        message={getErrorMessage(
          query.error,
          "Không kết nối được tới hệ thống. Kiểm tra mạng rồi thử lại."
        )}
        onRetry={() => query.refetch()}
        retrying={query.isFetching}
      />
    );
  }

  const data = query.data as T;

  if (empty && (isEmpty ? isEmpty(data) : isEmptyByDefault(data))) {
    return <>{empty}</>;
  }

  return <>{children(data)}</>;
}

function isEmptyByDefault(data: unknown): boolean {
  if (Array.isArray(data)) return data.length === 0;
  return data === null || data === undefined;
}

/**
 * Also exported standalone, for the handful of places that fetch
 * outside a QueryState (and for the route error boundary).
 */
export function ErrorState({
  title,
  message,
  onRetry,
  retrying = false,
}: {
  title: string;
  message: string;
  onRetry?: () => void;
  retrying?: boolean;
}) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center justify-center text-center py-10 px-6 border border-danger/40 bg-danger-subtle rounded-md"
    >
      <div
        className="w-10 h-10 rounded-md bg-surface flex items-center justify-center mb-3 text-danger"
        aria-hidden="true"
      >
        <WifiOff size={18} />
      </div>
      <p className="text-base font-medium text-ink">{title}</p>
      <p className="text-xs text-muted mt-1 max-w-[44ch] leading-relaxed">{message}</p>
      {onRetry && (
        <Button
          variant="secondary"
          size="sm"
          onClick={onRetry}
          loading={retrying}
          iconLeft={<RotateCw size={13} aria-hidden="true" />}
          className="mt-4"
        >
          Thử lại
        </Button>
      )}
    </div>
  );
}
