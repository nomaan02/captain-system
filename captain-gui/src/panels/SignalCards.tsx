import { useDashboardStore } from "@/stores/dashboardStore";
import { Badge } from "@/components/Badge";
import { formatTimestamp, formatNumber, formatCurrency } from "@/utils/formatters";
import { ArrowUp, ArrowDown, Clock } from "lucide-react";

export function SignalCards() {
  const signals = useDashboardStore((s) => s.pendingSignals);

  if (signals.length === 0) {
    return (
      <div className="panel">
        <div className="panel-header">Pending Signals</div>
        <div className="flex items-center gap-2 py-8 text-sm text-gray-400">
          <Clock className="h-4 w-4" />
          No pending signals — waiting for next session
        </div>
      </div>
    );
  }

  return (
    <div className="panel">
      <div className="panel-header">
        <span>Pending Signals</span>
        <Badge label={`${signals.length}`} className="bg-captain-blue text-white" />
      </div>
      <div className="max-h-80 space-y-3 overflow-y-auto">
        {signals.map((sig) => (
          <SignalCard key={sig.signal_id} signal={sig} />
        ))}
      </div>
    </div>
  );
}

function SignalCard({ signal }: { signal: ReturnType<typeof useDashboardStore.getState>["pendingSignals"][0] }) {
  const isLong = signal.direction === "LONG";

  return (
    <div className="rounded-lg border border-gray-200 p-3 dark:border-gray-700">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className={`flex items-center gap-1 text-sm font-semibold ${isLong ? "text-green-500" : "text-red-500"}`}>
            {isLong ? <ArrowUp className="h-4 w-4" /> : <ArrowDown className="h-4 w-4" />}
            {signal.direction ?? "—"}
          </div>
          <span className="text-sm font-medium">{signal.asset}</span>
        </div>
        <span className="text-xs text-gray-400">{formatTimestamp(signal.timestamp)}</span>
      </div>

      <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
        <div className="flex justify-between text-gray-500 dark:text-gray-400">
          <span>Quality</span>
          <span className="font-mono">{formatNumber(signal.quality_score)}</span>
        </div>
        <div className="flex justify-between text-gray-500 dark:text-gray-400">
          <span>Confidence</span>
          <span className="font-mono">{signal.confidence_tier ?? "—"}</span>
        </div>
      </div>

      <div className="mt-2 text-[10px] font-mono text-gray-400">
        {signal.signal_id}
      </div>
    </div>
  );
}
