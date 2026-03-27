import { useDashboardStore } from "@/stores/dashboardStore";
import { ProgressBar } from "@/components/ProgressBar";
import { captainStatusColor } from "@/utils/colors";
import { Gauge } from "lucide-react";

export function WarmupGauges() {
  const gauges = useDashboardStore((s) => s.warmupGauges);

  if (gauges.length === 0) {
    return (
      <div className="panel">
        <div className="panel-header">
          <span className="flex items-center gap-1.5">
            <Gauge className="h-3.5 w-3.5" /> Warmup
          </span>
        </div>
        <p className="text-sm text-gray-400">No assets warming up</p>
      </div>
    );
  }

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="flex items-center gap-1.5">
          <Gauge className="h-3.5 w-3.5" /> Warmup Progress
        </span>
      </div>
      <div className="space-y-3">
        {gauges.map((g) => {
          const pct = g.warmup_pct ?? 0;
          const color =
            pct >= 100 ? "bg-captain-green" : pct >= 50 ? "bg-captain-blue" : "bg-yellow-500";
          return (
            <div key={g.asset_id}>
              <div className="mb-1 flex items-center justify-between text-sm">
                <span className="font-medium">{g.asset_id}</span>
                <span className={`text-xs ${captainStatusColor[g.status]}`}>
                  {g.status}
                </span>
              </div>
              <ProgressBar value={pct} color={color} showLabel />
            </div>
          );
        })}
      </div>
    </div>
  );
}
