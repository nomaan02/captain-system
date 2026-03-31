import PropTypes from "prop-types";
import useDashboardStore from "../../stores/dashboardStore";
import { formatCurrency, formatPrice, formatTimeSince } from "../../utils/formatting";
import { POINT_VALUES } from "../../constants/pointValues";

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
  const currentPrice = liveMarket?.last_price;
  const pnl = pos.current_pnl ?? 0;
  const pointValue = POINT_VALUES[asset] ?? 5;
  const ticks = currentPrice && entryPrice ? Math.round((currentPrice - entryPrice) * (direction === "LONG" ? 1 : -1) / (pointValue > 100 ? 1 : 0.25)) : 0;
  const slLevel = pos.sl_level;
  const tpLevel = pos.tp_level;

  // Derive SL/TP distances
  const slDist = slLevel != null && entryPrice != null ? Math.abs(entryPrice - slLevel) : null;
  const tpDist = tpLevel != null && entryPrice != null ? Math.abs(tpLevel - entryPrice) : null;
  const slDistValue = slDist != null ? slDist * contracts * pointValue : null;
  const tpDistValue = tpDist != null ? tpDist * contracts * pointValue : null;

  return (
    <section
      data-testid="active-position"
      className={`self-stretch flex items-start justify-end max-w-full relative text-left text-[10.9px] text-[#64748b] font-['JetBrains_Mono'] ${className}`}
    >
      <div className="w-full border-[#1e293b] border-solid border-b-[0.9px] box-border flex flex-col items-end pt-0 px-0 pb-1 gap-[6.2px] max-w-full z-[1]">
        <div className="self-stretch border-[#1e293b] border-solid border-b-[0.9px] flex items-start justify-between pt-[3.4px] px-[7px] pb-[3px] gap-5 text-[9.2px] mq450:flex-wrap mq450:gap-5">
          <div className="flex items-start gap-1.5">
            <div className="flex flex-col items-start pt-[4.5px] px-0 pb-0">
              <div className="w-[5px] h-[5.3px] relative rounded-full bg-[rgba(16,185,129,0.54)]" />
            </div>
            <div className="relative tracking-[1.02px] leading-[13.8px] uppercase">
              Active Position
            </div>
          </div>
          <div className="flex items-start gap-[5.1px] text-[8.2px]">
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
        <div className="self-stretch flex items-start justify-end py-0 pl-2 pr-[3px] box-border max-w-full text-[7.2px]">
          <div className="flex-1 flex items-start justify-between py-0 pl-px pr-0 box-border gap-5 max-w-full mq450:flex-wrap mq450:gap-5">
            <div className="flex items-start gap-[10.2px]">
              <div className="flex flex-col items-start gap-[3.4px]">
                <div className="relative leading-[7.2px]">ENTRY</div>
                <div data-testid="position-entry" className="relative text-[11.2px] leading-[11.3px] text-[#e2e8f0]">
                  {formatPrice(entryPrice)}
                </div>
              </div>
              <div className="flex flex-col items-start gap-[3.4px]">
                <div className="relative leading-[7.2px]">CURRENT</div>
                <div data-testid="position-current" className={`relative text-[11.2px] leading-[11.3px] ${pnl >= 0 ? "text-[#10b981]" : "text-[#ef4444]"}`}>
                  {currentPrice ? formatPrice(currentPrice) : "—"}
                </div>
              </div>
            </div>
            <div data-testid="position-pnl" className={`relative text-right text-[18.4px] ${pnl >= 0 ? "text-[#10b981]" : "text-[#ef4444]"}`}>
              <span className={`leading-[18.41px] ${pnl >= 0 ? "text-[#10b981]" : "text-[#ef4444]"}`}>{formatCurrency(pnl, { showSign: true })}</span>
              <span className={`text-[9.2px] leading-[13.8px] ${pnl >= 0 ? "text-[rgba(16,185,129,0.7)]" : "text-[rgba(239,68,68,0.7)]"}`}>({ticks >= 0 ? "+" : ""}{ticks}t)</span>
            </div>
          </div>
        </div>
        <div className="self-stretch flex items-start justify-end py-0 pl-2 pr-[7px] box-border max-w-full text-[#ef4444]">
          <div className="flex-1 flex items-start justify-between py-0 pl-px pr-0 box-border gap-5 max-w-full mq450:flex-wrap mq450:gap-5">
            <div className="flex flex-col items-start pt-[1.5px] px-0 pb-0">
              <div className="relative leading-[7.2px]">{slLevel != null ? `SL ${formatPrice(slLevel)}` : "SL —"}</div>
            </div>
            <div className="relative leading-[7.2px] text-[#10b981]">
              {tpLevel != null ? `TP ${formatPrice(tpLevel)}` : "TP —"}
            </div>
          </div>
        </div>
        <div className="self-stretch flex items-start justify-end py-0 px-2 box-border max-w-full">
          <div className="flex-1 [background:linear-gradient(90deg,_#ef4444,_#1e293b_50%,_#10b981)] flex items-start justify-between py-0 pl-[346px] pr-[265px] box-border gap-5 max-w-full mq750:gap-5 mq750:pl-[86px] mq750:pr-[66px] mq750:box-border mq1025:gap-5 mq1025:pl-[173px] mq1025:pr-[132px] mq1025:box-border">
            <div className="h-[6.3px] w-px relative bg-[#3b82f6] shrink-0" />
            <div className="mt-[-2.1px] h-[3.2px] w-[5px] relative shrink-0" />
          </div>
        </div>
        <div className="self-stretch flex items-start justify-end py-0 pl-2 pr-1 box-border max-w-full text-[#ef4444]">
          <div className="flex-1 flex items-start justify-between gap-5 max-w-full mq450:flex-wrap mq450:gap-5">
            <div className="relative leading-[7.2px]">{slDist != null ? `${slDist.toFixed(2)}pts (${formatCurrency(slDistValue)})` : "—"}</div>
            <div className="relative leading-[7.2px] text-[#10b981]">
              {tpDist != null ? `${tpDist.toFixed(2)}pts (${formatCurrency(tpDistValue)})` : "—"}
            </div>
          </div>
        </div>
        <div className="self-stretch flex items-start py-0 px-2 text-[8.2px]">
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
