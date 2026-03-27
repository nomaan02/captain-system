import { BrowserRouter, Routes, Route } from "react-router-dom";
import { useEffect } from "react";
import { AuthProvider, useAuth } from "@/auth/AuthContext";
import { RequireRole } from "@/auth/RequireRole";
import { useWebSocket } from "@/ws/useWebSocket";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { AppLayout } from "@/layouts/AppLayout";
import { DashboardPage } from "@/pages/DashboardPage";
import { SystemOverviewPage } from "@/pages/SystemOverviewPage";
import { HistoryPage } from "@/pages/HistoryPage";
import { ReportsPage } from "@/pages/ReportsPage";
import { SettingsPage } from "@/pages/SettingsPage";

function ThemeApplier() {
  useEffect(() => {
    document.documentElement.classList.add("dark");
  }, []);
  return null;
}

function WsConnector() {
  const { user } = useAuth();
  useWebSocket(user.user_id);
  return null;
}

function NotFoundPage() {
  return (
    <div className="flex h-full items-center justify-center">
      <p className="text-gray-400">Page not found</p>
    </div>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <BrowserRouter>
          <ThemeApplier />
          <WsConnector />
          <Routes>
            <Route element={<AppLayout />}>
              <Route index element={<DashboardPage />} />
              <Route
                path="system"
                element={
                  <RequireRole
                    allowed={["ADMIN"]}
                    fallback={<p className="p-8 text-gray-400">Access denied</p>}
                  >
                    <SystemOverviewPage />
                  </RequireRole>
                }
              />
              <Route path="history" element={<HistoryPage />} />
              <Route path="reports" element={<ReportsPage />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="*" element={<NotFoundPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ErrorBoundary>
  );
}
