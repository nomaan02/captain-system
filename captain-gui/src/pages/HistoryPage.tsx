import { useState, useEffect, useMemo } from "react";
import { createColumnHelper } from "@tanstack/react-table";
import { DataTable } from "@/components/DataTable";
import { api } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";
import { formatTimestamp, formatCurrency, formatPct } from "@/utils/formatters";
import { Badge } from "@/components/Badge";
import { priorityColor } from "@/utils/colors";
import type { NotificationPriority } from "@/utils/constants";

const TABS = ["Signals", "Trade Outcomes", "Decay Events", "AIM Changes", "System Events"] as const;
type Tab = (typeof TABS)[number];

// --- Column definitions ---

interface SignalRow {
  signal_id: string;
  asset: string;
  direction: string;
  confidence_tier: string;
  quality_score: number;
  timestamp: string;
}

interface TradeRow {
  signal_id: string;
  asset: string;
  direction: string;
  outcome: string;
  pnl: number;
  account_id: string;
  timestamp: string;
}

interface DecayRow {
  asset: string;
  cp_prob: number;
  cusum_stat: number;
  level: number;
  timestamp: string;
}

interface AimChangeRow {
  aim_id: string;
  aim_name: string;
  status: string;
  meta_weight: number;
  modifier: number;
}

interface SystemEventRow {
  event_id: string;
  event_type: string;
  asset: string;
  user_id: string;
  timestamp: string;
}

const sigCol = createColumnHelper<SignalRow>();
const signalColumns = [
  sigCol.accessor("timestamp", { header: "Time", cell: (i) => formatTimestamp(i.getValue()) }),
  sigCol.accessor("asset", { header: "Asset" }),
  sigCol.accessor("direction", { header: "Dir" }),
  sigCol.accessor("confidence_tier", { header: "Confidence" }),
  sigCol.accessor("quality_score", { header: "Quality", cell: (i) => (i.getValue() ?? 0).toFixed(3) }),
  sigCol.accessor("signal_id", { header: "ID", cell: (i) => <span className="font-mono text-[10px]">{i.getValue()}</span> }),
];

const tradeCol = createColumnHelper<TradeRow>();
const tradeColumns = [
  tradeCol.accessor("timestamp", { header: "Time", cell: (i) => formatTimestamp(i.getValue()) }),
  tradeCol.accessor("asset", { header: "Asset" }),
  tradeCol.accessor("direction", { header: "Dir" }),
  tradeCol.accessor("outcome", {
    header: "Outcome",
    cell: (i) => {
      const v = i.getValue();
      const cls = v === "TP_HIT" ? "bg-green-500/20 text-green-600" : v === "SL_HIT" ? "bg-red-500/20 text-red-600" : "";
      return <Badge label={v} className={cls} />;
    },
  }),
  tradeCol.accessor("pnl", { header: "P&L", cell: (i) => {
    const v = i.getValue();
    return <span className={v >= 0 ? "text-green-500" : "text-red-500"}>{formatCurrency(v)}</span>;
  }}),
  tradeCol.accessor("account_id", { header: "Account" }),
];

const decayCol = createColumnHelper<DecayRow>();
const decayColumns = [
  decayCol.accessor("timestamp", { header: "Time", cell: (i) => formatTimestamp(i.getValue()) }),
  decayCol.accessor("asset", { header: "Asset" }),
  decayCol.accessor("level", { header: "Level" }),
  decayCol.accessor("cp_prob", { header: "CP Prob", cell: (i) => formatPct(i.getValue() * 100) }),
  decayCol.accessor("cusum_stat", { header: "CUSUM", cell: (i) => i.getValue().toFixed(4) }),
];

const aimCol = createColumnHelper<AimChangeRow>();
const aimColumns = [
  aimCol.accessor("aim_id", { header: "AIM ID" }),
  aimCol.accessor("aim_name", { header: "Name" }),
  aimCol.accessor("status", { header: "Status" }),
  aimCol.accessor("meta_weight", { header: "Weight", cell: (i) => (i.getValue() ?? 0).toFixed(4) }),
  aimCol.accessor("modifier", { header: "Modifier", cell: (i) => (i.getValue() ?? 0).toFixed(4) }),
];

const sysCol = createColumnHelper<SystemEventRow>();
const sysColumns = [
  sysCol.accessor("timestamp", { header: "Time", cell: (i) => formatTimestamp(i.getValue()) }),
  sysCol.accessor("event_type", { header: "Type" }),
  sysCol.accessor("asset", { header: "Asset" }),
  sysCol.accessor("user_id", { header: "User" }),
  sysCol.accessor("event_id", { header: "Event ID", cell: (i) => <span className="font-mono text-[10px]">{i.getValue()}</span> }),
];

export function HistoryPage() {
  const [activeTab, setActiveTab] = useState<Tab>("Signals");
  const { user } = useAuth();
  const [dashData, setDashData] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    api.dashboard(user.user_id).then((d) => setDashData(d as any)).catch(() => {});
  }, [user.user_id]);

  const signalData: SignalRow[] = useMemo(() => (dashData as any)?.pending_signals ?? [], [dashData]);
  const decayData: DecayRow[] = useMemo(() => (dashData as any)?.decay_alerts ?? [], [dashData]);
  const aimData: AimChangeRow[] = useMemo(() => (dashData as any)?.aim_states ?? [], [dashData]);

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">History</h1>
      <div className="flex gap-1 border-b border-gray-200 dark:border-gray-700">
        {TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-3 py-2 text-sm transition-colors ${
              activeTab === tab
                ? "border-b-2 border-captain-blue font-medium text-captain-blue"
                : "text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
            }`}
          >
            {tab}
          </button>
        ))}
      </div>
      <div className="panel">
        {activeTab === "Signals" && (
          <DataTable data={signalData} columns={signalColumns} searchPlaceholder="Search signals..." />
        )}
        {activeTab === "Trade Outcomes" && (
          <DataTable data={[] as TradeRow[]} columns={tradeColumns} searchPlaceholder="Search trades..." />
        )}
        {activeTab === "Decay Events" && (
          <DataTable data={decayData} columns={decayColumns} searchPlaceholder="Search decay events..." />
        )}
        {activeTab === "AIM Changes" && (
          <DataTable data={aimData} columns={aimColumns} searchPlaceholder="Search AIMs..." />
        )}
        {activeTab === "System Events" && (
          <DataTable data={[] as SystemEventRow[]} columns={sysColumns} searchPlaceholder="Search events..." />
        )}
      </div>
    </div>
  );
}
