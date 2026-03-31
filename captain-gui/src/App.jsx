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
    </Routes>
  );
}
export default App;
