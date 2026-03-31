import PropTypes from "prop-types";
import { formatCurrency, formatPrice } from "../../utils/formatting";

const STATUS_CONFIG = {
  or_complete: { label: "OR COMPLETE", bg: "bg-[rgba(6,182,212,0.12)]", border: "border-[rgba(6,182,212,0.25)]", badge: "text-[#06b6d4]" },
  aim_scored: { label: "AIM SCORED", bg: "bg-[rgba(6,182,212,0.12)]", border: "border-[rgba(6,182,212,0.25)]", badge: "text-[#06b6d4]" },
  breakout: { label: "BREAKOUT", bg: "bg-[rgba(245,158,11,0.12)]", border: "border-[rgba(245,158,11,0.25)]", badge: "text-[#f59e0b]" },
  sized: { label: "SIZED", bg: "bg-[rgba(59,130,246,0.12)]", border: "border-[rgba(59,130,246,0.25)]", badge: "text-[#3b82f6]" },
  exited: { label: "EXITED", bg: "bg-[rgba(16,185,129,0.12)]", border: "border-[rgba(16,185,129,0.25)]", badge: "text-[#10b981]" },
  error: { label: "ERROR", bg: "bg-[rgba(239,68,68,0.15)]", border: "border-[rgba(239,68,68,0.25)]", badge: "text-[#ef4444]" },
  loading: { label: "LOADING", bg: "bg-[rgba(100,116,139,0.05)]", border: "border-[#1e293b]", badge: "text-[#64748b]" },
};

const AssetCard = ({ asset, data }) => {
  const status = data?.status || "loading";
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.loading;

  const orResult = data?.orResult;
  const breakout = data?.breakout;
  const sizing = data?.sizing;
  const exitResult = data?.exitResult;
  const error = data?.error;

  const direction = breakout?.direction > 0 ? "LONG" : breakout?.direction < 0 ? "SHORT" : null;
  const pnl = exitResult?.pnl ?? null;
  const exitReason = exitResult?.reason || exitResult?.exit_reason || null;
  const contracts = sizing?.final ?? sizing?.contracts ?? breakout?.contracts ?? null;

  const isShimmer = status === "loading";

  return (
    <div
      data-testid={`asset-card-${asset}`}
      data-status={status}
      className={`border border-solid ${cfg.border} ${cfg.bg} p-2 font-mono ${isShimmer ? "animate-pulse" : ""}`}
    >
      {/* Header row: Asset name + status badge */}
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <span data-testid={`asset-card-name-${asset}`} className="text-[11px] text-[#06b6d4] font-semibold">{asset}</span>
          {direction && (
            <span
              className={`px-1 py-[1px] text-[7px] leading-[10px] border border-solid ${
                direction === "LONG"
                  ? "bg-[rgba(16,185,129,0.2)] border-[rgba(16,185,129,0.4)] text-[#10b981]"
                  : "bg-[rgba(239,68,68,0.2)] border-[rgba(239,68,68,0.4)] text-[#ef4444]"
              }`}
            >
              {direction}
            </span>
          )}
          {orResult?.session && (
            <span className="px-1 py-[1px] text-[6px] leading-[9px] border border-solid border-[#374151] text-[#64748b] uppercase">
              {orResult.session}
            </span>
          )}
        </div>
        <span className={`text-[7px] uppercase tracking-[0.5px] ${cfg.badge}`}>{cfg.label}</span>
      </div>

      {/* Error state */}
      {status === "error" && (
        <div className="text-[9px] text-[#ef4444] mt-1">{error || "Unknown error"}</div>
      )}

      {/* OR range */}
      {orResult && (
        <div className="flex items-center gap-3 text-[8px] mt-1">
          <span>
            <span className="text-[#64748b]">OR </span>
            <span className="text-[#e2e8f0]">{formatPrice(orResult.or_low)} - {formatPrice(orResult.or_high)}</span>
          </span>
          {orResult.or_range != null && (
            <span className="text-[#64748b]">({formatPrice(orResult.or_range)} range)</span>
          )}
        </div>
      )}

      {/* Entry / TP / SL */}
      {breakout && (
        <div className="flex items-center gap-3 text-[8px] mt-1">
          <span>
            <span className="text-[#64748b]">E </span>
            <span className="text-[#e2e8f0]">{formatPrice(breakout.entry_price)}</span>
          </span>
          <span>
            <span className="text-[#64748b]">TP </span>
            <span className="text-[#10b981]">{formatPrice(breakout.tp_level)}</span>
          </span>
          <span>
            <span className="text-[#64748b]">SL </span>
            <span className="text-[#ef4444]">{formatPrice(breakout.sl_level)}</span>
          </span>
        </div>
      )}

      {/* Sizing + Exit row */}
      {(contracts != null || exitResult) && (
        <div className="flex items-center justify-between text-[8px] mt-1">
          <div className="flex items-center gap-3">
            {contracts != null && (
              <span>
                <span className="text-[#64748b]">Qty </span>
                <span className="text-[#e2e8f0]">{contracts}</span>
              </span>
            )}
            {exitReason && (
              <span className={`px-1 py-[1px] text-[7px] leading-[9px] border border-solid ${
                exitReason === "TP" || exitReason === "TP_HIT"
                  ? "border-[rgba(16,185,129,0.4)] text-[#10b981]"
                  : exitReason === "SL" || exitReason === "SL_HIT"
                    ? "border-[rgba(239,68,68,0.4)] text-[#ef4444]"
                    : "border-[#374151] text-[#f59e0b]"
              }`}>
                {exitReason}
              </span>
            )}
          </div>
          {pnl != null && (
            <span data-testid={`asset-card-pnl-${asset}`} className={`text-[10px] font-semibold ${pnl >= 0 ? "text-[#10b981]" : "text-[#ef4444]"}`}>
              {formatCurrency(pnl, { showSign: true })}
            </span>
          )}
        </div>
      )}

      {/* Shimmer placeholder for loading */}
      {isShimmer && (
        <div className="space-y-1 mt-1">
          <div className="h-[8px] bg-[#1e293b] rounded w-3/4" />
          <div className="h-[8px] bg-[#1e293b] rounded w-1/2" />
        </div>
      )}
    </div>
  );
};

AssetCard.propTypes = {
  asset: PropTypes.string.isRequired,
  data: PropTypes.object,
};

export default AssetCard;
