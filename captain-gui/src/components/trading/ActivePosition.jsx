import PropTypes from "prop-types";
import useDashboardStore from "../../stores/dashboardStore";
import { formatCurrency, formatPrice, formatTimeSince } from "../../utils/formatting";
import { POINT_VALUES } from "../../constants/pointValues";

const TICK_SIZES = {
  MES: 0.25, ES: 0.25, MNQ: 0.25, NQ: 0.25,
  MYM: 1.0, M2K: 0.10, MGC: 0.10, MCL: 0.01,
  NKD: 5.0, ZB: 1/32, ZN: 1/64,
};

const ActivePosition = ({ className = "" }) => {
  const openPositions = useDashboardStore((s) => s.openPositions);
  const liveMarket = useDashboardStore((s) => s.liveMarket);
  const pos = openPositions?.[0]; // First open position

  if (!pos) {
    return (
      <section data-testid="active-position" className={`self-stretch flex items-center justify-center py-4 text-[10.9px] text-[#64748b] font-mono ${className}`}>
        <span data-testid="position-empty">No active position</span>
      </section>
    );
  }

  const direction = pos.direction; // Already normalized by store
  const asset = pos.asset_id ?? pos.asset ?? "—";
  const contracts = pos.contracts ?? 1;
  const entryPrice = pos.entry_price;
  // TODO: Refactor liveMarket to Map<assetId, MarketData>
  const marketMatch = liveMarket?.contract_id === asset || liveMarket?.symbol === asset;
  const currentPrice = marketMatch ? liveMarket?.last_price : null;
  const pnl = pos.current_pnl ?? 0;
  const pointValue = POINT_VALUES[asset] ?? 5;
  const tickSize = TICK_SIZES[asset] ?? 0.25;
  const ticks = currentPrice && entryPrice ? Math.round((currentPrice - entryPrice) * (direction === "LONG" ? 1 : -1) / tickSize) : 0;
  const slLevel = pos.sl_level;
  const tpLevel = pos.tp_level;

  // Derive SL/TP distances
  const slDist = slLevel != null && entryPrice != null ? Math.abs(entryPrice - slLevel) : null;
  const tpDist = tpLevel != null && entryPrice != null ? Math.abs(tpLevel - entryPrice) : null;
  const slDistValue = slDist != null ? slDist * contracts * pointValue : null;
  const tpDistValue = tpDist != null ? tpDist * contracts * pointValue : null;

  // Entry marker position on the SL–TP gradient bar
  const entryPct = slDist != null && tpDist != null && (slDist + tpDist) > 0
    ? (slDist / (slDist + tpDist)) * 100
    : 50;

  return (
    <section
      data-testid="active-position"
      className={`self-stretch flex items-start justify-end max-w-full relative text-left text-[10.9px] text-[#64748b] font-['JetBrains_Mono'] ${className}`}
    >
      <div className="w-full border-[#1e293b] border-solid border-b-[0.9px] box-border flex flex-col items-end pt-0 px-0 pb-1 gap-[6.2px] max-w-full z-[1]">
        <div className="self-stretch border-[#1e293b] border-solid border-b-[0.9px] flex items-start justify-between pt-[3.4px] px-[7px] pb-[3px] gap-5 text-[9.2px]">
          <div className="flex items-start gap-1.5">
            <div className="flex flex-col items-start pt-[4.5px] px-0 pb-0">
              <div className="w-[5px] h-[5.3px] relative rounded-full bg-[rgba(16,185,129,0.54)]" />
            </div>
            <div className="relative tracking-[1.02px] leading-[13.8px] uppercase">
              Active Position
            </div>
          </div>
          <div className="flex items-start gap-[5.1px] text-[10px]">
            <div className={`border-solid border-[0.9px] flex items-start pt-[0.8px] pb-[0.7px] pl-1 pr-[3px] ${direction === "LONG" ? "bg-[rgba(16,185,129,0.15)] border-[rgba(16,185,129,0.3)] text-[#10b981]" : "bg-[rgba(239,68,68,0.15)] border-[rgba(239,68,68,0.3)] text-[#ef4444]"}`}>
              <div data-testid="position-direction" className="relative leading-[13.3px]">{direction}</div>
            </div>
            <div data-testid="position-asset" className="flex-1 relative text-[9.2px] leading-[13.8px] text-[#06b6d4] inline-block min-w-[45px]">
              {asset}
            </div>
            <div className="flex flex-col items-start pt-[1.4px] px-0 pb-0">
              <div className="relative leading-[12.3px]">{`×${contracts}`}</div>
            </div>
            <div className="flex-1 flex flex-col items-start pt-[1.4px] px-0 pb-0">
              <div className="relative leading-[12.3px]">{pos.order_id ?? "—"}</div>
            </div>
          </div>
        </div>
        <div className="self-stretch flex items-start justify-end py-0 pl-2 pr-[3px] box-border max-w-full text-[10px]">
          <div className="flex-1 flex items-start justify-between py-0 pl-px pr-0 box-border gap-5 max-w-full">
            <div className="flex items-start gap-[10.2px]">
              <div className="flex flex-col items-start gap-[3.4px]">
                <div className="relative leading-tight">ENTRY</div>
                <div data-testid="position-entry" className="relative text-[11.2px] leading-[11.3px] text-[#e2e8f0]">
                  {formatPrice(entryPrice)}
                </div>
              </div>
              <div className="flex flex-col items-start gap-[3.4px]">
                <div className="relative leading-tight">CURRENT</div>
                <div data-testid="position-current" className={`relative text-[11.2px] leading-[11.3px] ${pnl >= 0 ? "text-[#10b981]" : "text-[#ef4444]"}`}>
                  {currentPrice ? formatPrice(currentPrice) : "—"}
                </div>
              </div>
            </div>
            <div data-testid="position-pnl" className={`relative text-right text-lg ${pnl >= 0 ? "text-[#10b981]" : "text-[#ef4444]"}`}>
              <span className={`leading-[18.41px] ${pnl >= 0 ? "text-[#10b981]" : "text-[#ef4444]"}`}>{formatCurrency(pnl, { showSign: true })}</span>
              <span className={`text-[9.2px] leading-[13.8px] ${pnl >= 0 ? "text-[rgba(16,185,129,0.7)]" : "text-[rgba(239,68,68,0.7)]"}`}>({ticks >= 0 ? "+" : ""}{ticks}t)</span>
            </div>
          </div>
        </div>
        <div className="self-stretch flex items-start justify-end py-0 pl-2 pr-[7px] box-border max-w-full text-[#ef4444]">
          <div className="flex-1 flex items-start justify-between py-0 pl-px pr-0 box-border gap-5 max-w-full">
            <div className="flex flex-col items-start pt-[1.5px] px-0 pb-0">
              <div className="relative leading-tight">{slLevel != null ? `SL ${formatPrice(slLevel)}` : "SL —"}</div>
            </div>
            <div className="relative leading-tight text-[#10b981]">
              {tpLevel != null ? `TP ${formatPrice(tpLevel)}` : "TP —"}
            </div>
          </div>
        </div>
        <div className="self-stretch py-0 px-2 box-border max-w-full">
          <div className="w-full h-1.5 relative [background:linear-gradient(90deg,_#ef4444,_#1e293b_50%,_#10b981)]">
            <div
              className="absolute top-0 h-full w-px bg-[#3b82f6]"
              style={{ left: `${entryPct}%` }}
            />
          </div>
        </div>
        <div className="self-stretch flex items-start justify-end py-0 pl-2 pr-1 box-border max-w-full text-[#ef4444]">
          <div className="flex-1 flex items-start justify-between gap-5 max-w-full">
            <div className="relative leading-tight">{slDist != null ? `${slDist.toFixed(2)}pts (${formatCurrency(slDistValue)})` : "—"}</div>
            <div className="relative leading-tight text-[#10b981]">
              {tpDist != null ? `${tpDist.toFixed(2)}pts (${formatCurrency(tpDistValue)})` : "—"}
            </div>
          </div>
        </div>
        <div className="self-stretch flex items-start py-0 px-2 text-[10px]">
          <div className="flex items-start gap-[10.3px]">
            <div className="flex-1 relative leading-[12.3px]">
              <span>{`Time: `}</span>
              <span className="text-[#e2e8f0]">{pos.entry_time ? formatTimeSince(pos.entry_time) : "—"}</span>
            </div>
            <div className="relative leading-[12.3px]">
              <span>{`Lots: `}</span>
              <span className="text-[#e2e8f0]">{contracts}</span>
            </div>
            <div className="flex-1 relative leading-[12.3px]">
              <span>{`Fill: `}</span>
              <span className="text-[#e2e8f0]">{pos.order_id ?? "—"}</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

ActivePosition.propTypes = {
  className: PropTypes.string,
};

export default ActivePosition;
