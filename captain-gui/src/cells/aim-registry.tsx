import { useCallback, useMemo } from "react";
import { useDashboardStore } from "@/stores/dashboardStore";
import { useAuth } from "@/auth/AuthContext";
import { useWebSocket } from "@/ws/useWebSocket";
import { Panel } from "@/components/ui/panel";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { AimState } from "@/api/types";

const aimStatusToVariant = (s: string) => {
  switch (s) {
    case "ACTIVE": return "go" as const;
    case "SUPPRESSED": return "danger" as const;
    case "WARM_UP":
    case "BOOTSTRAPPED": return "warning" as const;
    default: return "neutral" as const;
  }
};

const aimBorderColor = (s: string) => {
  switch (s) {
    case "ACTIVE": return "#4ade80";
    case "SUPPRESSED": return "#f87171";
    case "WARM_UP":
    case "BOOTSTRAPPED": return "#fbbf24";
    default: return "#3f3f46";
  }
};

/** Priority order for picking the "aggregate" status across assets */
const STATUS_PRIORITY: Record<string, number> = {
  ACTIVE: 0, SUPPRESSED: 1, ELIGIBLE: 2, BOOTSTRAPPED: 3,
  WARM_UP: 4, COLLECTING: 5, INSTALLED: 6,
};

interface GroupedAim {
  aim_id: number;
  aim_name: string;
  status: string;        // highest-priority status across assets
  assets_active: number; // how many assets have this AIM active
  assets_total: number;  // total assets
}

function AimCard({ aim }: { aim: GroupedAim }) {
  const { user } = useAuth();
  const { send } = useWebSocket(user.user_id);
  const isAdmin = user.role === "ADMIN";
  const isOff = aim.status === "INSTALLED" || aim.status === "COLLECTING";

  const toggleActive = useCallback(() => {
    const cmd = aim.status === "ACTIVE" ? "DEACTIVATE_AIM" : "ACTIVATE_AIM";
    send({ type: "command", command: cmd, aim_id: aim.aim_id, user_id: user.user_id });
  }, [aim, send, user.user_id]);

  return (
    <div
      className="rounded-[3px] p-1.5"
      style={{
        backgroundColor: "#111113",
        border: "1px solid #1a1a1f",
        borderLeft: `2px solid ${aimBorderColor(aim.status)}`,
      }}
    >
      {/* Row 1: ID + status */}
      <div className="flex items-center justify-between">
        <span
          className="text-xs font-semibold"
          style={{ color: isOff ? "#71717a" : "#e4e4e7" }}
        >
          {aim.aim_id}
        </span>
        <Badge variant={aimStatusToVariant(aim.status)} size="sm">
          {aim.status}
        </Badge>
      </div>

      {/* Row 2: Name */}
      <div
        className="mt-0.5 truncate text-[11px]"
        style={{ color: isOff ? "#3f3f46" : "#a1a1aa" }}
      >
        {aim.aim_name}
      </div>

      {/* Row 3: Asset coverage */}
      <div className="mt-1 text-[11px]" style={{ color: "#52525b" }}>
        {aim.assets_active}/{aim.assets_total} assets
      </div>

      {/* Admin toggle */}
      {isAdmin && (
        <button
          onClick={toggleActive}
          className="mt-1 w-full rounded-[2px] py-px text-[10px] font-semibold transition-colors"
          style={{
            backgroundColor:
              aim.status === "ACTIVE"
                ? "rgba(248, 113, 113, 0.1)"
                : "rgba(74, 222, 128, 0.1)",
            color: aim.status === "ACTIVE" ? "#f87171" : "#4ade80",
          }}
        >
          {aim.status === "ACTIVE" ? "DEACTIVATE" : "ACTIVATE"}
        </button>
      )}
    </div>
  );
}

export function AimRegistryCell() {
  const aimStates = useDashboardStore((s) => s.aimStates);

  // Group per-asset rows into one card per AIM ID
  const grouped = useMemo(() => {
    const map = new Map<string, { aim_name: string; statuses: string[] }>();
    for (const a of aimStates) {
      const key = String(a.aim_id);
      const entry = map.get(key) ?? { aim_name: a.aim_name, statuses: [] };
      entry.statuses.push(a.status);
      map.set(key, entry);
    }
    const result: GroupedAim[] = [];
    for (const [aim_id, { aim_name, statuses }] of map) {
      const sorted = [...statuses].sort(
        (a, b) => (STATUS_PRIORITY[a] ?? 99) - (STATUS_PRIORITY[b] ?? 99)
      );
      result.push({
        aim_id: Number(aim_id),
        aim_name,
        status: sorted[0] ?? "INSTALLED",
        assets_active: statuses.filter((s) => s === "ACTIVE").length,
        assets_total: statuses.length,
      });
    }
    return result.sort((a, b) => a.aim_id - b.aim_id);
  }, [aimStates]);

  const activeCount = grouped.filter((a) => a.status === "ACTIVE").length;

  return (
    <Panel
      title="AIM REGISTRY"
      accent="gray"
      collapsible
      storageKey="aim-registry"
      headerRight={
        <Badge variant="go" size="sm">
          {activeCount}/{grouped.length} active
        </Badge>
      }
    >
      {grouped.length === 0 ? (
        <div className="py-2 text-[11px] text-dim">No AIMs loaded</div>
      ) : (
        <ScrollArea className="max-h-[220px]">
          <div
            className="grid gap-px"
            style={{
              gridTemplateColumns: "repeat(8, minmax(0, 1fr))",
            }}
          >
            {grouped.map((aim) => (
              <AimCard key={aim.aim_id} aim={aim} />
            ))}
          </div>
        </ScrollArea>
      )}
    </Panel>
  );
}
