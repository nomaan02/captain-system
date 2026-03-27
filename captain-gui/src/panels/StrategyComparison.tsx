import { useCallback } from "react";
import { useAuth } from "@/auth/AuthContext";
import { useWebSocket } from "@/ws/useWebSocket";
import { Badge } from "@/components/Badge";
import { ArrowRight, Check, X, GitBranch } from "lucide-react";

interface StrategyParam {
  name: string;
  current: string | number;
  proposed: string | number;
}

interface Props {
  asset: string;
  candidateId: string;
  params: StrategyParam[];
  recommendation: string;
}

export function StrategyComparison({ asset, candidateId, params, recommendation }: Props) {
  const { user } = useAuth();
  const { send } = useWebSocket(user.user_id);

  const handleDecision = useCallback(
    (cmd: "ADOPT_STRATEGY" | "REJECT_STRATEGY" | "PARALLEL_TRACK") => {
      send({
        type: "command",
        command: cmd,
        asset,
        candidate_id: candidateId,
        user_id: user.user_id,
      });
    },
    [send, asset, candidateId, user.user_id],
  );

  return (
    <div className="panel">
      <div className="panel-header">
        <span>Strategy Injection — {asset}</span>
        <Badge
          label={recommendation}
          className={
            recommendation === "ADOPT"
              ? "bg-green-500/20 text-green-600"
              : recommendation === "REJECT"
                ? "bg-red-500/20 text-red-600"
                : "bg-yellow-500/20 text-yellow-700"
          }
        />
      </div>

      {/* Comparison table */}
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 text-xs text-gray-500 dark:border-gray-700 dark:text-gray-400">
            <th className="py-1.5 text-left font-medium">Parameter</th>
            <th className="py-1.5 text-right font-medium">Current</th>
            <th className="py-1.5 text-center"><ArrowRight className="mx-auto h-3 w-3" /></th>
            <th className="py-1.5 text-right font-medium">Proposed</th>
            <th className="py-1.5 text-right font-medium">Delta</th>
          </tr>
        </thead>
        <tbody>
          {params.map((p) => {
            const curr = Number(p.current);
            const prop = Number(p.proposed);
            const delta = isNaN(curr) || isNaN(prop) ? "—" : (prop - curr).toFixed(4);
            const deltaColor =
              delta === "—" ? "" : Number(delta) > 0 ? "text-green-500" : Number(delta) < 0 ? "text-red-500" : "";
            return (
              <tr key={p.name} className="border-b border-gray-100 dark:border-gray-800">
                <td className="py-1.5 text-gray-600 dark:text-gray-300">{p.name}</td>
                <td className="py-1.5 text-right font-mono text-xs">{p.current}</td>
                <td />
                <td className="py-1.5 text-right font-mono text-xs">{p.proposed}</td>
                <td className={`py-1.5 text-right font-mono text-xs ${deltaColor}`}>{delta}</td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {/* Action buttons */}
      <div className="mt-3 flex gap-2">
        <button
          onClick={() => handleDecision("ADOPT_STRATEGY")}
          className="flex items-center gap-1 rounded bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700"
        >
          <Check className="h-3 w-3" /> Adopt
        </button>
        <button
          onClick={() => handleDecision("PARALLEL_TRACK")}
          className="flex items-center gap-1 rounded bg-yellow-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-yellow-700"
        >
          <GitBranch className="h-3 w-3" /> Parallel
        </button>
        <button
          onClick={() => handleDecision("REJECT_STRATEGY")}
          className="flex items-center gap-1 rounded bg-gray-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-gray-700"
        >
          <X className="h-3 w-3" /> Reject
        </button>
      </div>
    </div>
  );
}
