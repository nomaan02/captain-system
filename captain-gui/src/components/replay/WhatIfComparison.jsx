import useReplayStore from "../../stores/replayStore";
import { formatCurrency } from "../../utils/formatting";

const CompRow = ({ label, original, whatIf, isCurrency = false, highlight = false }) => {
  const delta = (whatIf ?? 0) - (original ?? 0);
  const fmt = isCurrency ? (v) => formatCurrency(v, { showSign: true }) : (v) => (v ?? "--");

  return (
    <div className={`grid grid-cols-4 gap-1 py-[2px] text-[9px] font-mono border-b border-[#1e293b] ${highlight ? "bg-[rgba(6,182,212,0.05)]" : ""}`}>
      <span className="text-[#64748b] pl-1">{label}</span>
      <span className="text-[#e2e8f0] text-right">{fmt(original)}</span>
      <span className="text-[#e2e8f0] text-right">{fmt(whatIf)}</span>
      <span className={`text-right pr-1 ${
        delta > 0 ? "text-[#10b981]" : delta < 0 ? "text-[#ef4444]" : "text-[#64748b]"
      }`}>
        {isCurrency ? formatCurrency(delta, { showSign: true }) : (delta !== 0 ? (delta > 0 ? `+${delta}` : `${delta}`) : "--")}
      </span>
    </div>
  );
};

const WhatIfComparison = () => {
  const comparison = useReplayStore((s) => s.comparison);
  const summary = useReplayStore((s) => s.summary);
  const assetResults = useReplayStore((s) => s.assetResults);
  const assetOrder = useReplayStore((s) => s.assetOrder);

  if (!comparison) return null;

  const origTrades = assetOrder.filter((a) => assetResults[a]?.status === "exited");
  const origPnl = origTrades.reduce((s, a) => {
    const ppc = assetResults[a]?.exitResult?.pnl_per_contract ?? assetResults[a]?.exitResult?.pnl ?? 0;
    const cts = assetResults[a]?.sizing?.contracts ?? 0;
    return s + ppc * cts;
  }, 0);
  const origBlocked = assetOrder.filter((a) => assetResults[a]?.status === "blocked").length;

  const wiTrades = comparison.trades || [];
  const wiPnl = comparison.total_pnl ?? wiTrades.reduce((s, t) => s + (t.pnl ?? 0), 0);
  const wiBlocked = comparison.blocked_count ?? 0;

  // Detect assets that changed status
  const wiAssetMap = {};
  (comparison.asset_results || []).forEach((ar) => { wiAssetMap[ar.asset || ar.asset_id] = ar; });

  const changedAssets = assetOrder.filter((a) => {
    const origStatus = assetResults[a]?.status;
    const wiStatus = wiAssetMap[a]?.status;
    if (!wiStatus) return false;
    return origStatus !== wiStatus;
  });

  return (
    <div data-testid="what-if-comparison" className="p-3 space-y-2">
      <div className="text-[9px] uppercase tracking-[1px] text-[#06b6d4] font-mono">What-If Comparison</div>

      {/* Header row */}
      <div className="grid grid-cols-4 gap-1 text-[7px] uppercase tracking-[0.5px] text-[#64748b] font-mono border-b border-[#1e293b] pb-1">
        <span className="pl-1">Metric</span>
        <span className="text-right">Original</span>
        <span className="text-right">What-If</span>
        <span className="text-right pr-1">Delta</span>
      </div>

      {/* Comparison rows */}
      <CompRow label="Total P&L" original={origPnl} whatIf={wiPnl} isCurrency highlight />
      <CompRow label="Trades" original={origTrades.length} whatIf={wiTrades.length} />
      <CompRow label="Blocked" original={origBlocked} whatIf={wiBlocked} />

      {/* Per-asset contract changes */}
      {comparison.asset_results && comparison.asset_results.length > 0 && (
        <div className="border-t border-[#1e293b] pt-2 mt-2">
          <div className="text-[8px] uppercase tracking-[0.5px] text-[#64748b] font-mono mb-1">Per-Asset Contracts</div>
          <div className="max-h-[120px] overflow-y-auto">
            {comparison.asset_results.map((ar) => {
              const asset = ar.asset || ar.asset_id;
              const origContracts = assetResults[asset]?.sizing?.final ?? assetResults[asset]?.sizing?.contracts ?? 0;
              const wiContracts = ar.contracts ?? 0;
              const delta = wiContracts - origContracts;
              return (
                <div key={asset} className="flex items-center justify-between py-[2px] text-[9px] font-mono border-b border-[#1e293b]">
                  <span className="text-[#06b6d4]">{asset}</span>
                  <div className="flex items-center gap-3">
                    <span className="text-[#64748b]">{origContracts}</span>
                    <span className="text-[#64748b]">-&gt;</span>
                    <span className="text-[#e2e8f0]">{wiContracts}</span>
                    {delta !== 0 && (
                      <span className={`text-[8px] ${delta > 0 ? "text-[#10b981]" : "text-[#ef4444]"}`}>
                        {delta > 0 ? `+${delta}` : delta}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Changed status assets */}
      {changedAssets.length > 0 && (
        <div className="border-t border-[#1e293b] pt-2 mt-2">
          <div className="text-[8px] uppercase tracking-[0.5px] text-[#f59e0b] font-mono mb-1">Status Changes</div>
          {changedAssets.map((a) => {
            const origStatus = assetResults[a]?.status;
            const wiStatus = wiAssetMap[a]?.status;
            return (
              <div key={a} className="flex items-center justify-between py-[2px] text-[9px] font-mono">
                <span className="text-[#06b6d4]">{a}</span>
                <div className="flex items-center gap-1">
                  <span className="text-[#64748b]">{origStatus}</span>
                  <span className="text-[#64748b]">-&gt;</span>
                  <span className={wiStatus === "exited" || wiStatus === "sized" ? "text-[#10b981]" : wiStatus === "blocked" ? "text-[#ef4444]" : "text-[#e2e8f0]"}>
                    {wiStatus}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default WhatIfComparison;
