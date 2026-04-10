import PropTypes from "prop-types";
import useDashboardStore from "../../stores/dashboardStore";
import useChartStore from "../../stores/chartStore";
import { formatPrice } from "../../utils/formatting";

// TODO: liveMarket store streams one asset at a time (keyed by contract_id).
// Tickers without a matching feed show "---". Wire multi-asset feed when backend supports it.
const TICKERS = ["MES", "MNQ", "ES", "NQ", "MYM", "MGC", "NKD", "ZN", "MCL", "6E"];

const MarketTicker = ({ className = "" }) => {
  const liveMarket = useDashboardStore((s) => s.liveMarket);
  const selectedAsset = useChartStore((s) => s.selectedAsset);
  const setSelectedAsset = useChartStore((s) => s.setSelectedAsset);

  return (
    <div className={`relative ${className}`}>
      <nav
        data-testid="market-status-panel"
        className="m-0 w-full overflow-x-auto flex items-stretch shrink-0 text-[10px] text-[#0faf7a] font-['JetBrains_Mono']"
        aria-label="Market tickers"
      >
        {TICKERS.map((symbol) => {
          const hasData = liveMarket?.contract_id === symbol;
          const price =
            hasData && liveMarket.last_price != null
              ? formatPrice(liveMarket.last_price)
              : "---";
          const changePct = hasData ? liveMarket.change_pct : null;
          const isSelected = selectedAsset === symbol;
          const changeColor =
            changePct != null
              ? changePct >= 0
                ? "text-[#0faf7a]"
                : "text-[#ef4444]"
              : "text-[#64748b]";

          return (
            <button
              key={symbol}
              type="button"
              data-testid={`ticker-${symbol}`}
              onClick={() => setSelectedAsset(symbol)}
              aria-current={isSelected ? "true" : undefined}
              className={`cursor-pointer border-r border-solid border-[#1a3038] flex flex-col items-start pt-1.5 pb-1 pl-3 pr-3 gap-px shrink-0 text-left ${
                isSelected ? "bg-[#0d1f1a]" : ""
              }`}
            >
              <span className="flex items-center gap-1.5">
                <span className="font-medium leading-[14px]">{symbol}</span>
                <span
                  className={`size-1.5 rounded-full ${hasData ? "bg-[#0faf7a]" : "bg-[#64748b]"}`}
                  aria-hidden="true"
                />
                <span className="sr-only">
                  {hasData ? "Connected" : "No data"}
                </span>
              </span>
              <span className="flex items-baseline gap-1.5 tabular-nums">
                <span
                  data-testid={`ticker-${symbol}-price`}
                  className="font-medium leading-[15px] text-[#fff]"
                >
                  {price}
                </span>
                <span className={`font-medium leading-[14px] ${changeColor}`}>
                  {changePct != null
                    ? `${changePct >= 0 ? "+" : ""}${changePct.toFixed(2)}%`
                    : "---"}
                </span>
              </span>
            </button>
          );
        })}
      </nav>
      {/* FIX-044: Scroll fade indicator for horizontal overflow */}
      <div
        className="pointer-events-none absolute right-0 top-0 bottom-0 w-8 bg-gradient-to-l from-surface to-transparent"
        aria-hidden="true"
      />
    </div>
  );
};

MarketTicker.propTypes = {
  className: PropTypes.string,
};

export default MarketTicker;
