import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./context/AuthContext";
import ErrorBoundary from "./components/ErrorBoundary";
import LoginPage from "./pages/LoginPage";
import NotFoundPage from "./pages/NotFoundPage";
import type { UserRole } from "./types";

// Route-level code splitting — the driver bundle shouldn't ship the
// dispatch board (and its map library) to a phone that will never open it.
const DispatchBoard = lazy(() => import("./pages/DispatchBoard"));
const DriverDashboard = lazy(() => import("./pages/DriverDashboard"));
const CreateUserPage = lazy(() => import("./pages/CreateUserPage"));
const FleetPage = lazy(() => import("./pages/FleetPage"));
const NotificationsPage = lazy(() => import("./pages/NotificationsPage"));
const HistoryPage = lazy(() => import("./pages/HistoryPage"));
const EmployeesPage = lazy(() => import("./pages/EmployeesPage"));
// Admin-only, and the only screen in the app that shows money in
// aggregate — kept out of the dispatcher bundle entirely.
const AdminDashboard = lazy(() => import("./pages/AdminDashboard"));

function FullPageLoader() {
  return (
    <div
      className="min-h-screen flex items-center justify-center"
      role="status"
      aria-label="Đang tải"
    >
      <div className="w-6 h-6 rounded-full border-2 border-line-strong border-t-brand animate-spin" />
    </div>
  );
}

function ProtectedRoute({
  children,
  allow,
}: {
  children: ReactNode;
  allow?: UserRole[];
}) {
  const { user, loading } = useAuth();
  if (loading) return <FullPageLoader />;
  if (!user) return <Navigate to="/login" replace />;
  if (allow && !allow.includes(user.role)) {
    return <Navigate to={user.role === "driver" ? "/driver" : "/"} replace />;
  }
  return <>{children}</>;
}

export default function App() {
  return (
    <ErrorBoundary>
      <Suspense fallback={<FullPageLoader />}>
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
        <Route
          path="/fleet"
          element={
            <ProtectedRoute allow={["admin", "dispatcher"]}>
              <FleetPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/notifications"
          element={
            <ProtectedRoute allow={["admin", "dispatcher"]}>
              <NotificationsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/history"
          element={
            <ProtectedRoute allow={["admin", "dispatcher", "driver"]}>
              <HistoryPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/business"
          element={
            <ProtectedRoute allow={["admin"]}>
              <AdminDashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="/employees"
          element={
            <ProtectedRoute allow={["admin"]}>
              <EmployeesPage />
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </Suspense>
    </ErrorBoundary>
  );
}
