import { useState, useEffect } from "react";
import useDashboardStore from "../stores/dashboardStore";

const SettingsPage = () => {
  const selectedAccount = useDashboardStore((s) => s.selectedAccount);
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem("captain-theme") || "dark";
  });

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    localStorage.setItem("captain-theme", next);
  };

  return (
    <div className="h-screen bg-surface p-4 overflow-y-auto">
      <h1 className="text-lg font-mono text-white tracking-[2px] uppercase mb-6">
        Settings
      </h1>

      {/* User Information */}
      <section className="mb-6">
        <h2 className="text-sm font-mono text-captain-green tracking-[1.5px] uppercase mb-3">
          User Information
        </h2>
        <div className="bg-surface-card border border-border-subtle p-3 font-mono text-xs">
          <div className="flex items-center justify-between py-1.5 border-b border-border-subtle">
            <span className="text-[#64748b] uppercase tracking-wider">Account</span>
            <span className="text-white">{selectedAccount || "Loading..."}</span>
          </div>
          <div className="flex items-center justify-between py-1.5">
            <span className="text-[#64748b] uppercase tracking-wider">Role</span>
            <span className="text-white">ADMIN</span>
          </div>
        </div>
      </section>

      {/* Appearance */}
      <section className="mb-6">
        <h2 className="text-sm font-mono text-captain-green tracking-[1.5px] uppercase mb-3">
          Appearance
        </h2>
        <div className="bg-surface-card border border-border-subtle p-3 font-mono text-xs">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-white mb-1">Theme</div>
              <div className="text-[#64748b]">Current: {theme}</div>
            </div>
            <button
              onClick={toggleTheme}
              className="px-3 py-1.5 text-[10px] font-mono border border-solid cursor-pointer bg-[rgba(16,185,129,0.15)] border-[rgba(16,185,129,0.3)] text-[#10b981] hover:bg-[rgba(16,185,129,0.25)] transition-colors"
            >
              {theme === "dark" ? "Switch to Light" : "Switch to Dark"}
            </button>
          </div>
        </div>
      </section>
    </div>
  );
};

export default SettingsPage;
