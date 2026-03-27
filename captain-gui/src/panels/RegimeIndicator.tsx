import { Badge } from "@/components/Badge";
import { useDashboardStore } from "@/stores/dashboardStore";
import { Activity } from "lucide-react";

export function RegimeIndicator() {
  // Regime info comes with signals — show latest known regime from pending signals
  const signals = useDashboardStore((s) => s.pendingSignals);
  // For now, show a static indicator; real regime comes via WS signal payloads
  return (
    <div className="panel">
      <div className="panel-header">
        <span className="flex items-center gap-1.5">
          <Activity className="h-3.5 w-3.5" /> Regime
        </span>
      </div>
      <div className="flex items-center gap-3 py-2">
        <Badge label="REGIME_NEUTRAL" className="bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-300" />
        <span className="text-xs text-gray-400">
          Regime-conditioned allocation active. Neutral = no vol-based adjustment.
        </span>
      </div>
    </div>
  );
}
