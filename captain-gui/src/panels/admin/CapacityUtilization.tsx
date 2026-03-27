import { Cpu } from "lucide-react";

interface Props {
  capacity: Record<string, unknown>;
}

export function CapacityUtilization({ capacity }: Props) {
  const entries = Object.entries(capacity);

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="flex items-center gap-1.5">
          <Cpu className="h-3.5 w-3.5" /> Capacity Utilization
        </span>
      </div>
      {entries.length === 0 ? (
        <p className="text-sm text-gray-400">No capacity data</p>
      ) : (
        <dl className="space-y-1 text-sm">
          {entries.map(([key, val]) => (
            <div key={key} className="flex justify-between">
              <dt className="text-gray-500 dark:text-gray-400">{key}</dt>
              <dd className="font-mono text-xs">{String(val)}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}
