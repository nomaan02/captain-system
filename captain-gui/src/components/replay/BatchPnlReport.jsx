import { useState } from "react";
import useReplayStore from "../../stores/replayStore";
import { formatCurrency } from "../../utils/formatting";

const BatchPnlReport = () => {
  const batchStatus = useReplayStore((s) => s.batchStatus);
  const batchDayResults = useReplayStore((s) => s.batchDayResults);
  const batchSummary = useReplayStore((s) => s.batchSummary);
  const batchCurrentDay = useReplayStore((s) => s.batchCurrentDay);
  const batchCompletedDays = useReplayStore((s) => s.batchCompletedDays);
  const batchTotalDays = useReplayStore((s) => s.batchTotalDays);

  const [view, setView] = useState("daily"); // "daily" | "overall"

  if (batchStatus === "idle") return null;

  // Running state -- show progress + live day results
  if (batchStatus === "running" || batchStatus === "paused") {
    return (
      <div data-testid="batch-pnl-report" className="p-3 space-y-2">
        <div className="text-[9px] uppercase tracking-[1px] text-[#0faf7a] font-mono">
          Batch Progress
        </div>
        <div className="flex justify-between text-[10px] font-mono">
          <span className="text-[#64748b]">
            Day {batchCompletedDays} / {batchTotalDays}
          </span>
          {batchCurrentDay && (
            <span className="text-[#06b6d4]">{batchCurrentDay}</span>
          )}
        </div>
        {/* Progress bar */}
        <div
          role="progressbar"
          aria-valuenow={batchCompletedDays}
          aria-valuemin={0}
          aria-valuemax={batchTotalDays}
          aria-label={`Batch progress: ${batchCompletedDays} of ${batchTotalDays} days`}
          className="h-[3px] bg-[#1e293b] rounded-full overflow-hidden"
        >
          <div
            className="h-full bg-[#0faf7a] transition-all duration-300"
            style={{
              width: `${Math.round(
                (batchCompletedDays / Math.max(batchTotalDays, 1)) * 100
              )}%`,
            }}
          />
        </div>
        {/* Live day-by-day rows */}
        {batchDayResults.length > 0 && (
          <div className="max-h-[200px] overflow-y-auto border-t border-[#1e293b] pt-1 [&::-webkit-scrollbar]:w-[6px] [&::-webkit-scrollbar-track]:bg-[#0d1117] [&::-webkit-scrollbar-thumb]:bg-[#374151] [&::-webkit-scrollbar-thumb]:rounded">
            {batchDayResults.map((d) => (
              <div
                key={d.date}
                className="flex justify-between py-[2px] text-[9px] font-mono border-b border-[#1e293b]"
              >
                <span className="text-[#e2e8f0]">{d.date?.slice(5)}</span>
                <span className="text-[#64748b]">{d.trades}t</span>
                <span
                  className={
                    d.pnl >= 0 ? "text-[#10b981]" : "text-[#ef4444]"
                  }
                >
                  {formatCurrency(d.pnl, { showSign: true })}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  // Complete -- toggle between day-by-day and overall views
  return (
    <div data-testid="batch-pnl-report" className="p-3 space-y-3">
      {/* Header with view toggle + download */}
      <div className="flex items-center justify-between">
        <div className="text-[9px] uppercase tracking-[1px] text-[#0faf7a] font-mono">
          Period Report
        </div>
        <div className="flex gap-[2px]">
          {["daily", "overall"].map((v) => (
            <button
              key={v}
              data-testid={`batch-view-${v}`}
              onClick={() => setView(v)}
              aria-pressed={view === v}
              className={`px-2 py-[2px] text-[10px] font-mono border border-solid cursor-pointer transition-colors ${
                view === v
                  ? "bg-[rgba(15,175,122,0.2)] border-[rgba(15,175,122,0.4)] text-[#0faf7a]"
                  : "bg-[#111827] border-[#1e293b] text-[#64748b]"
              }`}
            >
              {v === "daily" ? "Day-by-Day" : "Overall"}
            </button>
          ))}
          <button
            data-testid="batch-download-csv"
            aria-label="Download batch results as CSV"
            onClick={() => handleDownloadCSV(batchDayResults)}
            className="px-2 py-[2px] text-[10px] font-mono border border-solid bg-[#111827] border-[#1e293b] text-[#64748b] cursor-pointer hover:text-[#e2e8f0] transition-colors"
          >
            CSV
          </button>
        </div>
      </div>

      {view === "daily" ? (
        <DailyView days={batchDayResults} />
      ) : (
        <OverallView summary={batchSummary} />
      )}
    </div>
  );
};

const DailyView = ({ days }) => (
  <div>
    {/* Header */}
    <div className="grid grid-cols-5 gap-1 text-[7px] uppercase tracking-[0.5px] text-[#64748b] font-mono border-b border-[#1e293b] pb-1">
      <span>Date</span>
      <span className="text-center">Trades</span>
      <span className="text-center">W/L</span>
      <span className="text-right">P&L</span>
      <span className="text-right">Cum</span>
    </div>
    <div className="max-h-[300px] overflow-y-auto [&::-webkit-scrollbar]:w-[6px] [&::-webkit-scrollbar-track]:bg-[#0d1117] [&::-webkit-scrollbar-thumb]:bg-[#374151] [&::-webkit-scrollbar-thumb]:rounded">
      {days.map((d) => (
        <div
          key={d.date}
          className="grid grid-cols-5 gap-1 py-[3px] text-[9px] font-mono border-b border-[#1e293b]"
        >
          <span className="text-[#e2e8f0]">{d.date?.slice(5)}</span>
          <span className="text-center text-[#e2e8f0]">{d.trades}</span>
          <span className="text-center">
            <span className="text-[#10b981]">{d.wins}</span>
            <span className="text-[#64748b]">/</span>
            <span className="text-[#ef4444]">{d.losses}</span>
          </span>
          <span
            className={`text-right ${
              d.pnl >= 0 ? "text-[#10b981]" : "text-[#ef4444]"
            }`}
          >
            {formatCurrency(d.pnl, { showSign: true })}
          </span>
          <span
            className={`text-right ${
              d.cumulativePnl >= 0 ? "text-[#10b981]" : "text-[#ef4444]"
            }`}
          >
            {formatCurrency(d.cumulativePnl, { showSign: true })}
          </span>
        </div>
      ))}
    </div>
  </div>
);

const OverallView = ({ summary }) => {
  if (!summary)
    return (
      <div className="text-[10px] text-[#64748b] font-mono">No data</div>
    );

  const stats = [
    { label: "Total Trades", value: summary.total_trades },
    {
      label: "Win Rate",
      value: `${summary.win_rate}%`,
    },
    {
      label: "Best Day",
      value: formatCurrency(summary.best_day, { showSign: true }),
      color: "#10b981",
    },
    {
      label: "Worst Day",
      value: formatCurrency(summary.worst_day, { showSign: true }),
      color: "#ef4444",
    },
    {
      label: "Avg Daily P&L",
      value: formatCurrency(summary.avg_daily_pnl, { showSign: true }),
      color: summary.avg_daily_pnl >= 0 ? "#10b981" : "#ef4444",
    },
    {
      label: "Max Drawdown",
      value: formatCurrency(summary.max_drawdown),
      color: "#ef4444",
    },
    {
      label: "Profitable Days",
      value: `${summary.profitable_days} / ${summary.total_days}`,
    },
    {
      label: "Losing Days",
      value: `${summary.losing_days} / ${summary.total_days}`,
    },
  ];

  return (
    <div className="space-y-2">
      {/* Large PnL display */}
      <div className="text-center py-2">
        <div className="text-[7px] uppercase tracking-[0.5px] text-[#64748b] font-mono mb-1">
          Total P&L
        </div>
        <div
          data-testid="batch-total-pnl"
          className="text-[22px] font-mono font-semibold"
          style={{
            color: summary.total_pnl >= 0 ? "#10b981" : "#ef4444",
          }}
        >
          {formatCurrency(summary.total_pnl, { showSign: true })}
        </div>
        <div className="text-[8px] text-[#64748b] font-mono">
          {summary.total_days} trading day{summary.total_days !== 1 ? "s" : ""}
        </div>
      </div>

      {/* Stats */}
      <div className="space-y-1">
        {stats.map((s) => (
          <div
            key={s.label}
            className="flex justify-between text-[9px] font-mono"
          >
            <span className="text-[#64748b]">{s.label}</span>
            <span style={{ color: s.color || "#e2e8f0" }}>{s.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

function handleDownloadCSV(dayResults) {
  if (!dayResults?.length) return;
  const headers = "Date,Trades,Wins,Losses,PnL,Cumulative PnL\n";
  const rows = dayResults
    .map(
      (d) =>
        `${d.date},${d.trades},${d.wins},${d.losses},${d.pnl},${d.cumulativePnl}`
    )
    .join("\n");
  const blob = new Blob([headers + rows], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `batch_replay_${dayResults[0]?.date}_to_${
    dayResults[dayResults.length - 1]?.date
  }.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export default BatchPnlReport;
