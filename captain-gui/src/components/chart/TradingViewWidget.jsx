import { useEffect, useRef, memo } from "react";
import useChartStore from "../../stores/chartStore";

// Map our asset IDs to free TradingView symbols (index/CFD equivalents)
const TV_SYMBOLS = {
  MES: "FOREXCOM:SPXUSD",
  ES: "FOREXCOM:SPXUSD",
  MNQ: "FOREXCOM:NSXUSD",
  NQ: "FOREXCOM:NSXUSD",
  MYM: "BLACKBULL:US30",
  MGC: "OANDA:XAUUSD",
  NKD: "TVC:NI225",
  ZN: "TVC:US10Y",
  ZB: "TVC:US30Y",
  M2K: "CME_MINI:RTY1!",
  MCL: "TVC:USOIL",
  "6E": "FX:EURUSD",
};

// Map our timeframes to TradingView intervals
const TV_INTERVALS = {
  "15s": "15S",
  "1m": "1",
  "5m": "5",
  "15m": "15",
};

const TradingViewWidget = memo(() => {
  const containerRef = useRef(null);
  const selectedAsset = useChartStore((s) => s.selectedAsset);
  const timeframe = useChartStore((s) => s.timeframe);

  useEffect(() => {
    if (!containerRef.current) return;

    // Clear previous widget
    containerRef.current.innerHTML = "";

    const symbol = TV_SYMBOLS[selectedAsset] ?? "CME_MINI:MES1!";
    const interval = TV_INTERVALS[timeframe] ?? "5";

    const script = document.createElement("script");
    script.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    script.type = "text/javascript";
    script.async = true;
    script.innerHTML = JSON.stringify({
      autosize: true,
      symbol,
      interval,
      timezone: "America/New_York",
      theme: "dark",
      style: "1",
      locale: "en",
      backgroundColor: "#0a0f0d",
      gridColor: "rgba(30, 41, 59, 0.5)",
      allow_symbol_change: false,
      hide_top_toolbar: true,
      hide_legend: false,
      save_image: false,
      calendar: false,
      support_host: "https://www.tradingview.com",
    });

    containerRef.current.appendChild(script);
  }, [selectedAsset, timeframe]);

  return (
    <div className="tradingview-widget-container w-full h-full" ref={containerRef}>
      <div className="tradingview-widget-container__widget w-full h-full" />
    </div>
  );
});

TradingViewWidget.displayName = "TradingViewWidget";

export default TradingViewWidget;
