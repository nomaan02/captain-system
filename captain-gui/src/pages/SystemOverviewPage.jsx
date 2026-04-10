import { useEffect, useState, useCallback } from "react";
import useSystemOverviewStore from "../stores/systemOverviewStore";
import api from "../api/client";
import StatusDot from "../components/shared/StatusDot";
import StatusBadge from "../components/shared/StatusBadge";
import StatBox from "../components/shared/StatBox";
import DataTable from "../components/shared/DataTable";
import { formatTimestamp, formatTimeAgo } from "../utils/formatting";
import { createColumnHelper } from "@tanstack/react-table";
import { RadarChart, PolarGrid, PolarAngleAxis, Radar, ResponsiveContainer } from "recharts";

const columnHelper = createColumnHelper();

const SEVERITY_COLORS = {
  P1_CRITICAL: { bg: "bg-[rgba(239,68,68,0.15)]", border: "border-[rgba(239,68,68,0.3)]", text: "text-[#ef4444]" },
  P2_HIGH: { bg: "bg-[rgba(255,136,0,0.15)]", border: "border-[rgba(255,136,0,0.3)]", text: "text-[#ff8800]" },
  P3_MEDIUM: { bg: "bg-[rgba(245,158,11,0.1)]", border: "border-[rgba(245,158,11,0.3)]", text: "text-[#f59e0b]" },
  P4_LOW: { bg: "bg-[rgba(100,116,139,0.1)]", border: "border-[#374151]", text: "text-[#64748b]" },
};

const incidentColumns = [
  columnHelper.accessor("timestamp", { header: "Time", cell: (info) => formatTimestamp(info.getValue()) }),
  columnHelper.accessor("severity", {
    header: "Severity",
    cell: (info) => {
      const v = info.getValue();
      const c = SEVERITY_COLORS[v] || SEVERITY_COLORS.P4_LOW;
      return <span className={`px-1.5 py-0.5 text-[9px] font-mono border border-solid ${c.bg} ${c.border} ${c.text}`}>{v}</span>;
    },
  }),
  columnHelper.accessor("type", { header: "Type" }),
  columnHelper.accessor("component", { header: "Component" }),
  columnHelper.accessor("status", { header: "Status" }),
  columnHelper.accessor("details", {
    header: "Details",
    cell: (info) => {
      const v = info.getValue();
      return v ? <span className="truncate max-w-[200px] block">{v}</span> : "—";
    },
  }),
];

const concentrationColumns = [
  columnHelper.accessor("asset", { header: "Asset" }),
  columnHelper.accessor("direction", {
    header: "Direction",
    cell: (info) => {
      const v = info.getValue();
      const isLong = v === "LONG";
      return (
        <span className={`px-1.5 py-0.5 text-[9px] font-mono border border-solid ${
          isLong
            ? "bg-[rgba(16,185,129,0.15)] border-[rgba(16,185,129,0.3)] text-[#10b981]"
            : "bg-[rgba(239,68,68,0.15)] border-[rgba(239,68,68,0.3)] text-[#ef4444]"
        }`}>
          {v}
        </span>
      );
    },
  }),
  columnHelper.accessor("total_contracts", { header: "Contracts" }),
  columnHelper.accessor("user_count", { header: "Users" }),
];

const GOVERNANCE_DATA = [
  { event: "SOD Reset", frequency: "Daily 19:00 ET", status: "Automated" },
  { event: "Decay Detection", frequency: "Per-session", status: "Automated" },
  { event: "AIM Rebalance", frequency: "Weekly", status: "Automated" },
  { event: "Kelly Update", frequency: "Per-trade", status: "Automated" },
  { event: "Strategy Injection Check", frequency: "Monthly", status: "Admin review" },
  { event: "P1/P2 Rerun (Level 3)", frequency: "On decay trigger", status: "Admin review" },
  { event: "System Health Diagnostic", frequency: "8h", status: "Automated" },
  { event: "Contract Roll", frequency: "Quarterly", status: "Admin confirm" },
];

const CONTAINERS = ["questdb", "redis", "captain-offline", "captain-online", "captain-command", "nginx"];

const PanelCard = ({ title, children, headerRight }) => (
  <div className="bg-surface-card border border-border-subtle p-3">
    <div className="flex items-center justify-between mb-3">
      <h3 className="text-sm font-mono text-captain-green tracking-[1.5px] uppercase">{title}</h3>
      {headerRight}
    </div>
    {children}
  </div>
);

const KeyValueList = ({ data, maxHeight }) => {
  if (!data || Object.keys(data).length === 0) return <div className="text-[#64748b] text-xs font-mono py-4 text-center">No data</div>;
  return (
    <div className={`font-mono text-xs ${maxHeight ? `max-h-[${maxHeight}] overflow-y-auto` : ""}`} style={maxHeight ? { maxHeight } : undefined}>
      {Object.entries(data).map(([key, value]) => (
        <div key={key} className="flex items-center justify-between py-1 border-b border-border-subtle last:border-b-0">
          <span className="text-[#94a3b8]">{key}</span>
          <span className="text-white">{String(value ?? "—")}</span>
        </div>
      ))}
    </div>
  );
};

const SystemOverviewPage = () => {
  const { overview, loading, error, fetch: fetchOverview } = useSystemOverviewStore();
  const [healthData, setHealthData] = useState(null);
  const [statusData, setStatusData] = useState(null);
  const [healthError, setHealthError] = useState(null);

  useEffect(() => {
    fetchOverview();
  }, []);

  // Circuit breaker independent fetch with 30s auto-refresh
  const fetchHealth = useCallback(async () => {
    try {
      const data = await api.health();
      setHealthData(data);
      setHealthError(null);
    } catch (err) {
      setHealthError(err.message);
    }
  }, []);

  useEffect(() => {
    fetchHealth();
    const id = setInterval(fetchHealth, 30000);
    return () => clearInterval(id);
  }, [fetchHealth]);

  // Deployment + Reconciliation independent fetch
  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const data = await api.status();
        setStatusData(data);
      } catch (_) {}
    };
    fetchStatus();
  }, []);

  // Admin check (hardcoded since no auth context exists)
  const isAdmin = true;
  if (!isAdmin) {
    return (
      <div className="h-full bg-surface p-4 flex items-center justify-center">
        <div className="text-[#64748b] text-sm font-mono">Access restricted to administrators.</div>
      </div>
    );
  }

  if (loading && !overview) {
    return (
      <div className="h-full bg-surface p-4">
        <h1 className="text-lg font-mono text-white tracking-[2px] uppercase mb-6">System Overview</h1>
        <div className="text-[#64748b] text-xs font-mono py-8 text-center">Loading system overview...</div>
      </div>
    );
  }

  const o = overview || {};

  // Radar chart data
  const radarData = (o.diagnostic_health || []).map((d) => ({
    dimension: d.dimension?.replace(/_/g, " ") || "",
    score: d.score || 0,
  }));

  // Signal quality
  const sq = o.signal_quality || {};
  const passRate = sq.pass_rate != null ? (sq.pass_rate * 100).toFixed(1) : null;
  const passColor = passRate >= 70 ? "text-[#10b981]" : passRate >= 40 ? "text-[#f59e0b]" : "text-[#ef4444]";
  const barColor = passRate >= 70 ? "bg-[#10b981]" : passRate >= 40 ? "bg-[#f59e0b]" : "bg-[#ef4444]";

  return (
    <div className="h-full bg-surface p-4 overflow-y-auto">
      <h1 className="text-lg font-mono text-white tracking-[2px] uppercase mb-6">System Overview</h1>

      {error && (
        <div className="mb-4 p-2 bg-[rgba(239,68,68,0.1)] border border-[rgba(239,68,68,0.3)] text-[#ef4444] text-xs font-mono">
          {error}
        </div>
      )}

      {/* Row 1: System Health + Network Concentration */}
      <div className="grid grid-cols-2 gap-4 mb-4">
        {/* 4.1 System Health */}
        <PanelCard title="System Health">
          {radarData.length > 0 ? (
            <>
              <div className="h-[200px] mb-3">
                <ResponsiveContainer width="100%" height="100%">
                  <RadarChart data={radarData}>
                    <PolarGrid stroke="#1e293b" />
                    <PolarAngleAxis dataKey="dimension" tick={{ fill: "#94a3b8", fontSize: 9, fontFamily: "JetBrains Mono" }} />
                    <Radar dataKey="score" stroke="#0faf7a" fill="#0faf7a" fillOpacity={0.3} />
                  </RadarChart>
                </ResponsiveContainer>
              </div>
              <div className="grid grid-cols-2 gap-2">
                {(o.diagnostic_health || []).map((d) => (
                  <div key={d.dimension} className="flex items-center justify-between text-xs font-mono">
                    <span className="text-[#94a3b8]">{d.dimension?.replace(/_/g, " ")}</span>
                    <StatusBadge status={d.status} />
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="text-[#64748b] text-xs font-mono py-4 text-center">No diagnostic data</div>
          )}
        </PanelCard>

        {/* 4.2 Network Concentration */}
        <PanelCard
          title="Network Concentration"
          headerRight={
            <span className="text-[10px] text-[#64748b] font-mono">
              {(o.network_concentration?.exposures || []).length} positions
            </span>
          }
        >
          <DataTable
            columns={concentrationColumns}
            data={o.network_concentration?.exposures || []}
            searchPlaceholder="Search exposures..."
            emptyMessage="No exposure data"
          />
        </PanelCard>
      </div>

      {/* Row 2: Signal Quality + Capacity + Compliance */}
      <div className="grid grid-cols-3 gap-4 mb-4">
        {/* 4.3 Signal Quality */}
        <PanelCard title="Signal Quality">
          {sq.total_evaluated != null ? (
            <>
              <div className="grid grid-cols-3 gap-2 mb-3">
                <StatBox label="Total Evaluated" value={sq.total_evaluated} />
                <StatBox label="Passed" value={sq.passed} color="text-[#10b981]" />
                <StatBox label="Pass Rate" value={passRate != null ? `${passRate}%` : "—"} color={passColor} />
              </div>
              <div>
                <div className="text-[9px] text-[#64748b] font-mono mb-1">7-day pass rate</div>
                <div className="w-full bg-[rgba(226,232,240,0.06)] border border-[rgba(226,232,240,0.1)] h-[10px] overflow-hidden">
                  <div className={`h-full ${barColor} transition-all`} style={{ width: `${passRate || 0}%` }} />
                </div>
              </div>
            </>
          ) : (
            <div className="text-[#64748b] text-xs font-mono py-4 text-center">No signal quality data</div>
          )}
        </PanelCard>

        {/* 4.4 Capacity Utilization */}
        <PanelCard title="Capacity Utilization">
          <KeyValueList data={o.capacity_state} />
        </PanelCard>

        {/* 4.5 Compliance Status */}
        <PanelCard
          title="Compliance Status"
          headerRight={o.compliance_gate?.execution_mode && <StatusBadge status={o.compliance_gate.execution_mode} />}
        >
          {o.compliance_gate?.requirements ? (
            <KeyValueList data={o.compliance_gate.requirements} />
          ) : (
            <div className="text-[#64748b] text-xs font-mono py-4 text-center">No active requirements</div>
          )}
        </PanelCard>
      </div>

      {/* Row 3: Action Queue + Data Quality */}
      <div className="grid grid-cols-2 gap-4 mb-4">
        {/* 4.6 Action Queue */}
        <PanelCard
          title="Action Queue"
          headerRight={
            <span className="text-[10px] text-[#64748b] font-mono">
              {(o.action_queue || []).length} open
            </span>
          }
        >
          {(o.action_queue || []).length > 0 ? (
            <div className="max-h-[300px] overflow-y-auto">
              {o.action_queue.map((item, i) => (
                <div key={i} className="flex items-start justify-between py-2 border-b border-border-subtle last:border-b-0">
                  <div className="flex items-start gap-2">
                    <StatusBadge status={item.status} />
                    <div>
                      <div className="text-xs text-white font-mono font-bold">{item.dimension}</div>
                      {item.details && <div className="text-[10px] text-[#94a3b8] font-mono mt-0.5">{item.details}</div>}
                    </div>
                  </div>
                  <span className="text-[9px] text-[#64748b] font-mono whitespace-nowrap ml-2">{formatTimestamp(item.timestamp)}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-[#64748b] text-xs font-mono py-4 text-center">No open actions</div>
          )}
        </PanelCard>

        {/* 4.7 Data Quality */}
        <PanelCard title="Data Quality">
          {(o.data_quality?.assets || []).length > 0 ? (
            <div>
              {o.data_quality.assets.map((a) => {
                const isStale = !a.last_data_update || (Date.now() - new Date(a.last_data_update).getTime()) > 5 * 60 * 1000;
                return (
                  <div key={a.asset_id} className="flex items-center justify-between py-1.5 border-b border-border-subtle last:border-b-0">
                    <div className="flex items-center gap-2">
                      <StatusDot status={isStale ? "error" : "ok"} />
                      <span className="text-xs text-white font-mono font-bold">{a.asset_id}</span>
                      <span className="text-[10px] text-[#94a3b8] font-mono">{a.status}</span>
                    </div>
                    <span className="text-[10px] text-[#64748b] font-mono">{formatTimeAgo(a.last_data_update)}</span>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="text-[#64748b] text-xs font-mono py-4 text-center">No asset data</div>
          )}
        </PanelCard>
      </div>

      {/* Row 4: Circuit Breaker + Deployment */}
      <div className="grid grid-cols-2 gap-4 mb-4">
        {/* 4.8 Circuit Breaker / System Status */}
        <PanelCard
          title="Circuit Breaker"
          headerRight={
            <button
              onClick={fetchHealth}
              className="px-2 py-1 text-[9px] font-mono border border-solid bg-transparent border-[#2e4e5a] text-[#64748b] cursor-pointer hover:bg-[rgba(100,116,139,0.05)] transition-colors"
            >
              Refresh
            </button>
          }
        >
          {healthError && <div className="text-[#ef4444] text-xs font-mono mb-2">{healthError}</div>}
          {healthData ? (
            <div className="grid grid-cols-3 gap-2">
              <StatBox label="System" value={healthData.status || "—"} />
              <StatBox label="Circuit Breaker" value={healthData.circuit_breaker || "—"} />
              <StatBox label="Uptime" value={healthData.uptime_seconds ? `${(healthData.uptime_seconds / 3600).toFixed(1)}h` : "—"} />
              <StatBox label="Active Users" value={healthData.active_users ?? "—"} />
              <StatBox label="API Connections" value={healthData.api_connections != null ? String(healthData.api_connections) : "—"} />
              <StatBox label="Last Signal" value={healthData.last_signal_time ? formatTimestamp(healthData.last_signal_time) : "—"} />
            </div>
          ) : (
            <div className="text-[#64748b] text-xs font-mono py-4 text-center">Loading health data...</div>
          )}
        </PanelCard>

        {/* 4.9 Deployment Status */}
        <PanelCard title="Deployment Status">
          <div className="grid grid-cols-3 gap-2">
            {CONTAINERS.map((name) => {
              const proc = statusData?.processes || {};
              const infra = ["questdb", "redis", "nginx"];
              const status = proc[name]?.status || (infra.includes(name) ? "ok" : "unknown");
              return (
                <div key={name} className="flex items-center gap-2 py-1.5">
                  <StatusDot status={status} />
                  <span className="text-xs text-white font-mono">{name}</span>
                </div>
              );
            })}
          </div>
        </PanelCard>
      </div>

      {/* Row 5: Constraints + Reconciliation + Performance */}
      <div className="grid grid-cols-3 gap-4 mb-4">
        {/* 4.10 Active Constraints */}
        <PanelCard title="Active Constraints">
          <KeyValueList data={o.system_params} maxHeight="200px" />
          {(!o.system_params || Object.keys(o.system_params).length === 0) && (
            <div className="text-[#64748b] text-xs font-mono py-4 text-center">No constraints loaded</div>
          )}
        </PanelCard>

        {/* 4.11 Reconciliation Status */}
        <PanelCard title="Reconciliation Status">
          {statusData?.processes ? (
            <div>
              {Object.entries(statusData.processes).map(([role, info]) => (
                <div key={role} className="flex items-center gap-2 py-1.5 border-b border-border-subtle last:border-b-0">
                  <StatusDot status={info.status || "unknown"} />
                  <span className="text-xs text-white font-mono uppercase">{role}</span>
                  <span className="text-[10px] text-[#64748b] font-mono ml-auto">{info.status}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-[#64748b] text-xs font-mono py-4 text-center">No process status available</div>
          )}
        </PanelCard>

        {/* 4.12 Performance */}
        <PanelCard title="Performance">
          <div className="text-[#64748b] text-xs font-mono py-4 text-center">
            Performance data available via RPT-02 / RPT-10
          </div>
        </PanelCard>
      </div>

      {/* Row 6: Model Validation + Governance + Capacity Recs */}
      <div className="grid grid-cols-3 gap-4 mb-4">
        {/* 4.13 Model Validation */}
        <PanelCard title="Model Validation">
          <div className="text-[#64748b] text-xs font-mono py-4 text-center">
            AIM model validation metrics are available via RPT-04 (AIM Effectiveness Report). Decay detection monitors model drift continuously.
          </div>
        </PanelCard>

        {/* 4.14 Governance Schedule */}
        <PanelCard title="Governance Schedule">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border-subtle">
                <th className="text-left text-[10px] text-[#94a3b8] uppercase tracking-wider font-mono font-normal px-2 py-1">Event</th>
                <th className="text-left text-[10px] text-[#94a3b8] uppercase tracking-wider font-mono font-normal px-2 py-1">Frequency</th>
                <th className="text-left text-[10px] text-[#94a3b8] uppercase tracking-wider font-mono font-normal px-2 py-1">Status</th>
              </tr>
            </thead>
            <tbody>
              {GOVERNANCE_DATA.map((row) => (
                <tr key={row.event} className="border-b border-border-subtle last:border-b-0">
                  <td className="text-xs text-white font-mono px-2 py-1.5">{row.event}</td>
                  <td className="text-xs text-[#94a3b8] font-mono px-2 py-1.5">{row.frequency}</td>
                  <td className="px-2 py-1.5">
                    <StatusBadge status={row.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </PanelCard>

        {/* 4.15 Capacity Recommendations */}
        <PanelCard title="Capacity Recommendations">
          <div className="text-[#64748b] text-xs font-mono py-4 text-center">
            Capacity recommendations are computed by Online B9 (Capacity Evaluator). Data appears here when capacity evaluations run at session boundaries.
          </div>
        </PanelCard>
      </div>

      {/* Row 7: Incident Log (full width) */}
      <div className="mb-4">
        <PanelCard
          title="Incident Log"
          headerRight={
            <span className="text-[10px] text-[#64748b] font-mono">
              {(o.incident_log || []).length} incidents
            </span>
          }
        >
          <DataTable
            columns={incidentColumns}
            data={o.incident_log || []}
            searchPlaceholder="Search incidents..."
            emptyMessage="No incidents recorded"
          />
        </PanelCard>
      </div>

      {/* Row 8: Admin Decision Log + Stress Test + Version History */}
      <div className="grid grid-cols-3 gap-4 mb-4">
        {/* 4.17 Admin Decision Log */}
        <PanelCard title="Admin Decision Log">
          <div className="text-[#64748b] text-xs font-mono py-4 text-center">
            Admin decisions (strategy adoptions, AIM toggles, TSM switches) are logged in P3-D17 session event log. View in History &rarr; System Events tab.
          </div>
        </PanelCard>

        {/* 4.18 Stress Test Review */}
        <PanelCard title="Stress Test Review">
          <div className="text-[#64748b] text-xs font-mono py-4 text-center">
            Stress test results will be available after Phase 7 validation. Generate via RPT-08 (Regime Calibration).
          </div>
        </PanelCard>

        {/* 4.19 Version History */}
        <PanelCard title="Version History">
          <div className="flex items-start gap-3 py-2">
            <span className="px-2 py-0.5 text-[10px] font-mono bg-[rgba(59,130,246,0.15)] border border-[rgba(59,130,246,0.3)] text-[#3b82f6] whitespace-nowrap">
              v1.0.0
            </span>
            <div>
              <div className="text-[10px] text-[#64748b] font-mono">2026-03-14</div>
              <div className="text-xs text-[#94a3b8] font-mono mt-0.5">Initial Captain Function release — V1+V2+V3 unified build</div>
            </div>
          </div>
        </PanelCard>
      </div>
    </div>
  );
};

export default SystemOverviewPage;
