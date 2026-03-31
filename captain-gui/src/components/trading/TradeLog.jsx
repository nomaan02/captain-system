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
      className={`w-full h-full flex items-start pt-0 pb-[4.7px] pl-px pr-0 text-center text-[10.8px] text-[#94a3b8] font-['JetBrains_Mono'] ${className}`}
    >
      <div className="h-full flex-1 border-[#2e4e5a] border-solid border-b-[0.9px] box-border flex flex-col items-start pt-0 px-0 pb-[17px] overflow-y-auto">
        <div className="self-stretch h-[24.1px] border-[#2e4e5a] border-solid border-b-[0.9px] box-border flex items-start pt-[4.2px] px-2 pb-[3px] shrink-0 text-left text-[9.7px] text-[#fff] font-[Inter]">
          <div data-testid="tradelog-header" className="relative leading-[14.6px]">TRADE LOG</div>
        </div>
        <div className="self-stretch h-[18.2px] border-[#2e4e5a] border-solid border-b-[0.9px] box-border flex items-start justify-between pt-[2.2px] pb-0.5 pl-2 pr-2.5 gap-5 shrink-0 text-[8.6px] text-[#fff]">
          <div className="flex items-start gap-[33px]">
            <div className="relative leading-[13px]">TIME</div>
            <div className="flex items-start gap-[11.4px]">
              <div className="relative leading-[13px]">ASSET</div>
              <div className="relative leading-[13px]">D</div>
            </div>
          </div>
          <div className="flex items-start gap-[37.3px]">
            <div className="relative leading-[13px]">{`P&L`}</div>
            <div className="relative leading-[13px]">DUR</div>
          </div>
        </div>
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
              <div data-testid="tradelog-row" key={trade.trade_id ?? trade.order_id ?? idx} className={`self-stretch ${bgClass} flex items-start justify-between pt-[1.1px] pb-[0.2px] pl-2 pr-2.5 gap-5 shrink-0`}>
                <div className="flex items-start gap-[20.2px]">
                  <div className="relative leading-[16.2px]">{time}</div>
                  <div className="relative leading-[16.2px] text-[#e2e8f0]">{trade.asset_id ?? trade.asset ?? "—"}</div>
                  <div className={`relative leading-[16.2px] ${dirColor}`}>{dirLetter}</div>
                </div>
                <div className="flex items-start gap-[33.3px] text-left">
                  <div className={`relative leading-[16.2px] ${pnlColor}`}>{pnl !== 0 || trade.pnl != null ? (pnl >= 0 ? "+" : "") + Math.round(pnl) : "—"}</div>
                  <div className="relative leading-[16.2px] text-[#fff] text-center">
                    {duration}
                  </div>
                </div>
              </div>
            );
          })
        ) : (
          <div className="self-stretch flex items-center justify-center py-4 text-[9.7px] text-[#64748b]">
            No trades today
          </div>
        )}
        <div className="self-stretch h-[24.1px] border-[#2e4e5a] border-solid border-t-[0.9px] box-border flex items-start pt-[3px] px-2 pb-[5px] shrink-0 text-left text-[9.7px] text-[#fff]">
          <div data-testid="tradelog-total" className="relative leading-[14.6px]">
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
