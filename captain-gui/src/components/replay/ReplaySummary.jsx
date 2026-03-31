import useReplayStore from "../../stores/replayStore";
import { formatCurrency } from "../../utils/formatting";
import api from "../../api/client";

const ReplaySummary = () => {
  const status = useReplayStore((s) => s.status);
  const summary = useReplayStore((s) => s.summary);
  const replayId = useReplayStore((s) => s.replayId);
  const assetResults = useReplayStore((s) => s.assetResults);
  const assetOrder = useReplayStore((s) => s.assetOrder);
  const config = useReplayStore((s) => s.config);

  const isComplete = status === "complete";
  const hasError = summary?.error;

  // Helper to get actual PnL for a trade (pnl_per_contract * contracts)
  const getTradePnl = (ar) => {
    const ppc = ar?.exitResult?.pnl_per_contract ?? ar?.exitResult?.pnl ?? 0;
    const cts = ar?.sizing?.contracts ?? 0;
    return ppc * cts;
  };

  // Compute stats from asset results
  const trades = assetOrder
    .map((a) => ({ asset: a, ...assetResults[a] }))
    .filter((t) => (t.sizing?.contracts ?? 0) > 0 && (t.exitResult || t.status === "exited"));

  const wins = trades.filter((t) => getTradePnl(t) >= 0);
  const losses = trades.filter((t) => getTradePnl(t) < 0);
  const blockedCount = assetOrder.filter((a) => (assetResults[a]?.sizing?.contracts ?? 0) === 0 && assetResults[a]?.exitResult).length;
  const errorCount = assetOrder.filter((a) => assetResults[a]?.status === "error").length;

  // Use summary.total_pnl if available (from replay_complete), else compute
  const totalPnl = summary?.total_pnl ?? trades.reduce((sum, t) => sum + getTradePnl(t), 0);

  const tradesSorted = [...trades].sort((a, b) => getTradePnl(b) - getTradePnl(a));

  const handleSave = async () => {
    if (!replayId) return;
    try {
      await api.replaySave(replayId);
    } catch (err) {
      console.error("Replay save failed:", err);
    }
  };

  const handleWhatIf = async () => {
    try {
      const overrides = {
        user_capital: config.capital,
        budget_divisor: config.budgetDivisor,
        risk_goal: config.riskGoal,
        max_positions: config.maxPositions,
        max_contracts: config.maxContracts,
        tp_multiple: config.tpMultiple,
        sl_multiple: config.slMultiple,
        cb_enabled: config.cbEnabled,
        mdd_limit: config.mddLimit,
        mll_limit: config.mllLimit,
      };
      const result = await api.replayWhatIf(overrides);
      useReplayStore.getState().setComparison(result);
    } catch (err) {
      console.error("What-if failed:", err);
    }
  };

  if (!isComplete && status !== "running" && status !== "paused") {
    return (
      <div data-testid="replay-summary" className="p-3">
        <div className="text-[9px] uppercase tracking-[1px] text-[#0faf7a] font-mono mb-2">Summary</div>
        <div className="text-[10px] text-[#64748b] font-mono text-center py-4">
          Run a replay to see results
        </div>
      </div>
    );
  }

  if (status === "running" || status === "paused") {
    return (
      <div data-testid="replay-summary" className="p-3">
        <div className="text-[9px] uppercase tracking-[1px] text-[#0faf7a] font-mono mb-2">Summary</div>
        <div className="text-[10px] text-[#64748b] font-mono text-center py-4">
          Replay in progress...
        </div>
        <div className="space-y-1 mt-2">
          <div className="flex justify-between text-[9px] font-mono">
            <span className="text-[#64748b]">Assets processed</span>
            <span className="text-[#e2e8f0]">{assetOrder.length}</span>
          </div>
          <div className="flex justify-between text-[9px] font-mono">
            <span className="text-[#64748b]">Trades</span>
            <span className="text-[#e2e8f0]">{trades.length}</span>
          </div>
          <div className="flex justify-between text-[9px] font-mono">
            <span className="text-[#64748b]">Running P&L</span>
            <span className={`${totalPnl >= 0 ? "text-[#10b981]" : "text-[#ef4444]"}`}>
              {formatCurrency(totalPnl, { showSign: true })}
            </span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div data-testid="replay-summary" className="p-3 space-y-3">
      <div className="text-[9px] uppercase tracking-[1px] text-[#0faf7a] font-mono">Summary</div>

      {/* Error state */}
      {hasError && (
        <div className="bg-[rgba(239,68,68,0.1)] border border-[rgba(239,68,68,0.25)] p-2 text-[9px] text-[#ef4444] font-mono">
          {summary.error}
        </div>
      )}

      {/* Total PnL */}
      <div className="text-center py-2">
        <div className="text-[7px] uppercase tracking-[0.5px] text-[#64748b] font-mono mb-1">Total P&L</div>
        <div
          data-testid="replay-summary-pnl"
          className={`text-[22px] font-mono font-semibold ${totalPnl >= 0 ? "text-[#10b981]" : "text-[#ef4444]"}`}
        >
          {formatCurrency(totalPnl, { showSign: true })}
        </div>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 gap-x-3 gap-y-1">
        <div className="flex justify-between text-[9px] font-mono">
          <span className="text-[#64748b]">Wins</span>
          <span className="text-[#10b981]">{wins.length}</span>
        </div>
        <div className="flex justify-between text-[9px] font-mono">
          <span className="text-[#64748b]">Losses</span>
          <span className="text-[#ef4444]">{losses.length}</span>
        </div>
        <div className="flex justify-between text-[9px] font-mono">
          <span className="text-[#64748b]">Trades</span>
          <span className="text-[#e2e8f0]">{trades.length}</span>
        </div>
        <div className="flex justify-between text-[9px] font-mono">
          <span className="text-[#64748b]">Blocked</span>
          <span className="text-[#64748b]">{blockedCount}</span>
        </div>
        <div className="flex justify-between text-[9px] font-mono">
          <span className="text-[#64748b]">Errors</span>
          <span className="text-[#ef4444]">{errorCount}</span>
        </div>
        <div className="flex justify-between text-[9px] font-mono">
          <span className="text-[#64748b]">Win Rate</span>
          <span className="text-[#e2e8f0]">
            {trades.length > 0 ? `${Math.round((wins.length / trades.length) * 100)}%` : "--"}
          </span>
        </div>
      </div>

      {/* Trades table */}
      {tradesSorted.length > 0 && (
        <div className="border-t border-[#1e293b] pt-2">
          <div className="text-[8px] uppercase tracking-[0.5px] text-[#64748b] font-mono mb-1">All Trades</div>
          <div className="max-h-[160px] overflow-y-auto">
            {tradesSorted.map((t) => {
              const pnl = getTradePnl(t);
              const reason = t.exitResult?.exit_reason || t.exitResult?.reason || "--";
              return (
                <div key={t.asset} className="flex items-center justify-between py-[2px] text-[9px] font-mono border-b border-[#1e293b]">
                  <div className="flex items-center gap-2">
                    <span className="text-[#06b6d4]">{t.asset}</span>
                    <span className={`text-[7px] px-1 border border-solid ${
                      reason === "TP" || reason === "TP_HIT"
                        ? "border-[rgba(16,185,129,0.3)] text-[#10b981]"
                        : "border-[rgba(239,68,68,0.3)] text-[#ef4444]"
                    }`}>
                      {reason}
                    </span>
                  </div>
                  <span className={pnl >= 0 ? "text-[#10b981]" : "text-[#ef4444]"}>
                    {formatCurrency(pnl, { showSign: true })}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Action buttons */}
      <div className="flex gap-2 pt-2 border-t border-[#1e293b]">
        <button
          data-testid="replay-what-if-btn"
          onClick={handleWhatIf}
          className="flex-1 py-[4px] text-[9px] font-mono border border-solid bg-[rgba(6,182,212,0.1)] border-[rgba(6,182,212,0.3)] text-[#06b6d4] cursor-pointer hover:bg-[rgba(6,182,212,0.2)] transition-colors"
        >
          What-If
        </button>
        <button
          data-testid="replay-save-btn"
          onClick={handleSave}
          className="flex-1 py-[4px] text-[9px] font-mono border border-solid bg-[rgba(16,185,129,0.1)] border-[rgba(16,185,129,0.3)] text-[#10b981] cursor-pointer hover:bg-[rgba(16,185,129,0.2)] transition-colors"
        >
          Save
        </button>
      </div>
    </div>
  );
};

export default ReplaySummary;
