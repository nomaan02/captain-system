import { useSystemOverviewStore } from "@/stores/systemOverviewStore";
import { Badge } from "@/components/Badge";
import { Lock } from "lucide-react";

export function ActiveConstraints() {
  const params = useSystemOverviewStore((s) => s.overview?.system_params ?? {});
  const entries = Object.entries(params);

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="flex items-center gap-1.5">
          <Lock className="h-3.5 w-3.5" /> Active Constraints
        </span>
      </div>
      {entries.length === 0 ? (
        <p className="text-sm text-gray-400">No constraints loaded</p>
      ) : (
        <div className="max-h-48 space-y-1 overflow-y-auto">
          {entries.map(([key, val]) => (
            <div key={key} className="flex items-center justify-between rounded px-2 py-1 text-xs">
              <span className="text-gray-600 dark:text-gray-300">{key}</span>
              <span className="font-mono text-gray-400">{val}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
