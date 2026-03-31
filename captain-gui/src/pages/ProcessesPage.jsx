import { useEffect } from "react";
import useProcessesStore from "../stores/processesStore";
import StatusDot from "../components/shared/StatusDot";
import StatusBadge from "../components/shared/StatusBadge";
import DataTable from "../components/shared/DataTable";
import CollapsiblePanel from "../components/shared/CollapsiblePanel";
import { formatTime } from "../utils/formatting";
import { BLOCK_REGISTRY } from "../constants/blockRegistry";
import { createColumnHelper } from "@tanstack/react-table";

const columnHelper = createColumnHelper();

const strategyColumns = [
  columnHelper.accessor("asset", {
    header: "Asset",
    cell: (info) => <span className="font-bold">{info.getValue()}</span>,
  }),
  columnHelper.accessor("captain_status", {
    header: "Status",
    cell: (info) => <StatusBadge status={info.getValue()} />,
  }),
  columnHelper.accessor("m", {
    header: "m",
    cell: (info) => <span className="text-right block">{info.getValue() ?? "—"}</span>,
  }),
  columnHelper.accessor("k", {
    header: "k",
    cell: (info) => <span className="text-right block">{info.getValue() ?? "—"}</span>,
  }),
  columnHelper.accessor("oo", {
    header: "OO",
    cell: (info) => {
      const v = info.getValue();
      return <span className="text-right block">{v != null ? v.toFixed(4) : "—"}</span>;
    },
  }),
  columnHelper.accessor("sessions", {
    header: "Sessions",
    cell: (info) => {
      const v = info.getValue();
      return v && v.length > 0 ? v.join(", ") : "—";
    },
  }),
];

const TRIGGER_COLORS = {
  always_on: "bg-[rgba(16,185,129,0.15)] border-[rgba(16,185,129,0.3)] text-[#10b981]",
  session_open: "bg-[rgba(59,130,246,0.15)] border-[rgba(59,130,246,0.3)] text-[#3b82f6]",
  scheduled: "bg-[rgba(59,130,246,0.15)] border-[rgba(59,130,246,0.3)] text-[#3b82f6]",
  per_trade: "bg-[rgba(245,158,11,0.1)] border-[rgba(245,158,11,0.3)] text-[#f59e0b]",
  per_session: "bg-[rgba(245,158,11,0.1)] border-[rgba(245,158,11,0.3)] text-[#f59e0b]",
};
const DEFAULT_TRIGGER_COLOR = "bg-[rgba(100,116,139,0.1)] border-[#374151] text-[#64748b]";

const PROCESS_NAMES = {
  ONLINE: "CAPTAIN ONLINE",
  OFFLINE: "CAPTAIN OFFLINE",
  COMMAND: "CAPTAIN COMMAND",
};

const ACCENT_MAP = { ONLINE: "green", OFFLINE: "blue", COMMAND: "gray" };

const ProcessesPage = () => {
  const { processes, lockedStrategies, apiConnections, loading, error, startPolling, stopPolling } = useProcessesStore();

  useEffect(() => {
    startPolling();
    return () => stopPolling();
  }, []);

  const getProcessStatus = (role) => {
    const p = processes[role];
    return p ? p.status : "unknown";
  };

  return (
    <div className="h-screen bg-surface p-4 overflow-y-auto">
      <h1 className="text-lg font-mono text-white tracking-[2px] uppercase mb-6">Processes</h1>

      {/* Error banner */}
      {error && (
        <div className="mb-4 p-2 bg-[rgba(239,68,68,0.1)] border border-[rgba(239,68,68,0.3)] text-[#ef4444] text-xs font-mono">
          {error}
        </div>
      )}

      {/* Section 1: Process Health Cards */}
      <section className="mb-6">
        <h2 className="text-sm font-mono text-captain-green tracking-[1.5px] uppercase mb-3">Process Health</h2>
        <div className="grid grid-cols-3 gap-4">
          {["ONLINE", "OFFLINE", "COMMAND"].map((role) => {
            const p = processes[role] || {};
            const status = p.status || "unknown";
            return (
              <div key={role} className="bg-surface-card border border-border-subtle p-3 font-mono">
                <div className="flex items-center gap-2 mb-2">
                  <StatusDot status={status} />
                  <span className="text-sm text-white uppercase tracking-wider">{PROCESS_NAMES[role]}</span>
                </div>
                <div className="flex items-center justify-between">
                  <StatusBadge status={status} />
                  <span className="text-[10px] text-[#64748b]">{formatTime(p.timestamp)}</span>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* Section 2: Locked Strategies Table */}
      <section className="mb-6">
        <h2 className="text-sm font-mono text-captain-green tracking-[1.5px] uppercase mb-3">Locked Strategies</h2>
        <div className="bg-surface-card border border-border-subtle p-3">
          <DataTable
            columns={strategyColumns}
            data={lockedStrategies}
            searchPlaceholder="Search strategies..."
            emptyMessage="No locked strategies loaded"
          />
        </div>
      </section>

      {/* Section 3: Block Groups */}
      <section className="mb-6">
        <h2 className="text-sm font-mono text-captain-green tracking-[1.5px] uppercase mb-3">Block Registry</h2>
        <div className="flex flex-col gap-3">
          {["ONLINE", "OFFLINE", "COMMAND"].map((role) => {
            const blocks = BLOCK_REGISTRY[role] || [];
            const status = getProcessStatus(role);
            return (
              <CollapsiblePanel
                key={role}
                title={PROCESS_NAMES[role]}
                storageKey={`processes-${role}`}
                accentColor={ACCENT_MAP[role]}
                headerRight={
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-[#64748b] font-mono">{blocks.length} blocks</span>
                    <StatusDot status={status} size="4px" />
                  </div>
                }
              >
                <div className="flex flex-col">
                  {blocks.map((block) => (
                    <div key={block.id} className="flex items-start gap-3 py-2 border-b border-border-subtle last:border-b-0">
                      <StatusDot status={status} size="4px" pulse={false} />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-0.5">
                          <span className="text-xs text-white font-bold font-mono">{block.name}</span>
                          <span className={`px-1.5 py-0.5 text-[8px] font-mono border border-solid ${TRIGGER_COLORS[block.trigger] || DEFAULT_TRIGGER_COLOR}`}>
                            {block.triggerLabel}
                          </span>
                        </div>
                        <div className="text-[10px] text-[#94a3b8] font-mono mb-0.5">{block.description}</div>
                        <div className="text-[9px] text-[#64748b] font-mono">{block.sourceFile}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </CollapsiblePanel>
            );
          })}
        </div>
      </section>

      {/* Section 4: API Connections */}
      <section className="mb-6">
        <h2 className="text-sm font-mono text-captain-green tracking-[1.5px] uppercase mb-3">API Connections</h2>
        <div className="bg-surface-card border border-border-subtle p-3 font-mono text-xs">
          <div className="flex items-center gap-2">
            <StatusDot status={apiConnections.connected > 0 ? "ok" : "unknown"} />
            <span className="text-white">
              {apiConnections.connected}/{apiConnections.total} connected
            </span>
          </div>
        </div>
      </section>
    </div>
  );
};

export default ProcessesPage;
