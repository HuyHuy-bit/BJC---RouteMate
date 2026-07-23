import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./context/AuthContext";
import LoginPage from "./pages/LoginPage";
import DispatchBoard from "./pages/DispatchBoard";
import DriverDashboard from "./pages/DriverDashboard";
import CreateUserPage from "./pages/CreateUserPage";

function Loading() {
  return (
    <div className="min-h-screen flex items-center justify-center text-sm">
      Đang tải...
    </div>
  );
}

function ProtectedRoute({
  children,
  allow,
}: {
  children: React.ReactNode;
  allow?: Array<"admin" | "dispatcher" | "driver">;
}) {
  const { user, loading } = useAuth();
  if (loading) return <Loading />;
  if (!user) return <Navigate to="/login" replace />;
  if (allow && !allow.includes(user.role)) {
    return <Navigate to={user.role === "driver" ? "/driver" : "/"} replace />;
  }
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <ProtectedRoute allow={["admin", "dispatcher"]}>
            <DispatchBoard />
          </ProtectedRoute>
        }
      />
      <Route
        path="/driver"
        element={
          <ProtectedRoute allow={["driver"]}>
            <DriverDashboard />
          </ProtectedRoute>
        }
      />
      <Route
        path="/admin/users/new"
        element={
          <ProtectedRoute allow={["admin"]}>
            <CreateUserPage />
          </ProtectedRoute>
        }
      />
    </Routes>
  );
}
