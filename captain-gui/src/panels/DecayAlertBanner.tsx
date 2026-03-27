import { useDashboardStore } from "@/stores/dashboardStore";
import { AlertTriangle } from "lucide-react";
import { formatPct, formatTimestamp } from "@/utils/formatters";

export function DecayAlertBanner() {
  const decayAlerts = useDashboardStore((s) => s.decayAlerts);

  if (decayAlerts.length === 0) return null;

  return (
    <div className="space-y-2">
      {decayAlerts.map((alert, i) => {
        const isLevel3 = alert.level >= 3;
        const bgClass = isLevel3
          ? "bg-red-500/15 text-red-600 dark:text-red-400"
          : "bg-yellow-500/15 text-yellow-700 dark:text-yellow-400";

        return (
          <div key={`${alert.asset}-${i}`} className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm ${bgClass}`}>
            <AlertTriangle className="h-4 w-4 flex-shrink-0" />
            <span>
              <strong>{alert.asset}</strong> — Level {alert.level} decay detected
              (cp_prob: {formatPct(alert.cp_prob * 100)})
            </span>
            <span className="ml-auto text-xs opacity-70">
              {formatTimestamp(alert.timestamp)}
            </span>
          </div>
        );
      })}
    </div>
  );
}
