import { useDashboardStore } from "@/stores/dashboardStore";
import { ProgressBar } from "@/components/ProgressBar";
import { formatCurrency } from "@/utils/formatters";
import { Wallet } from "lucide-react";

export function SiloDrawdownBar() {
  const silo = useDashboardStore((s) => s.capitalSilo);

  if (!silo || silo.total_capital == null) {
    return (
      <div className="panel">
        <div className="panel-header">Capital</div>
        <p className="text-sm text-gray-400">No capital data</p>
      </div>
    );
  }

  const dailyPnl = silo.daily_pnl ?? 0;
  const cumPnl = silo.cumulative_pnl ?? 0;
  const pnlColor = dailyPnl >= 0 ? "text-green-500" : "text-red-500";

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="flex items-center gap-1.5">
          <Wallet className="h-3.5 w-3.5" /> Capital Silo
        </span>
        <span className={`text-sm font-semibold ${pnlColor}`}>
          {dailyPnl >= 0 ? "+" : ""}
          {formatCurrency(dailyPnl)}
        </span>
      </div>

      <div className="space-y-2">
        <div className="flex justify-between text-sm">
          <span>Total Capital</span>
          <span className="font-semibold">{formatCurrency(silo.total_capital)}</span>
        </div>
        <div className="flex justify-between text-xs text-gray-500 dark:text-gray-400">
          <span>Cumulative P&L</span>
          <span className={cumPnl >= 0 ? "text-green-500" : "text-red-500"}>
            {formatCurrency(cumPnl)}
          </span>
        </div>
        <div className="flex justify-between text-xs text-gray-500 dark:text-gray-400">
          <span>Status</span>
          <span>{silo.status ?? "—"}</span>
        </div>
      </div>
    </div>
  );
}
