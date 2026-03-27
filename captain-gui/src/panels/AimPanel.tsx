import { useState } from "react";
import { useDashboardStore } from "@/stores/dashboardStore";
import { AimCard } from "./AimCard";
import { Badge } from "@/components/Badge";

export function AimPanel() {
  const aimStates = useDashboardStore((s) => s.aimStates);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const activeCount = aimStates.filter((a) => a.status === "ACTIVE").length;

  return (
    <div className="panel">
      <div className="panel-header">
        <span>AIM Registry</span>
        <Badge
          label={`${activeCount}/${aimStates.length} active`}
          className="bg-captain-green/20 text-captain-green"
        />
      </div>
      {aimStates.length === 0 ? (
        <p className="py-4 text-sm text-gray-400">No AIMs loaded</p>
      ) : (
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {aimStates.map((aim) => (
            <AimCard
              key={aim.aim_id}
              aim={aim}
              expanded={expandedId === aim.aim_id}
              onToggle={() => setExpandedId(expandedId === aim.aim_id ? null : aim.aim_id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
