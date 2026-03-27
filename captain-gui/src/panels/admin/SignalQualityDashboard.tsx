import type { SignalQuality } from "@/api/types";
import { ProgressBar } from "@/components/ProgressBar";
import { formatPct } from "@/utils/formatters";
import { BarChart3 } from "lucide-react";

interface Props {
  quality: SignalQuality;
}

export function SignalQualityDashboard({ quality }: Props) {
  const passRate = quality.pass_rate * 100;

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="flex items-center gap-1.5">
          <BarChart3 className="h-3.5 w-3.5" /> Signal Quality
        </span>
      </div>
      <div className="space-y-3">
        <div className="grid grid-cols-3 gap-3 text-center">
          <div>
            <div className="text-2xl font-bold">{quality.total_evaluated}</div>
            <div className="text-[10px] uppercase text-gray-500 dark:text-gray-400">Evaluated</div>
          </div>
          <div>
            <div className="text-2xl font-bold text-captain-green">{quality.passed}</div>
            <div className="text-[10px] uppercase text-gray-500 dark:text-gray-400">Passed</div>
          </div>
          <div>
            <div className="text-2xl font-bold">{formatPct(passRate)}</div>
            <div className="text-[10px] uppercase text-gray-500 dark:text-gray-400">Pass Rate</div>
          </div>
        </div>
        <ProgressBar
          value={passRate}
          color={passRate >= 70 ? "bg-captain-green" : passRate >= 40 ? "bg-yellow-500" : "bg-red-500"}
          showLabel
          label="7-day pass rate"
        />
      </div>
    </div>
  );
}
