import PropTypes from "prop-types";
import useDashboardStore from "../../stores/dashboardStore";
import useChartStore from "../../stores/chartStore";
import { formatPrice } from "../../utils/formatting";

const MarketTicker = ({ className = "" }) => {
  const liveMarket = useDashboardStore((s) => s.liveMarket);
  const selectedAsset = useChartStore((s) => s.selectedAsset);
  const setSelectedAsset = useChartStore((s) => s.setSelectedAsset);

  return (
    <nav
      data-testid="market-status-panel"
      className={`m-0 w-full overflow-x-auto flex items-start shrink-0 text-center text-[9px] text-[#0faf7a] font-['JetBrains_Mono'] ${className}`}
    >
      {/* MES — wired to liveMarket */}
      <div
        data-testid="ticker-MES"
        onClick={() => setSelectedAsset("MES")}
        className={`cursor-pointer self-stretch border-[#1a3038] border-solid border-r border-b flex flex-col items-start pt-[5.9px] pb-[5px] pl-3 pr-[11px] gap-[1.1px] shrink-0 ${
          selectedAsset === "MES" ? "bg-[#0d1f1a]" : ""
        }`}
      >
        <div className="flex items-start py-0 pl-0 pr-5 gap-[5.3px]">
          <div className="relative leading-[13.5px] font-medium">MES</div>
          <div className="flex flex-col items-start pt-[4.6px] px-0 pb-0">
            <div className="w-[4.5px] h-[4.5px] relative rounded-full bg-[#0faf7a]" />
          </div>
        </div>
        <div className="flex items-start gap-[5px] text-[9.8px] text-[#fff]">
          <div data-testid="ticker-MES-price" className="relative leading-[14.7px] font-medium">
            {liveMarket?.last_price ? formatPrice(liveMarket.last_price) : "—"}
          </div>
          <div className="flex flex-col items-start pt-[1.7px] px-0 pb-0 text-[7.5px]">
            <div
              className={`self-stretch relative leading-[11.3px] font-medium ${
                liveMarket?.change_pct >= 0 ? "text-[#0faf7a]" : "text-[#ef4444]"
              }`}
            >
              {liveMarket?.change_pct != null
                ? `${liveMarket.change_pct >= 0 ? "+" : ""}${liveMarket.change_pct.toFixed(2)}%`
                : "—"}

            </div>
          </div>
        </div>
      </div>

      {/* MNQ */}
      <div
        data-testid="ticker-MNQ"
        onClick={() => setSelectedAsset("MNQ")}
        className={`cursor-pointer border-[#1a3038] border-solid border-r flex items-start pt-[6.5px] pb-[6.3px] pl-3 pr-[11px] gap-[4.9px] shrink-0 ${
          selectedAsset === "MNQ" ? "bg-[#0d1f1a]" : ""
        }`}
      >
        <div className="flex flex-col items-start gap-[1.2px]">
          <div className="flex items-start py-0 pl-0 pr-[21px] gap-[5.2px]">
            <div className="relative leading-[13.5px] font-medium">MNQ</div>
            <div className="flex flex-col items-start pt-[4.7px] px-0 pb-0">
              <div className="w-[4.5px] h-[4.5px] relative rounded-full bg-[#0faf7a]" />
            </div>
          </div>
          <div data-testid="ticker-MNQ-price" className="relative text-[9.8px] leading-[14.7px] font-medium text-[#fff]">
            19284.83{/* NOTE: hardcoded, not from store */}
          </div>
        </div>
        <div className="flex flex-col items-start pt-[16.9px] px-0 pb-0 text-[7.5px]">
          <div className="self-stretch relative leading-[11.3px] font-medium">
            +0.24%
          </div>
        </div>
      </div>

      {/* ES */}
      <div
        data-testid="ticker-ES"
        onClick={() => setSelectedAsset("ES")}
        className={`cursor-pointer border-[#1a3038] border-solid border-r flex flex-col items-start pt-[6.5px] pb-[6.3px] pl-3 pr-[11px] gap-[1.2px] shrink-0 text-[#fff] ${
          selectedAsset === "ES" ? "bg-[#0d1f1a]" : ""
        }`}
      >
        <div className="relative leading-[13.5px] font-medium">ES</div>
        <div className="flex items-start gap-[5px] text-[9.8px]">
          <div data-testid="ticker-ES-price" className="relative leading-[14.7px] font-medium">5429.65{/* NOTE: hardcoded, not from store */}</div>
          <div className="flex flex-col items-start pt-[1.7px] px-0 pb-0 text-[7.5px] text-[#ef4444]">
            <div className="self-stretch relative leading-[11.3px] font-medium">
              -0.22%
            </div>
          </div>
        </div>
      </div>

      {/* NQ */}
      <div
        data-testid="ticker-NQ"
        onClick={() => setSelectedAsset("NQ")}
        className={`cursor-pointer border-[#1a3038] border-solid border-r flex flex-col items-start pt-[6.5px] pb-[6.3px] pl-3 pr-[11px] gap-[1.2px] shrink-0 text-[#fff] ${
          selectedAsset === "NQ" ? "bg-[#0d1f1a]" : ""
        }`}
      >
        <div className="relative leading-[13.5px] font-medium">NQ</div>
        <div className="flex items-start gap-[4.9px] text-[9.8px]">
          <div data-testid="ticker-NQ-price" className="relative leading-[14.7px] font-medium">19283.92{/* NOTE: hardcoded, not from store */}</div>
          <div className="flex flex-col items-start pt-[1.7px] px-0 pb-0 text-[7.5px] text-[#0faf7a]">
            <div className="self-stretch relative leading-[11.3px] font-medium">
              +0.23%
            </div>
          </div>
        </div>
      </div>

      {/* MYM */}
      <div
        data-testid="ticker-MYM"
        onClick={() => setSelectedAsset("MYM")}
        className={`cursor-pointer border-[#1a3038] border-solid border-r flex items-start pt-[6.5px] pb-[6.3px] pl-3 pr-[11px] gap-[4.9px] shrink-0 ${
          selectedAsset === "MYM" ? "bg-[#0d1f1a]" : ""
        }`}
      >
        <div className="flex flex-col items-start gap-[1.2px]">
          <div className="flex items-start py-0 pl-0 pr-[21px] gap-[5.2px]">
            <div className="relative leading-[13.5px] font-medium">MYM</div>
            <div className="flex flex-col items-start pt-[4.7px] px-0 pb-0">
              <div className="w-[4.5px] h-[4.5px] relative rounded-full bg-[#0faf7a]" />
            </div>
          </div>
          <div data-testid="ticker-MYM-price" className="relative text-[9.8px] leading-[14.7px] font-medium text-[#fff]">
            39842.91{/* NOTE: hardcoded, not from store */}
          </div>
        </div>
        <div className="flex flex-col items-start pt-[16.9px] px-0 pb-0 text-[7.5px] text-[#ef4444]">
          <div className="self-stretch relative leading-[11.3px] font-medium">
            -0.19%
          </div>
        </div>
      </div>

      {/* MGC */}
      <div
        data-testid="ticker-MGC"
        onClick={() => setSelectedAsset("MGC")}
        className={`cursor-pointer border-[#1a3038] border-solid border-r flex flex-col items-start pt-[6.5px] pb-[6.3px] pl-3 pr-[11px] gap-[1.2px] shrink-0 text-[#fff] ${
          selectedAsset === "MGC" ? "bg-[#0d1f1a]" : ""
        }`}
      >
        <div className="relative leading-[13.5px] font-medium">MGC</div>
        <div className="flex items-start gap-[5px] text-[9.8px]">
          <div data-testid="ticker-MGC-price" className="relative leading-[14.7px] font-medium">2634.16{/* NOTE: hardcoded, not from store */}</div>
          <div className="flex flex-col items-start pt-[1.7px] px-0 pb-0 text-[7.5px] text-[#0faf7a]">
            <div className="self-stretch relative leading-[11.3px] font-medium">
              +0.32%
            </div>
          </div>
        </div>
      </div>

      {/* NKD */}
      <div
        data-testid="ticker-NKD"
        onClick={() => setSelectedAsset("NKD")}
        className={`cursor-pointer border-[#1a3038] border-solid border-r flex flex-col items-start pt-[6.5px] pb-[6.3px] pl-3 pr-[11px] gap-[1.2px] shrink-0 text-[#fff] ${
          selectedAsset === "NKD" ? "bg-[#0d1f1a]" : ""
        }`}
      >
        <div className="relative leading-[13.5px] font-medium">NKD</div>
        <div className="flex items-start gap-[4.9px] text-[9.8px]">
          <div data-testid="ticker-NKD-price" className="relative leading-[14.7px] font-medium">38451.03{/* NOTE: hardcoded, not from store */}</div>
          <div className="flex flex-col items-start pt-[1.7px] px-0 pb-0 text-[7.5px] text-[#0faf7a]">
            <div className="self-stretch relative leading-[11.3px] font-medium">
              +0.33%
            </div>
          </div>
        </div>
      </div>

      {/* ZN */}
      <div
        data-testid="ticker-ZN"
        onClick={() => setSelectedAsset("ZN")}
        className={`cursor-pointer border-[#1a3038] border-solid border-r flex items-start pt-[6.5px] pb-[6.3px] pl-3 pr-[11px] gap-[5.2px] shrink-0 text-[#fff] ${
          selectedAsset === "ZN" ? "bg-[#0d1f1a]" : ""
        }`}
      >
        <div className="flex flex-col items-start gap-[1.2px]">
          <div className="relative leading-[13.5px] font-medium">ZN</div>
          <div data-testid="ticker-ZN-price" className="relative text-[9.8px] leading-[14.7px] font-medium">
            110.27{/* NOTE: hardcoded, not from store */}
          </div>
        </div>
        <div className="flex-1 flex flex-col items-start pt-[16.9px] px-0 pb-0 text-[7.5px] text-[#ef4444]">
          <div className="self-stretch relative leading-[11.3px] font-medium">
            -0.07%
          </div>
        </div>
      </div>

      {/* MCL */}
      <div
        data-testid="ticker-MCL"
        onClick={() => setSelectedAsset("MCL")}
        className={`cursor-pointer border-[#1a3038] border-solid border-r flex items-start pt-[6.5px] pb-[6.3px] pl-3 pr-[11px] gap-[5.3px] shrink-0 text-[#fff] ${
          selectedAsset === "MCL" ? "bg-[#0d1f1a]" : ""
        }`}
      >
        <div className="flex flex-col items-start gap-[1.2px]">
          <div className="relative leading-[13.5px] font-medium">MCL</div>
          <div data-testid="ticker-MCL-price" className="relative text-[9.8px] leading-[14.7px] font-medium">
            71.90{/* NOTE: hardcoded, not from store */}
          </div>
        </div>
        <div className="flex-1 flex flex-col items-start pt-[16.9px] px-0 pb-0 text-[7.5px] text-[#ef4444]">
          <div className="self-stretch relative leading-[11.3px] font-medium">
            -0.50%
          </div>
        </div>
      </div>

      {/* 6E */}
      <div
        data-testid="ticker-6E"
        onClick={() => setSelectedAsset("6E")}
        className={`cursor-pointer border-[#1a3038] border-solid border-r flex items-start pt-[6.5px] pb-[6.3px] pl-3 pr-[11px] gap-[5.4px] shrink-0 text-[#fff] ${
          selectedAsset === "6E" ? "bg-[#0d1f1a]" : ""
        }`}
      >
        <div className="flex flex-col items-start gap-[1.2px]">
          <div className="relative leading-[13.5px] font-medium">6E</div>
          <div data-testid="ticker-6E-price" className="relative text-[9.8px] leading-[14.7px] font-medium">
            1.08{/* NOTE: hardcoded, not from store */}
          </div>
        </div>
        <div className="flex-1 flex flex-col items-start pt-[16.9px] px-0 pb-0 text-[7.5px] text-[#0faf7a]">
          <div className="self-stretch relative leading-[11.3px] font-medium">
            +0.09%
          </div>
        </div>
      </div>
    </nav>
  );
};

MarketTicker.propTypes = {
  className: PropTypes.string,
};

export default MarketTicker;
