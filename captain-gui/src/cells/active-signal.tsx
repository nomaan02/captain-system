import { useCallback } from "react";
import { useDashboardStore } from "@/stores/dashboardStore";
import { useAuth } from "@/auth/AuthContext";
import { useWebSocket } from "@/ws/useWebSocket";
import { Panel } from "@/components/ui/panel";
import { Badge } from "@/components/ui/badge";
import { DataCell, DataCellRow } from "@/components/ui/data-cell";
import { ProximityBar } from "@/components/ui/proximity-bar";
import { ScrollArea } from "@/components/ui/scroll-area";
import { formatCurrency, formatNumber, formatTimestamp } from "@/utils/formatters";
import { Check, X, Clock } from "lucide-react";

export function ActiveSignalCell() {
  const signals = useDashboardStore((s) => s.pendingSignals);
  const positions = useDashboardStore((s) => s.openPositions);
  const lastAck = useDashboardStore((s) => s.lastAck);
  const removeSignal = useDashboardStore((s) => s.removeSignal);
  const { user } = useAuth();
  const { send } = useWebSocket(user.user_id);

  const handleAction = useCallback(
    (signalId: string, action: "TAKEN" | "SKIPPED", signal: (typeof signals)[0]) => {
      send({
        type: "command",
        command: "TAKEN_SKIPPED",
        action,
        signal_id: signalId,
        asset: signal.asset,
        direction: signal.direction,
        user_id: user.user_id,
      });
      removeSignal(signalId);
    },
    [send, removeSignal, user.user_id],
  );

  const hasSignals = signals.length > 0;
  const hasPositions = positions.length > 0;

  return (
    <Panel
      title="ACTIVE SIGNAL"
      accent={hasSignals ? "green" : "gray"}
      headerRight={
        <div className="flex items-center gap-1.5">
          {hasSignals && <Badge variant="go">GO</Badge>}
          {hasPositions && (
            <Badge variant="info">{positions.length} open</Badge>
          )}
        </div>
      }
    >
      <ScrollArea className="max-h-[320px]">
        {/* Pending signals */}
        {signals.length === 0 && positions.length === 0 && (
          <div className="flex items-center gap-2 py-4 text-[11px] text-dim">
            <Clock className="h-3 w-3" />
            No pending signals — waiting for next session
          </div>
        )}

        {signals.map((sig) => {
          const isLong = sig.direction === "LONG";
          return (
            <div
              key={sig.signal_id}
              className="mb-2 rounded-[3px] border p-2"
              style={{
                backgroundColor: isLong
                  ? "rgba(74, 222, 128, 0.05)"
                  : "rgba(248, 113, 113, 0.05)",
                borderColor: isLong
                  ? "rgba(74, 222, 128, 0.15)"
                  : "rgba(248, 113, 113, 0.15)",
              }}
            >
              {/* Signal header */}
              <div className="mb-1.5 flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <Badge variant={isLong ? "go" : "danger"}>
                    {sig.direction ?? "—"}
                  </Badge>
                  <span className="text-xs font-semibold text-foreground">
                    {sig.asset}
                  </span>
                  {sig.confidence_tier && (
                    <Badge variant="neutral" size="sm">
                      {sig.confidence_tier}
                    </Badge>
                  )}
                </div>
                <span className="text-[11px] text-ghost">
                  {formatTimestamp(sig.timestamp)}
                </span>
              </div>

              {/* Metrics row */}
              <DataCellRow className="mb-1.5 grid-cols-2">
                <DataCell
                  label="Quality"
                  value={formatNumber(sig.quality_score, 3)}
                />
                <DataCell
                  label="Confidence"
                  value={sig.confidence_tier ?? "—"}
                />
              </DataCellRow>

              {/* TAKEN / SKIPPED */}
              <div className="flex gap-1.5">
                <button
                  onClick={() => handleAction(sig.signal_id, "TAKEN", sig)}
                  className="flex flex-1 items-center justify-center gap-1 rounded-[3px] py-1 text-[11px] font-semibold transition-colors"
                  style={{
                    backgroundColor: "rgba(74, 222, 128, 0.1)",
                    border: "1px solid rgba(74, 222, 128, 0.25)",
                    color: "#4ade80",
                  }}
                >
                  <Check className="h-3 w-3" /> TAKEN
                </button>
                <button
                  onClick={() => handleAction(sig.signal_id, "SKIPPED", sig)}
                  className="flex flex-1 items-center justify-center gap-1 rounded-[3px] py-1 text-[11px] font-semibold transition-colors"
                  style={{
                    backgroundColor: "rgba(100, 116, 139, 0.1)",
                    border: "1px solid rgba(100, 116, 139, 0.2)",
                    color: "#94a3b8",
                  }}
                >
                  <X className="h-3 w-3" /> SKIP
                </button>
              </div>
            </div>
          );
        })}

        {/* Ack banner */}
        {lastAck?.command === "TAKEN_SKIPPED" && (
          <div
            className="mb-2 rounded-[3px] px-2 py-1 text-[11px]"
            style={{
              backgroundColor: "rgba(59, 130, 246, 0.1)",
              color: "#60a5fa",
            }}
          >
            {lastAck.action === "TAKEN" ? "Trade taken" : "Signal skipped"} — {lastAck.signal_id}
          </div>
        )}

        {/* Open positions */}
        {positions.map((pos) => {
          const pnl = pos.current_pnl ?? 0;
          const isLong = pos.direction === "LONG";
          const approxCurrent = pos.entry_price + pnl / (pos.contracts * 50 || 1);

          return (
            <div
              key={pos.signal_id}
              className="mb-2 rounded-[3px] border border-border-subtle bg-card-elevated p-2"
            >
              <div className="mb-1 flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <Badge variant={isLong ? "go" : "danger"} size="sm">
                    {pos.direction}
                  </Badge>
                  <span className="text-xs font-semibold text-foreground">
                    {pos.asset}
                  </span>
                  <span className="text-[11px] text-dim">
                    {pos.contracts} ct
                  </span>
                </div>
                <span
                  className="text-xs font-semibold"
                  style={{ color: pnl >= 0 ? "#4ade80" : "#f87171" }}
                >
                  {pnl >= 0 ? "+" : ""}
                  {formatCurrency(pnl)}
                </span>
              </div>

              <ProximityBar
                entry={pos.entry_price}
                tp={pos.tp_level}
                sl={pos.sl_level}
                current={approxCurrent}
                className="mb-1.5"
              />

              <DataCellRow className="grid-cols-4">
                <DataCell label="Entry" value={formatCurrency(pos.entry_price)} />
                <DataCell label="TP" value={formatCurrency(pos.tp_level)} valueColor="text-green" />
                <DataCell label="SL" value={formatCurrency(pos.sl_level)} valueColor="text-red" />
                <DataCell label="Account" value={pos.account_id} />
              </DataCellRow>
            </div>
          );
        })}
      </ScrollArea>
    </Panel>
  );
}
