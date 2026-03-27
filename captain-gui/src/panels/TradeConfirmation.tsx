import { useCallback } from "react";
import { useDashboardStore } from "@/stores/dashboardStore";
import { useWebSocket } from "@/ws/useWebSocket";
import { useAuth } from "@/auth/AuthContext";
import { Check, X } from "lucide-react";

export function TradeConfirmation() {
  const signals = useDashboardStore((s) => s.pendingSignals);
  const removeSignal = useDashboardStore((s) => s.removeSignal);
  const lastAck = useDashboardStore((s) => s.lastAck);
  const { user } = useAuth();
  const { send } = useWebSocket(user.user_id);

  const handleAction = useCallback(
    (signalId: string, action: "TAKEN" | "SKIPPED", signal: typeof signals[0]) => {
      send({
        type: "command",
        command: "TAKEN_SKIPPED",
        action,
        signal_id: signalId,
        asset: signal.asset,
        direction: signal.direction,
        user_id: user.user_id,
      });
      removeSignal(signalId);
    },
    [send, removeSignal, user.user_id],
  );

  if (signals.length === 0) return null;

  return (
    <div className="panel">
      <div className="panel-header">Trade Confirmation</div>
      <div className="space-y-2">
        {signals.map((sig) => (
          <div
            key={sig.signal_id}
            className="flex items-center justify-between rounded border border-gray-200 px-3 py-2 dark:border-gray-700"
          >
            <div className="text-sm">
              <span className="font-medium">{sig.asset}</span>{" "}
              <span className={sig.direction === "LONG" ? "text-green-500" : "text-red-500"}>
                {sig.direction}
              </span>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => handleAction(sig.signal_id, "TAKEN", sig)}
                className="flex items-center gap-1 rounded bg-green-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-green-700"
              >
                <Check className="h-3 w-3" /> TAKEN
              </button>
              <button
                onClick={() => handleAction(sig.signal_id, "SKIPPED", sig)}
                className="flex items-center gap-1 rounded bg-gray-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-gray-700"
              >
                <X className="h-3 w-3" /> SKIP
              </button>
            </div>
          </div>
        ))}
      </div>

      {lastAck?.command === "TAKEN_SKIPPED" && (
        <div className="mt-2 rounded bg-captain-blue/10 px-3 py-1.5 text-xs text-captain-blue">
          {lastAck.action === "TAKEN" ? "Trade taken" : "Signal skipped"} — {lastAck.signal_id}
        </div>
      )}
    </div>
  );
}
