import { Component, type ErrorInfo, type ReactNode } from "react";
import Button from "./ui/Button";

/**
 * Last line of defence. Without this, one thrown render — a shape
 * the API didn't promise, an undefined lookup in a status map — is
 * a blank white screen with no way forward but a manual reload,
 * which most dispatchers will read as "the system is down".
 *
 * Deliberately a full reload rather than a state reset: if a render
 * threw, the cached data that caused it is still in memory, so
 * clearing the error and re-rendering would usually just throw
 * again in a loop.
 */
interface State {
  error: Error | null;
}

export default class ErrorBoundary extends Component<
  { children: ReactNode },
  State
> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // No telemetry service wired up yet, so the console is the only
    // record — keep the component stack, it's the useful half.
    console.error("Unhandled render error:", error, info.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div className="min-h-screen bg-canvas flex items-center justify-center p-6">
        <div className="w-full max-w-md text-center">
          <h1 className="text-xl font-semibold text-ink">
            Hệ thống gặp lỗi ngoài dự kiến
          </h1>
          <p className="text-base text-muted mt-2 leading-relaxed">
            Dữ liệu của bạn không bị mất. Tải lại trang để tiếp tục — nếu lỗi
            lặp lại, chụp màn hình này và gửi cho quản trị viên.
          </p>
          <p className="text-2xs font-mono text-faint mt-4 break-words bg-sunken rounded p-3 text-left">
            {error.message || String(error)}
          </p>
          <Button
            variant="primary"
            size="lg"
            className="mt-5"
            onClick={() => window.location.reload()}
          >
            Tải lại trang
          </Button>
        </div>
      </div>
    );
  }
}
