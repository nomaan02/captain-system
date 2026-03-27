import { useDashboardStore } from "@/stores/dashboardStore";
import { TpSlProximityBar } from "./TpSlProximityBar";
import { formatCurrency, formatTimestamp } from "@/utils/formatters";
import { ArrowUp, ArrowDown } from "lucide-react";

export function PositionMonitor() {
  const positions = useDashboardStore((s) => s.openPositions);

  if (positions.length === 0) {
    return (
      <div className="panel">
        <div className="panel-header">Open Positions</div>
        <p className="py-4 text-sm text-gray-400">No open positions</p>
      </div>
    );
  }

  return (
    <div className="panel">
      <div className="panel-header">
        <span>Open Positions</span>
        <span className="text-xs font-normal text-gray-400">{positions.length} active</span>
      </div>
      <div className="space-y-3">
        {positions.map((pos) => (
          <PositionCard key={pos.signal_id} position={pos} />
        ))}
      </div>
    </div>
  );
}

function PositionCard({ position }: { position: ReturnType<typeof useDashboardStore.getState>["openPositions"][0] }) {
  const isLong = position.direction === "LONG";
  const pnl = position.current_pnl ?? 0;
  const pnlColor = pnl >= 0 ? "text-green-500" : "text-red-500";

  return (
    <div className="rounded-lg border border-gray-200 p-3 dark:border-gray-700">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className={`flex items-center gap-1 text-sm font-semibold ${isLong ? "text-green-500" : "text-red-500"}`}>
            {isLong ? <ArrowUp className="h-4 w-4" /> : <ArrowDown className="h-4 w-4" />}
            {position.direction}
          </div>
          <span className="text-sm font-medium">{position.asset}</span>
          <span className="text-xs text-gray-400">{position.contracts} ct</span>
        </div>
        <span className={`text-sm font-bold ${pnlColor}`}>
          {formatCurrency(pnl)}
        </span>
      </div>

      <div className="mt-2">
        <TpSlProximityBar
          entry={position.entry_price}
          tp={position.tp_level}
          sl={position.sl_level}
          current={position.entry_price + (pnl / (position.contracts * 50 || 1))}
        />
      </div>

      <div className="mt-2 grid grid-cols-4 gap-2 text-xs text-gray-500 dark:text-gray-400">
        <div>
          <span className="block text-[10px] uppercase">Entry</span>
          {formatCurrency(position.entry_price)}
        </div>
        <div>
          <span className="block text-[10px] uppercase text-green-500">TP</span>
          {formatCurrency(position.tp_level)}
        </div>
        <div>
          <span className="block text-[10px] uppercase text-red-500">SL</span>
          {formatCurrency(position.sl_level)}
        </div>
        <div>
          <span className="block text-[10px] uppercase">Account</span>
          {position.account_id}
        </div>
      </div>

      <div className="mt-1 text-[10px] text-gray-400">
        Opened {formatTimestamp(position.entry_time)} | {position.signal_id}
      </div>
    </div>
  );
}
