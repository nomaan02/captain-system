import PropTypes from "prop-types";
import useDashboardStore from "../../stores/dashboardStore";
import { formatPrice, formatTime } from "../../utils/formatting";
import { ASSET_NAMES } from "../../constants/assetNames";
import TradingViewWidget from "./TradingViewWidget";
import useChartStore from "../../stores/chartStore";

const ChartPanel = ({ className = "" }) => {
  const liveMarket = useDashboardStore((s) => s.liveMarket);
  const orStatus = useDashboardStore((s) => s.orStatus);
  const timestamp = useDashboardStore((s) => s.timestamp);
  const selectedAsset = useChartStore((s) => s.selectedAsset);
  const assetName = ASSET_NAMES[selectedAsset] ?? selectedAsset;

  return (
    <div
      className={`flex flex-col h-full w-full text-left text-sm text-[#94a3b8] font-['JetBrains_Mono'] ${className}`}
    >
      {/* FIX-073: Visually-hidden h1 for page context */}
      <h1 className="sr-only">{selectedAsset} — Captain Trading System</h1>

      {/* FIX-068: System info footer bar — min 10px */}
      <div className="self-stretch bg-[#0a1614] border-[#1a3038] border-solid border-t flex items-start justify-between pt-[3px] px-1.5 pb-[3px] gap-5 text-[10px]">
        <div className="flex flex-col items-start py-0 pl-0 pr-5 box-border">
          <div className="relative leading-4">
            SYS:SIGNAL_ENGINE
          </div>
        </div>
        <div className="relative leading-4">
          BROKER:TOPSTEPX
        </div>
        <div className="relative leading-4 tabular-nums">UPD: {timestamp ? formatTime(timestamp) : "---"}</div>
      </div>

      {/* Chart header: asset info + LAST PRICE */}
      <div className="self-stretch border-[#1e293b] border-solid border-b box-border flex items-start pt-0 px-0 pb-0 max-w-full text-right">
        <div className="flex-1 border-[#1e293b] border-solid border-b box-border flex flex-col items-end pt-2 px-1.5 pb-3 max-w-full shrink-0">
          {/* LAST PRICE label + asset info row */}
          <div className="self-stretch flex items-start justify-end py-0 pl-1.5 pr-[5px] box-border max-w-full shrink-0">
            <div className="flex-1 flex flex-col items-end max-w-full shrink-0">
              <div className="relative leading-5">LAST PRICE</div>
              {/* FIX-070: text-[21.2px] → text-xl */}
              <div className="self-stretch flex items-end justify-between gap-5 max-w-full text-left text-xl text-[#fff]">
                <div className="flex-1 flex items-end gap-4 max-w-full">
                  <div className="flex-1 flex flex-col items-start gap-1.5 max-w-full">
                    <div className="flex items-start py-0 pl-0 pr-5 gap-3">
                      {/* FIX-070: leading-[31.8px] → leading-8 */}
                      <h3 data-testid="chart-asset-name" className="m-0 relative text-[length:inherit] leading-8 font-normal font-[inherit]">
                        {selectedAsset}
                      </h3>
                      {/* FIX-070: text-[16.7px] → text-base */}
                      <div className="flex flex-col items-start pt-1 px-0 pb-0 text-base text-[#94a3b8]">
                        <div className="relative leading-6">{assetName}</div>
                      </div>
                    </div>
                    {/* FIX-070: text-[15.2px] → text-sm | FIX-071: overflow-hidden + truncate */}
                    <div className="self-stretch flex items-start gap-5 text-sm text-[#94a3b8] overflow-hidden">
                      <div data-testid="chart-ohlc" className="relative leading-6 truncate tabular-nums">
                        {liveMarket ? `⊕ ${formatPrice(liveMarket.open)} ↕ ${formatPrice(liveMarket.high)}` : "---"}
                      </div>
                      <div data-testid="chart-bid-ask" className="relative leading-6 truncate tabular-nums">
                        {liveMarket ? `Bid/Ask ${formatPrice(liveMarket.best_bid)} / ${formatPrice(liveMarket.best_ask)}` : "---"}
                      </div>
                    </div>
                  </div>
                  {/* FIX-070: text-[15.2px] → text-sm */}
                  <div data-testid="chart-volume" className="relative text-sm leading-6 text-[#94a3b8] tabular-nums shrink-0">
                    {liveMarket?.volume != null ? `Vol ${liveMarket.volume.toLocaleString()}` : "Vol ---"}
                  </div>
                </div>
                {/* FIX-069: text-[45.8px] → responsive clamp */}
                <div className="flex flex-col items-start justify-end pt-0 px-0 pb-1 text-right text-[clamp(24px,4vw,46px)] text-[#10b981]">
                  <h2 data-testid="current-price" className="m-0 relative text-[length:inherit] leading-none font-normal font-[inherit] tabular-nums">
                    {liveMarket?.last_price ? formatPrice(liveMarket.last_price) : "---"}
                  </h2>
                </div>
              </div>
            </div>
          </div>

          {/* FIX-070: text-[14.1px]/leading-[21.2px] → text-sm/leading-5 */}
          <div data-testid="chart-change" className={`relative text-sm leading-5 shrink-0 tabular-nums ${liveMarket?.change != null && liveMarket.change >= 0 ? "text-[#10b981]" : "text-[#ef4444]"}`}>
            {liveMarket?.change != null ? (
              <span>
                {liveMarket.change >= 0 ? "▲" : "▼"} {liveMarket.change >= 0 ? "+" : ""}{formatPrice(liveMarket.change)} ({liveMarket.change_pct >= 0 ? "+" : ""}{liveMarket.change_pct?.toFixed(2)}%)
              </span>
            ) : "---"}
          </div>
        </div>
      </div>

      {/* Chart area (FIX-154..156: dead code removed, TradingView only) */}
      <div className="flex-1 flex flex-col min-h-0 w-full">
        <div className="flex-1 relative min-h-[200px] w-full">
          <TradingViewWidget />
        </div>

        {/* FIX-072: Differentiated OR states — PENDING vs --- */}
        <div className="flex items-center justify-between px-3 py-1.5 border-t border-[#1e293b] text-xs">
          <div className="flex items-center gap-4 tabular-nums">
            <div>
              <span className="text-[#94a3b8] mr-1">OR UPPER</span>
              <span data-testid="chart-or-upper" className="text-[#06b6d4]">
                {orStatus?.or_high != null
                  ? orStatus.or_high.toFixed(2)
                  : orStatus ? "PENDING" : "---"}
              </span>
            </div>
            <div>
              <span className="text-[#94a3b8] mr-1">PRICE</span>
            </div>
            <div>
              <span className="text-[#94a3b8] mr-1">OR LOWER</span>
              <span data-testid="chart-or-lower" className="text-[#06b6d4]">
                {orStatus?.or_low != null
                  ? orStatus.or_low.toFixed(2)
                  : orStatus ? "PENDING" : "---"}
              </span>
            </div>
          </div>
          <div data-testid="chart-or-state" className="bg-[rgba(245,158,11,0.1)] border border-solid border-[rgba(245,158,11,0.3)] px-2 py-0.5 text-[#f59e0b] text-[11px]">
            {orStatus?.or_state ?? "WAITING"}
          </div>
        </div>
      </div>
    </div>
  );
};

ChartPanel.propTypes = {
  className: PropTypes.string,
};

export default ChartPanel;
