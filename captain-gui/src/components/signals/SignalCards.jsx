import PropTypes from "prop-types";
import useDashboardStore from "../../stores/dashboardStore";
import { formatCurrency, formatPrice } from "../../utils/formatting";

const SignalCards = ({ className = "" }) => {
  const pendingSignals = useDashboardStore((s) => s.pendingSignals);
  const dailyTradeStats = useDashboardStore((s) => s.dailyTradeStats);
  const clearSignals = useDashboardStore((s) => s.clearSignals);

  return (
    <div
      data-testid="signal-panel"
      className={`w-full flex flex-col items-start overflow-y-auto text-left text-[10px] text-[#64748b] font-['JetBrains_Mono'] ${className}`}
    >
      {pendingSignals.length > 0 ? (
        pendingSignals.map((sig, idx) => (
          <div
            data-testid="signal-card"
            key={sig.signal_id ?? idx}
            className="self-stretch border-[#1e293b] border-solid border-b flex items-center justify-between px-3 py-[5px] gap-2"
          >
            {/* Left: direction + asset + strategy */}
            <div className="flex items-center gap-2 shrink-0">
              <span
                className={`px-1.5 py-[1px] text-[10px] leading-[14px] border border-solid ${
                  sig.direction === "LONG"
                    ? "bg-[rgba(16,185,129,0.2)] border-[rgba(16,185,129,0.4)] text-[#10b981]"
                    : sig.direction === "NEUTRAL"
                      ? "bg-[rgba(100,116,139,0.2)] border-[rgba(100,116,139,0.4)] text-[#94a3b8]"
                      : "bg-[rgba(239,68,68,0.2)] border-[rgba(239,68,68,0.4)] text-[#ef4444]"
                }`}
              >
                {sig.direction}
              </span>
              <span className="text-[11px] text-[#06b6d4]">{sig.asset ?? "—"}</span>
              <span className="text-[10px] text-[#4a5568]">{sig.strategy_name ?? ""}</span>
            </div>

            {/* Center: Entry / SL / TP inline */}
            <div className="flex items-center gap-3 text-[10px]">
              <span>
                <span className="text-[#4a5568]">E </span>
                <span className="text-[#e2e8f0]">{formatPrice(sig.entry_price)}</span>
              </span>
              <span>
                <span className="text-[#4a5568]">SL </span>
                <span className="text-[#ef4444]">{formatPrice(sig.sl_level)}</span>
              </span>
              <span>
                <span className="text-[#4a5568]">TP </span>
                <span className="text-[#10b981]">{formatPrice(sig.tp_level)}</span>
              </span>
            </div>

            {/* Right: P&L + confidence + tier badge */}
            <div className="flex items-center gap-2 shrink-0">
              <span
                className={`text-[10px] ${
                  (sig.pnl ?? 0) >= 0 ? "text-[#10b981]" : "text-[#ef4444]"
                }`}
              >
                {sig.pnl != null ? formatCurrency(sig.pnl, { showSign: true }) : "—"}
              </span>
              <span className="text-[10px] text-[#94a3b8]">
                {sig.quality_score != null
                  ? `${Math.round(sig.quality_score * 100)}%`
                  : ""}
              </span>
              {sig.confidence_tier && (
                <span
                  className={`px-1 py-[1px] text-[10px] leading-[14px] border border-solid ${
                    sig.confidence_tier === "HIGH"
                      ? "border-[rgba(16,185,129,0.4)] text-[#10b981]"
                      : sig.confidence_tier === "LOW"
                        ? "border-[rgba(239,68,68,0.4)] text-[#ef4444]"
                        : "border-[rgba(245,158,11,0.4)] text-[#f59e0b]"
                  }`}
                >
                  {sig.confidence_tier}
                </span>
              )}
            </div>
          </div>
        ))
      ) : (
        <div className="self-stretch flex items-center justify-center py-4 text-[10px] text-[#64748b]">
          No pending signals
        </div>
      )}

      {/* Session summary footer — compact single row */}
      <div data-testid="signal-session-footer" className="self-stretch bg-[#0a1614] flex items-center justify-between px-3 py-[4px] text-[10px] shrink-0">
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1">
            <span className="text-[#64748b]">P&L</span>
            <span data-testid="signal-session-pnl" className={`text-[12px] ${(dailyTradeStats?.total_pnl ?? 0) >= 0 ? 'text-[#10b981]' : 'text-[#ef4444]'}`}>
              {formatCurrency(dailyTradeStats?.total_pnl ?? 0, { showSign: true })}
            </span>
          </div>
          {pendingSignals.length > 0 && (
            <button
              data-testid="clear-signals-btn"
              onClick={clearSignals}
              className="min-h-[28px] px-2 text-[10px] inline-flex items-center font-mono border border-solid border-[#2e4e5a] bg-[#111827] text-[#94a3b8] hover:text-[#e2e8f0] hover:border-[#547380] cursor-pointer transition-colors"
            >
              Clear
            </button>
          )}
        </div>
        <div className="flex items-center gap-3">
          <span>
            <span className="text-[#64748b]">Win </span>
            <span data-testid="signal-session-win-pct" className="text-[#e2e8f0]">{dailyTradeStats?.win_pct != null ? `${dailyTradeStats.win_pct}%` : '—'}</span>
          </span>
          <span>
            <span className="text-[#64748b]">Signals </span>
            <span data-testid="signal-session-count" className="text-[#e2e8f0]">{pendingSignals.length}</span>
          </span>
          <span>
            <span className="text-[#64748b]">Trades </span>
            <span data-testid="signal-session-trades" className="text-[#e2e8f0]">{dailyTradeStats?.trades_today ?? 0}</span>
          </span>
        </div>
      </div>
    </div>
  );
};

SignalCards.propTypes = {
  className: PropTypes.string,
};

export default SignalCards;
