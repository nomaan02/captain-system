import { useDashboardStore } from "@/stores/dashboardStore";
import { ProgressBar } from "@/components/ProgressBar";
import { formatCurrency } from "@/utils/formatters";
import { TrendingUp } from "lucide-react";

export function ScalingDisplay() {
  const scaling = useDashboardStore((s) => s.scalingDisplay);

  if (scaling.length === 0) return null;

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="flex items-center gap-1.5">
          <TrendingUp className="h-3.5 w-3.5" /> Scaling Tiers
        </span>
      </div>
      <div className="space-y-3">
        {scaling.map((s) => (
          <div key={s.account_id} className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="font-medium">{s.account_id}</span>
              <span className="text-xs text-gray-400">{s.current_tier}</span>
            </div>

            <div className="grid grid-cols-3 gap-2 text-xs text-gray-500 dark:text-gray-400">
              <div>
                <span className="block text-[10px] uppercase">Max Micros</span>
                {s.current_max_micros}
              </div>
              <div>
                <span className="block text-[10px] uppercase">Open</span>
                {s.open_positions_micros}
              </div>
              <div>
                <span className="block text-[10px] uppercase">Available</span>
                <span className="font-semibold text-captain-green">{s.available_slots}</span>
              </div>
            </div>

            {s.next_tier_label && (
              <div className="text-xs text-gray-500 dark:text-gray-400">
                {formatCurrency(s.profit_to_next_tier)} to <strong>{s.next_tier_label}</strong>
              </div>
            )}

            <ProgressBar
              value={s.open_positions_micros}
              max={s.current_max_micros || 1}
              color="bg-captain-purple"
              showLabel
              label="Slot usage"
            />
          </div>
        ))}
      </div>
    </div>
  );
}
