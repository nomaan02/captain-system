import { useDashboardStore } from "@/stores/dashboardStore";
import { Panel } from "@/components/ui/panel";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { formatCurrency, formatTimestamp } from "@/utils/formatters";

export function TodaysTradesCell() {
  const positions = useDashboardStore((s) => s.openPositions);

  return (
    <Panel
      title="TODAY'S TRADES"
      accent="gray"
      headerRight={
        <Badge variant="neutral" size="sm">
          {positions.length}
        </Badge>
      }
    >
      <ScrollArea className="max-h-[200px]">
        {positions.length === 0 ? (
          <div className="py-2 text-[11px] text-dim">No trades today</div>
        ) : (
          <div>
            {/* Header */}
            <div
              className="grid text-[11px] font-medium text-dim"
              style={{
                gridTemplateColumns: "50px 50px 70px 70px 70px 50px minmax(0, 1fr)",
                padding: "4px 6px",
                backgroundColor: "#111113",
                borderRadius: "3px 3px 0 0",
              }}
            >
              <span>Time</span>
              <span>Dir</span>
              <span>Entry</span>
              <span>TP</span>
              <span>SL</span>
              <span>Ct</span>
              <span className="text-right">P&L</span>
            </div>

            {/* Body rows */}
            {positions.map((pos) => {
              const pnl = pos.current_pnl ?? 0;
              const isLong = pos.direction === "LONG";
              const time = pos.entry_time
                ? new Date(pos.entry_time).toLocaleTimeString("en-US", {
                    timeZone: "America/New_York",
                    hour: "2-digit",
                    minute: "2-digit",
                    hour12: false,
                  })
                : "—";

              return (
                <div
                  key={pos.signal_id}
                  className="grid text-[11px]"
                  style={{
                    gridTemplateColumns: "50px 50px 70px 70px 70px 50px minmax(0, 1fr)",
                    padding: "4px 6px",
                    borderBottom: "1px solid #111113",
                    color: "#a1a1aa",
                  }}
                >
                  <span>{time}</span>
                  <span style={{ color: isLong ? "#4ade80" : "#f87171" }}>
                    {pos.direction}
                  </span>
                  <span>{formatCurrency(pos.entry_price)}</span>
                  <span>{formatCurrency(pos.tp_level)}</span>
                  <span>{formatCurrency(pos.sl_level)}</span>
                  <span>{pos.contracts}</span>
                  <span
                    className="text-right font-semibold"
                    style={{ color: pnl >= 0 ? "#4ade80" : "#f87171" }}
                  >
                    {pnl >= 0 ? "+" : ""}
                    {formatCurrency(pnl)}
                  </span>
                </div>
              );
            })}
          </div>
        )}

        {/* Win/Loss streak */}
        {positions.length > 0 && (
          <div className="mt-2 flex gap-0.5">
            {positions.map((pos, i) => {
              const isWin = (pos.current_pnl ?? 0) >= 0;
              const isFirst = i === 0;
              const isLast = i === positions.length - 1;
              return (
                <div
                  key={pos.signal_id}
                  className="flex flex-1 items-center justify-center text-[11px] font-semibold"
                  style={{
                    height: 14,
                    backgroundColor: isWin ? "#4ade80" : "#f87171",
                    color: isWin ? "#052e16" : "#450a0a",
                    borderRadius: isFirst
                      ? "2px 0 0 2px"
                      : isLast
                        ? "0 2px 2px 0"
                        : "0",
                  }}
                >
                  {isWin ? "W" : "L"}
                </div>
              );
            })}
          </div>
        )}
      </ScrollArea>
    </Panel>
  );
}
