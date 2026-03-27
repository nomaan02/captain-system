import { Zap } from "lucide-react";

export function CapacityRecommendations() {
  return (
    <div className="panel">
      <div className="panel-header">
        <span className="flex items-center gap-1.5">
          <Zap className="h-3.5 w-3.5" /> Capacity Recommendations
        </span>
      </div>
      <p className="py-4 text-sm text-gray-400">
        Capacity recommendations are computed by Online B9 (Capacity Evaluator).
        Data appears here when capacity evaluations run at session boundaries.
      </p>
    </div>
  );
}
