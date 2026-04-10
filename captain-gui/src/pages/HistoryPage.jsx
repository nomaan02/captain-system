import { useState } from "react";
import useDashboardStore from "../stores/dashboardStore";

// TODO: Add independent data fetch — currently relies on DashboardPage WS being mounted first
import DataTable from "../components/shared/DataTable";
import StatusBadge from "../components/shared/StatusBadge";
import { formatTimestamp, formatCurrency } from "../utils/formatting";
import { createColumnHelper } from "@tanstack/react-table";

const columnHelper = createColumnHelper();

const signalColumns = [
  columnHelper.accessor("timestamp", { header: "Time", cell: (info) => formatTimestamp(info.getValue()) }),
  columnHelper.accessor("asset", { header: "Asset" }),
  columnHelper.accessor("direction", { header: "Dir" }),
  columnHelper.accessor("confidence_tier", { header: "Confidence" }),
  columnHelper.accessor("quality_score", { header: "Quality", cell: (info) => { const v = info.getValue(); return v != null ? v.toFixed(3) : "—"; } }),
  columnHelper.accessor("pnl", { header: "P&L", cell: (info) => { const v = info.getValue(); if (v == null) return "—"; return <span className={v >= 0 ? "text-[#10b981]" : "text-[#ef4444]"}>{formatCurrency(v)}</span>; } }),
  columnHelper.accessor("signal_id", { header: "ID", cell: (info) => <span className="text-[10px] text-[#64748b]">{info.getValue()}</span> }),
];

const tradeColumns = [
  columnHelper.accessor("timestamp", { header: "Time", cell: (info) => formatTimestamp(info.getValue()) }),
  columnHelper.accessor("asset", { header: "Asset" }),
  columnHelper.accessor("direction", { header: "Dir" }),
  columnHelper.accessor("outcome", { header: "Outcome", cell: (info) => <StatusBadge status={info.getValue()} /> }),
  columnHelper.accessor("pnl", { header: "P&L", cell: (info) => { const v = info.getValue(); if (v == null) return "—"; return <span className={v >= 0 ? "text-[#10b981]" : "text-[#ef4444]"}>{formatCurrency(v)}</span>; } }),
  columnHelper.accessor("account_id", { header: "Account" }),
];

const decayColumns = [
  columnHelper.accessor("timestamp", { header: "Time", cell: (info) => formatTimestamp(info.getValue()) }),
  columnHelper.accessor("asset", { header: "Asset" }),
  columnHelper.accessor("level", { header: "Level" }),
  columnHelper.accessor("cp_prob", { header: "CP Prob", cell: (info) => { const v = info.getValue(); return v != null ? `${(v * 100).toFixed(1)}%` : "—"; } }),
  columnHelper.accessor("cusum_stat", { header: "CUSUM", cell: (info) => { const v = info.getValue(); return v != null ? v.toFixed(4) : "—"; } }),
];

const aimColumns = [
  columnHelper.accessor("aim_id", { header: "AIM ID" }),
  columnHelper.accessor("aim_name", { header: "Name" }),
  columnHelper.accessor("status", { header: "Status" }),
  columnHelper.accessor("meta_weight", { header: "Weight", cell: (info) => { const v = info.getValue(); return v != null ? v.toFixed(4) : "—"; } }),
  columnHelper.accessor("modifier", { header: "Modifier", cell: (info) => { const v = info.getValue(); return v != null ? v.toFixed(4) : "—"; } }),
];

const eventColumns = [
  columnHelper.accessor("timestamp", { header: "Time", cell: (info) => formatTimestamp(info.getValue()) }),
  columnHelper.accessor("event_type", { header: "Type" }),
  columnHelper.accessor("asset", { header: "Asset" }),
  columnHelper.accessor("user_id", { header: "User" }),
  columnHelper.accessor("event_id", { header: "Event ID", cell: (info) => <span className="text-[10px] text-[#64748b]">{info.getValue()}</span> }),
];

const TABS = ["Signals", "Trade Outcomes", "Decay Events", "AIM Changes", "System Events"];

const HistoryPage = () => {
  const [activeTab, setActiveTab] = useState(0);
  const connected = useDashboardStore((s) => s.connected);
  const signalHistory = useDashboardStore((s) => s.signalHistory);
  const decayAlerts = useDashboardStore((s) => s.decayAlerts);
  const aimStates = useDashboardStore((s) => s.aimStates);

  if (!connected && (signalHistory || []).length === 0 && (decayAlerts || []).length === 0 && (aimStates || []).length === 0) {
    return (
      <div className="h-full bg-surface p-4 flex items-center justify-center">
        <div className="text-[#64748b] text-xs font-mono text-center">
          Connect to the dashboard first to load data
        </div>
      </div>
    );
  }

  const tabs = [
    { name: TABS[0], columns: signalColumns, data: signalHistory || [], search: "Search signals...", empty: "No signal history — clear signals from the dashboard to archive them here" },
    { name: TABS[1], columns: tradeColumns, data: [], search: "Search trades...", empty: "No historical data available. History is populated from completed trading sessions." },
    { name: TABS[2], columns: decayColumns, data: decayAlerts || [], search: "Search decay events...", empty: "No decay events" },
    { name: TABS[3], columns: aimColumns, data: aimStates || [], search: "Search AIMs...", empty: "No AIM data" },
    { name: TABS[4], columns: eventColumns, data: [], search: "Search events...", empty: "No historical data available. History is populated from completed trading sessions." },
  ];

  const current = tabs[activeTab];

  return (
    <div className="h-full bg-surface p-4 overflow-y-auto">
      <h1 className="text-lg font-mono text-white tracking-[2px] uppercase mb-6">History</h1>

      {/* Tab bar */}
      <div className="flex gap-2 mb-4">
        {tabs.map((tab, i) => (
          <button
            key={tab.name}
            onClick={() => setActiveTab(i)}
            className={`px-3 py-1.5 text-[10px] font-mono uppercase tracking-wider border border-solid transition-colors ${
              i === activeTab
                ? "bg-[rgba(16,185,129,0.15)] border-[rgba(16,185,129,0.3)] text-[#10b981]"
                : "bg-transparent border-[#2e4e5a] text-[#64748b] hover:bg-[rgba(100,116,139,0.05)]"
            }`}
          >
            {tab.name}
          </button>
        ))}
      </div>

      {/* Active table */}
      <div className="bg-surface-card border border-border-subtle p-3">
        <DataTable
          columns={current.columns}
          data={current.data}
          searchPlaceholder={current.search}
          emptyMessage={current.empty}
        />
      </div>
    </div>
  );
};

export default HistoryPage;
