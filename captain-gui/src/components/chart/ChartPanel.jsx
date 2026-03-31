import PropTypes from "prop-types";
import useDashboardStore from "../../stores/dashboardStore";
import { formatPrice, formatTime } from "../../utils/formatting";
import { ASSET_NAMES } from "../../constants/assetNames";
import TradingViewWidget from "./TradingViewWidget";
import CandlestickChart from "./CandlestickChart";
import TimeframeSelector from "./TimeframeSelector";
import ChartOverlayToggles from "./ChartOverlayToggles";
import useChartStore from "../../stores/chartStore";

// Set to true to use lightweight-charts with your own bar data instead of TradingView widget
const USE_CUSTOM_CHART = false;

const ChartPanel = ({ className = "" }) => {
  const liveMarket = useDashboardStore((s) => s.liveMarket);
  const orStatus = useDashboardStore((s) => s.orStatus);
  const timestamp = useDashboardStore((s) => s.timestamp);
  const selectedAsset = useChartStore((s) => s.selectedAsset);
  const assetName = ASSET_NAMES[selectedAsset] ?? selectedAsset;

  return (
    <div
      className={`flex flex-col h-full w-full text-left text-[13.6px] text-[#94a3b8] font-['JetBrains_Mono'] ${className}`}
    >
      {/* System info footer bar (sits above chart header in original flow) */}
      <div className="self-stretch bg-[#0a1614] border-[#1a3038] border-solid border-t flex items-start justify-between pt-[3px] px-[5px] pb-[3.4px] gap-5 text-[6.3px]">
        <div className="w-[141.8px] flex flex-col items-start py-0 pl-0 pr-5 box-border">
          <div className="relative leading-[12px]">
            SYS:SIGNAL_ENGINE
          </div>
        </div>
        <div className="relative leading-[12px]">
          BROKER:TOPSTEPX
        </div>
        <div className="relative leading-[12px]">UPD: {timestamp ? formatTime(timestamp) : "—"}</div>
      </div>

      {/* Chart header: asset info + LAST PRICE */}
      <div className="self-stretch border-[#1e293b] border-solid border-b box-border flex items-start pt-0 px-0 pb-0 max-w-full text-right">
        <div className="flex-1 border-[#1e293b] border-solid border-b box-border flex flex-col items-end pt-[8px] px-1.5 pb-3 max-w-full shrink-0">
          {/* LAST PRICE label + asset info row */}
          <div className="self-stretch flex items-start justify-end py-0 pl-1.5 pr-[5px] box-border max-w-full shrink-0">
            <div className="flex-1 flex flex-col items-end max-w-full shrink-0">
              <div className="relative leading-[20.5px]">LAST PRICE</div>
              <div className="self-stretch flex items-end justify-between gap-5 max-w-full text-left text-[21.2px] text-[#fff]">
                <div className="flex-1 flex items-end gap-[17.5px] max-w-full">
                  <div className="flex-1 flex flex-col items-start gap-[7px] max-w-full">
                    <div className="flex items-start py-0 pl-0 pr-5 gap-[11.3px]">
                      <h3 data-testid="chart-asset-name" className="m-0 relative text-[length:inherit] leading-[31.8px] font-normal font-[inherit]">
                        {selectedAsset}
                      </h3>
                      <div className="flex flex-col items-start pt-[4.9px] px-0 pb-0 text-[16.7px] text-[#94a3b8]">
                        <div className="relative leading-[25px]">{assetName}</div>
                      </div>
                    </div>
                    <div className="self-stretch flex items-start gap-[19px] text-[15.2px] text-[#94a3b8]">
                      <div data-testid="chart-ohlc" className="relative leading-[22.7px]">
                        {liveMarket ? `⊕ ${formatPrice(liveMarket.open)} ↕ ${formatPrice(liveMarket.high)}` : "—"}
                      </div>
                      <div data-testid="chart-bid-ask" className="relative leading-[22.7px]">
                        {liveMarket ? `Bid/Ask ${formatPrice(liveMarket.best_bid)} / ${formatPrice(liveMarket.best_ask)}` : "—"}
                      </div>
                    </div>
                  </div>
                  <div data-testid="chart-volume" className="relative text-[15.2px] leading-[22.7px] text-[#94a3b8]">
                    {liveMarket?.volume != null ? `Vol ${liveMarket.volume.toLocaleString()}` : "Vol —"}
                  </div>
                </div>
                {/* Large last price */}
                <div className="flex flex-col items-start justify-end pt-0 px-0 pb-[4.1px] text-right text-[45.8px] text-[#10b981]">
                  <h2 data-testid="current-price" className="m-0 relative text-[length:inherit] leading-[45.8px] font-normal font-[inherit]">
                    {liveMarket?.last_price ? formatPrice(liveMarket.last_price) : "—"}
                  </h2>
                </div>
              </div>
            </div>
          </div>

          {/* Change display */}
          <div data-testid="chart-change" className={`relative text-[14.1px] leading-[21.2px] shrink-0 ${liveMarket?.change >= 0 ? "text-[#10b981]" : "text-[#ef4444]"}`}>
            {liveMarket?.change != null ? (
              <span>
                {liveMarket.change >= 0 ? "▲" : "▼"} {liveMarket.change >= 0 ? "+" : ""}{formatPrice(liveMarket.change)} ({liveMarket.change_pct >= 0 ? "+" : ""}{liveMarket.change_pct?.toFixed(2)}%)
              </span>
            ) : "—"}
          </div>
        </div>
      </div>

      {/* Chart toolbar + chart area */}
      <div className="flex-1 flex flex-col min-h-0 w-full">
        {USE_CUSTOM_CHART && (
          <div className="flex items-center justify-between px-3 py-1 border-b border-[#1e293b] w-full">
            <TimeframeSelector />
            <ChartOverlayToggles />
          </div>
        )}
        <div className="flex-1 relative min-h-[200px] w-full">
          {USE_CUSTOM_CHART ? <CandlestickChart /> : <TradingViewWidget />}
        </div>

        {/* OR values display */}
        <div className="flex items-center justify-between px-3 py-1.5 border-t border-[#1e293b] text-[12px]">
          <div className="flex items-center gap-4">
            <div>
              <span className="text-[#94a3b8] mr-1">OR UPPER</span>
              <span data-testid="chart-or-upper" className="text-[#06b6d4]">{orStatus?.or_high ? orStatus.or_high.toFixed(2) : "—"}</span>
            </div>
            <div>
              <span className="text-[#94a3b8] mr-1">PRICE</span>
            </div>
            <div>
              <span className="text-[#94a3b8] mr-1">OR LOWER</span>
              <span data-testid="chart-or-lower" className="text-[#06b6d4]">{orStatus?.or_low ? orStatus.or_low.toFixed(2) : "—"}</span>
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
