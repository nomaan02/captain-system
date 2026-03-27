import { Brain } from "lucide-react";

export function ModelValidation() {
  return (
    <div className="panel">
      <div className="panel-header">
        <span className="flex items-center gap-1.5">
          <Brain className="h-3.5 w-3.5" /> Model Validation
        </span>
      </div>
      <p className="py-4 text-sm text-gray-400">
        AIM model validation metrics are available via RPT-04 (AIM Effectiveness Report).
        Decay detection monitors model drift continuously.
      </p>
    </div>
  );
}
