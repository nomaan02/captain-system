import { useEffect } from "react";
import {
  Routes,
  Route,
  Navigate,
  Outlet,
  useNavigationType,
  useLocation,
} from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import TopBar from "./components/layout/TopBar";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import ModelsPage from "./pages/ModelsPage";
import ConfigPage from "./pages/ConfigPage";
import SettingsPage from "./pages/SettingsPage";
import HistoryPage from "./pages/HistoryPage";
import ReportsPage from "./pages/ReportsPage";
import ProcessesPage from "./pages/ProcessesPage";
import SystemOverviewPage from "./pages/SystemOverviewPage";
import ReplayPage from "./pages/ReplayPage";
import PseudotraderPage from "./pages/PseudotraderPage";

function RequireAuth({ children }) {
  const { isAuthenticated, loading } = useAuth();
  const location = useLocation();

  if (loading) return (
    <div className="h-screen w-full bg-[#080e0d] flex items-center justify-center">
      <div className="w-5 h-5 border-2 border-[#00ad74] border-t-transparent rounded-full animate-spin" role="status">
        <span className="sr-only">Loading</span>
      </div>
    </div>
  );
  if (!isAuthenticated) return <Navigate to="/login" state={{ from: location }} replace />;
  return children;
}

function AuthenticatedLayout() {
  return (
    <div className="h-screen w-full flex flex-col overflow-hidden">
      <div className="shrink-0">
        <TopBar />
      </div>
      <div className="flex-1 min-h-0 flex flex-col">
        <Outlet />
      </div>
    </div>
  );
}

function App() {
  const action = useNavigationType();
  const location = useLocation();
  const pathname = location.pathname;

  useEffect(() => {
    if (action !== "POP") {
      window.scrollTo(0, 0);
    }
  }, [action, pathname]);

  useEffect(() => {
    let title = "Captain Dashboard";
    let metaDescription = "Captain Trading Dashboard";

    switch (pathname) {
      case "/":
        title = "Captain Dashboard";
        metaDescription = "Captain Trading Dashboard";
        break;
      case "/settings":
        title = "Captain Settings";
        break;
      case "/history":
        title = "Captain History";
        break;
      case "/reports":
        title = "Captain Reports";
        break;
      case "/processes":
        title = "Captain Processes";
        break;
      case "/system":
        title = "Captain System Overview";
        break;
      case "/replay":
        title = "Captain Replay";
        break;
      case "/pseudotrader":
        title = "Captain Pseudotrader";
        break;
      case "/login":
        title = "Captain Login";
        break;
      case "/models":
        title = "Captain Models";
        break;
      case "/config":
        title = "Captain Config";
        break;
    }

    if (title) {
      document.title = title;
    }

    if (metaDescription) {
      const metaDescriptionTag = document.querySelector(
        'head > meta[name="description"]',
      );
      if (metaDescriptionTag) {
        metaDescriptionTag.content = metaDescription;
      }
    }
  }, [pathname]);

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth><AuthenticatedLayout /></RequireAuth>}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/models" element={<ModelsPage />} />
        <Route path="/config" element={<ConfigPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/reports" element={<ReportsPage />} />
        <Route path="/processes" element={<ProcessesPage />} />
        <Route path="/system" element={<SystemOverviewPage />} />
        <Route path="/replay" element={<ReplayPage />} />
        <Route path="/pseudotrader" element={<PseudotraderPage />} />
      </Route>
    </Routes>
  );
}
export default App;
