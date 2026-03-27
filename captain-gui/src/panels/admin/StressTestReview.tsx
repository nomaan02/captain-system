import { FlaskConical } from "lucide-react";

export function StressTestReview() {
  return (
    <div className="panel">
      <div className="panel-header">
        <span className="flex items-center gap-1.5">
          <FlaskConical className="h-3.5 w-3.5" /> Stress Test Review
        </span>
      </div>
      <p className="py-4 text-sm text-gray-400">
        Stress test results will be available after Phase 7 validation. Generate via RPT-08 (Regime Calibration).
      </p>
    </div>
  );
}
