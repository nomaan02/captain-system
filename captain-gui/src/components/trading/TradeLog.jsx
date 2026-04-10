import PropTypes from "prop-types";
import useDashboardStore from "../../stores/dashboardStore";
import { formatCurrency } from "../../utils/formatting";

const computeDuration = (entryTime, exitTime) => {
  if (!entryTime || !exitTime) return "—";
  const ms = new Date(exitTime).getTime() - new Date(entryTime).getTime();
  if (ms < 0) return "—";
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
};

const TradeLog = ({ className = "" }) => {
  const closedTrades = useDashboardStore((s) => s.closedTrades);

  return (
    <div
      className={`w-full h-full flex items-start pt-0 pb-1 pl-px pr-0 text-center text-[11px] text-[#94a3b8] font-mono ${className}`}
    >
      <div className="h-full flex-1 border-[#2e4e5a] border-solid border-b box-border flex flex-col items-start pt-0 px-0 pb-4 overflow-y-auto">
        <div className="self-stretch h-6 border-[#2e4e5a] border-solid border-b box-border flex items-start pt-1 px-2 pb-[3px] shrink-0 text-left text-[10px] text-[#fff] font-sans">
          <div data-testid="tradelog-header" className="relative leading-4">TRADE LOG</div>
        </div>
        <table className="w-full border-collapse text-[10px]">
          <thead>
            <tr className="border-[#2e4e5a] border-solid border-b text-[#fff]">
              <th className="text-left font-normal leading-[13px] pt-0.5 pb-0.5 pl-2">TIME</th>
              <th className="text-left font-normal leading-[13px] pt-0.5 pb-0.5">ASSET</th>
              <th className="text-left font-normal leading-[13px] pt-0.5 pb-0.5">D</th>
              <th className="text-right font-normal leading-[13px] pt-0.5 pb-0.5">{`P&L`}</th>
              <th className="text-right font-normal leading-[13px] pt-0.5 pb-0.5 pr-2.5">DUR</th>
            </tr>
          </thead>
          <tbody>
            {closedTrades.length > 0 ? (
              closedTrades.map((trade, idx) => {
                const pnl = trade.pnl ?? trade.current_pnl ?? 0;
                const isWin = pnl >= 0;
                const bgClass = isWin ? "bg-[rgba(16,185,129,0.05)]" : "bg-[rgba(239,68,68,0.05)]";
                const pnlColor = isWin ? "text-[#00ad74]" : "text-[#ef4444]";
                const dirLetter = trade.direction === "LONG" ? "L" : "S";
                const dirColor = trade.direction === "LONG" ? "text-[#00ad74]" : "text-[#ef4444]";
                const time = trade.entry_time ? new Date(trade.entry_time).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "America/New_York" }) : "—";
                const duration = computeDuration(trade.entry_time, trade.exit_time);
                return (
                  <tr data-testid="tradelog-row" key={trade.trade_id ?? trade.order_id ?? idx} className={bgClass}>
                    <td className="text-left leading-4 pt-px pb-0 pl-2">{time}</td>
                    <td className="text-left leading-4 pt-px pb-0 text-[#e2e8f0]">{trade.asset_id ?? trade.asset ?? "—"}</td>
                    <td className={`text-left leading-4 pt-px pb-0 ${dirColor}`}>{dirLetter}</td>
                    <td className={`text-right leading-4 pt-px pb-0 ${pnlColor}`}>{pnl !== 0 || trade.pnl != null ? (pnl >= 0 ? "+" : "") + Math.round(pnl) : "—"}</td>
                    <td className="text-right leading-4 pt-px pb-0 pr-2.5 text-[#fff]">{duration}</td>
                  </tr>
                );
              })
            ) : (
              <tr>
                <td colSpan={5} className="text-center py-4 text-[10px] text-[#64748b]">
                  No trades today
                </td>
              </tr>
            )}
          </tbody>
        </table>
        <div className="self-stretch h-6 border-[#2e4e5a] border-solid border-t box-border flex items-start pt-[3px] px-2 pb-[5px] shrink-0 text-left text-[11px] text-[#fff]">
          <div data-testid="tradelog-total" className="relative leading-4">
            <span>{`Total: `}</span>
            <span className="text-[#00ad74]">{formatCurrency(closedTrades.reduce((sum, t) => sum + (t.pnl ?? t.current_pnl ?? 0), 0), { showSign: true })}</span>
            <span>{` | ${closedTrades.length} trades`}</span>
          </div>
        </div>
      </div>
    </div>
  );
};

TradeLog.propTypes = {
  className: PropTypes.string,
};

export default TradeLog;
