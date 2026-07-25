import { Link } from "react-router-dom";
import { Compass } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import Button from "../components/ui/Button";

/**
 * Replaces `<Route path="*" element={<Navigate to="/" replace />} />`.
 *
 * That redirect was silent, and for a driver it bounced twice — "/"
 * immediately forwards them to "/driver" — so a mistyped or stale
 * URL teleported you somewhere else with no explanation. Saying
 * "that page doesn't exist" and offering one correct way back is
 * both shorter and honest.
 */
export default function NotFoundPage() {
  const { user } = useAuth();
  const home = user?.role === "driver" ? "/driver" : "/";

  return (
    <div className="min-h-screen bg-canvas flex items-center justify-center p-6">
      <div className="w-full max-w-sm text-center">
        <div
          className="w-10 h-10 rounded-lg bg-sunken text-faint flex items-center justify-center mx-auto mb-3"
          aria-hidden="true"
        >
          <Compass size={18} />
        </div>
        <h1 className="text-xl font-semibold text-ink">Không tìm thấy trang</h1>
        <p className="text-base text-muted mt-2 leading-relaxed">
          Đường dẫn này không tồn tại hoặc bạn không có quyền truy cập.
        </p>
        <Link to={home} className="inline-block mt-5">
          <Button variant="primary" size="lg">
            {user?.role === "driver" ? "Về chuyến của tôi" : "Về bảng điều phối"}
          </Button>
        </Link>
      </div>
    </div>
  );
}
