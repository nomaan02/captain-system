import useChartStore from "../../stores/chartStore";

const TIMEFRAMES = ["15s", "1m", "5m", "15m"];

const TimeframeSelector = () => {
  const timeframe = useChartStore((s) => s.timeframe);
  const setTimeframe = useChartStore((s) => s.setTimeframe);

  return (
    <div className="flex items-center gap-1">
      {TIMEFRAMES.map((tf) => (
        <button
          key={tf}
          onClick={() => setTimeframe(tf)}
          className={`px-2 py-0.5 text-[9px] font-mono leading-[13px] cursor-pointer border border-solid ${
            timeframe === tf
              ? "bg-[rgba(59,246,62,0.2)] border-[rgba(59,246,74,0.4)] text-[#63f63b]"
              : "bg-transparent border-[#1e293b] text-[#64748b] hover:bg-[rgba(100,116,139,0.1)]"
          }`}
        >
          {tf}
        </button>
      ))}
    </div>
  );
};

export default TimeframeSelector;
