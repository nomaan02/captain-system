import { useEffect, useState } from "react";
import { api } from "@/api/client";
import { StatusDot } from "@/components/StatusDot";
import { Scale } from "lucide-react";

export function ReconciliationStatus() {
  const [status, setStatus] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    api.status().then(setStatus).catch(() => {});
  }, []);

  const processes = (status as any)?.processes ?? {};

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="flex items-center gap-1.5">
          <Scale className="h-3.5 w-3.5" /> Reconciliation
        </span>
      </div>
      <div className="space-y-2">
        {Object.entries(processes).map(([role, st]) => (
          <div key={role} className="flex items-center justify-between text-sm">
            <span>{role}</span>
            <StatusDot
              color={st === "ok" ? "bg-green-500" : st === "error" ? "bg-red-500" : "bg-yellow-500"}
              label={String(st)}
            />
          </div>
        ))}
        {Object.keys(processes).length === 0 && (
          <p className="text-sm text-gray-400">No process status available</p>
        )}
      </div>
    </div>
  );
}
