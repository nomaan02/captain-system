import { useEffect } from "react";
import useReplayStore from "../../stores/replayStore";
import { formatCurrency, formatTimestamp } from "../../utils/formatting";
import api from "../../api/client";

const ReplayHistory = () => {
  const replayHistory = useReplayStore((s) => s.replayHistory);

  useEffect(() => {
    api.replayHistory()
      .then((data) => {
        useReplayStore.getState().setHistory(data.history || data || []);
      })
      .catch(() => {});
  }, []);

  if (!replayHistory || replayHistory.length === 0) {
    return (
      <div data-testid="replay-history" className="p-3">
        <div className="text-[9px] uppercase tracking-[1px] text-[#0faf7a] font-mono mb-2">History</div>
        <div className="text-[10px] text-[#64748b] font-mono text-center py-3">
          No replay history
        </div>
      </div>
    );
  }

  return (
    <div data-testid="replay-history" className="p-3 space-y-2">
      <div className="text-[9px] uppercase tracking-[1px] text-[#0faf7a] font-mono">History</div>

      <div className="max-h-[200px] overflow-y-auto">
        {replayHistory.map((entry, idx) => {
          const pnl = entry.total_pnl ?? entry.pnl ?? 0;
          return (
            <div
              key={entry.replay_id || idx}
              data-testid={`replay-history-entry-${idx}`}
              className="flex items-center justify-between py-[3px] px-1 text-[9px] font-mono border-b border-[#1e293b] hover:bg-[rgba(255,255,255,0.02)]"
            >
              <div className="flex flex-col gap-[1px]">
                <div className="flex items-center gap-2">
                  <span className="text-[#e2e8f0]">{entry.date || "--"}</span>
                  <span className="text-[7px] px-1 border border-solid border-[#374151] text-[#64748b]">
                    {entry.session || "--"}
                  </span>
                </div>
                <span className="text-[7px] text-[#64748b]">
                  {entry.created_at ? formatTimestamp(entry.created_at) : "--"}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[8px] text-[#64748b]">
                  {entry.trades ?? "--"} trades
                </span>
                <span className={`text-[10px] font-semibold ${pnl >= 0 ? "text-[#10b981]" : "text-[#ef4444]"}`}>
                  {formatCurrency(pnl, { showSign: true })}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default ReplayHistory;
