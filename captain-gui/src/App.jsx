import { useEffect } from "react";
import {
  Routes,
  Route,
  useNavigationType,
  useLocation,
} from "react-router-dom";
import DashboardPage from "./pages/DashboardPage";
import ModelsPage from "./pages/ModelsPage";
import ConfigPage from "./pages/ConfigPage";
import SettingsPage from "./pages/SettingsPage";
import HistoryPage from "./pages/HistoryPage";
import ReportsPage from "./pages/ReportsPage";
import ProcessesPage from "./pages/ProcessesPage";
import SystemOverviewPage from "./pages/SystemOverviewPage";
import ReplayPage from "./pages/ReplayPage";

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
      <Route path="/" element={<DashboardPage />} />
      <Route path="/models" element={<ModelsPage />} />
      <Route path="/config" element={<ConfigPage />} />
      <Route path="/settings" element={<SettingsPage />} />
      <Route path="/history" element={<HistoryPage />} />
      <Route path="/reports" element={<ReportsPage />} />
      <Route path="/processes" element={<ProcessesPage />} />
      <Route path="/system" element={<SystemOverviewPage />} />
      <Route path="/replay" element={<ReplayPage />} />
    </Routes>
  );
}
export default App;
