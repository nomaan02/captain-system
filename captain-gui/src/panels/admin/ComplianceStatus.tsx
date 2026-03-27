import { Badge } from "@/components/Badge";
import { ShieldCheck } from "lucide-react";

interface Props {
  gate: { execution_mode: string; requirements: Record<string, unknown> };
}

export function ComplianceStatus({ gate }: Props) {
  const mode = gate.execution_mode;
  const reqs = Object.entries(gate.requirements);
  const modeColor =
    mode === "AUTOMATIC" ? "bg-green-500/20 text-green-600"
    : mode === "SEMI_AUTOMATIC" ? "bg-yellow-500/20 text-yellow-700"
    : "bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-300";

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="flex items-center gap-1.5">
          <ShieldCheck className="h-3.5 w-3.5" /> Compliance Gate
        </span>
        <Badge label={mode} className={modeColor} />
      </div>
      {reqs.length === 0 ? (
        <p className="text-sm text-gray-400">No active requirements</p>
      ) : (
        <dl className="space-y-1 text-xs">
          {reqs.map(([key, val]) => (
            <div key={key} className="flex justify-between text-gray-500 dark:text-gray-400">
              <dt>{key}</dt>
              <dd className="font-mono">{String(val)}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}
