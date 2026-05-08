import { useMemo } from "react";

/**
 * Warm-up Status banner — shows per-asset progress toward the
 * pseudotrader cold-start threshold (default 5 D03 trades). When every
 * asset has graduated, the banner collapses to a single confirmation row.
 *
 * Wired to GET /api/pseudotrader/coldstart_status; the orchestrator's
 * `_pseudotrader_gate` writes a `SKIP_COLD_START` row to D11 every time
 * an asset below threshold triggers an event, so this banner is the
 * counterpart that explains why the Decision Log fills with `SKIP_*`
 * rows during warm-up rather than ADOPT/REJECT outcomes.
 */
const WarmupStatus = ({ coldStart }) => {
  const summary = useMemo(() => {
    if (!coldStart || !Array.isArray(coldStart.per_asset)) return null;
    return {
      min: coldStart.min_required,
      total: coldStart.total_assets,
      warm: coldStart.warm_assets,
      cold: coldStart.cold_assets,
      perAsset: [...coldStart.per_asset].sort((a, b) =>
        a.asset.localeCompare(b.asset)
      ),
    };
  }, [coldStart]);

  if (!summary) {
    return (
      <div className="mb-3 p-2 border border-[#374151] bg-[rgba(100,116,139,0.05)] text-[10px] font-mono text-[#64748b]">
        Warm-up status unavailable
      </div>
    );
  }

  if (summary.cold === 0) {
    return (
      <div className="mb-3 p-2 border border-[rgba(16,185,129,0.3)] bg-[rgba(16,185,129,0.08)] text-[10px] font-mono text-[#10b981]">
        All {summary.total} assets warm — pseudotrader replay active
        (≥{summary.min} D03 trades each).
      </div>
    );
  }

  return (
    <div className="mb-3 p-3 border border-[rgba(245,158,11,0.3)] bg-[rgba(245,158,11,0.05)]">
      <div className="flex items-baseline justify-between mb-2">
        <div className="text-[11px] font-mono text-[#f59e0b] uppercase tracking-wider">
          Cold-start in progress
        </div>
        <div className="text-[10px] font-mono text-[#94a3b8]">
          {summary.warm}/{summary.total} warm · {summary.cold} below threshold
        </div>
      </div>
      <div className="text-[10px] font-mono text-[#94a3b8] mb-2">
        Pseudotrader replay activates per-asset once {summary.min} D03 trades
        have accumulated. Until then, gate decisions are auto-approved and
        recorded as SKIP_COLD_START in the Decision Log below.
      </div>
      <div className="flex flex-wrap gap-1.5">
        {summary.perAsset.map((a) => {
          const ratio = a.n_trades / Math.max(summary.min, 1);
          const colorClass = a.warm
            ? "border-[rgba(16,185,129,0.4)] text-[#10b981] bg-[rgba(16,185,129,0.08)]"
            : ratio >= 0.5
              ? "border-[rgba(245,158,11,0.4)] text-[#f59e0b] bg-[rgba(245,158,11,0.08)]"
              : "border-[#374151] text-[#94a3b8] bg-[rgba(100,116,139,0.05)]";
          return (
            <span
              key={a.asset}
              className={`px-1.5 py-0.5 text-[9px] font-mono border border-solid ${colorClass}`}
            >
              {a.asset} {a.n_trades}/{summary.min}
            </span>
          );
        })}
      </div>
    </div>
  );
};

export default WarmupStatus;
