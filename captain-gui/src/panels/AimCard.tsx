import { useCallback } from "react";
import type { AimState } from "@/api/types";
import { aimStatusColor } from "@/utils/colors";
import { formatNumber, formatPct } from "@/utils/formatters";
import { ProgressBar } from "@/components/ProgressBar";
import { useAuth } from "@/auth/AuthContext";
import { useWebSocket } from "@/ws/useWebSocket";
import { ChevronDown, ChevronRight, Power, PowerOff } from "lucide-react";

interface Props {
  aim: AimState;
  expanded: boolean;
  onToggle: () => void;
}

export function AimCard({ aim, expanded, onToggle }: Props) {
  const { user } = useAuth();
  const { send } = useWebSocket(user.user_id);
  const isAdmin = user.role === "ADMIN";

  const toggleActive = useCallback(() => {
    const cmd = aim.status === "ACTIVE" ? "DEACTIVATE_AIM" : "ACTIVATE_AIM";
    send({
      type: "command",
      command: cmd,
      aim_id: aim.aim_id,
      user_id: user.user_id,
    });
  }, [aim, send, user.user_id]);

  const statusColor = aimStatusColor[aim.status] || "text-gray-400";

  return (
    <div className="rounded border border-gray-200 dark:border-gray-700">
      {/* Collapsed header */}
      <button
        onClick={onToggle}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-800/50"
      >
        {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        <span className="flex-1 font-medium">{aim.aim_name ?? aim.aim_id}</span>
        <span className={`text-xs ${statusColor}`}>{aim.status}</span>
      </button>

      {/* Collapsed stats row */}
      {!expanded && (
        <div className="flex gap-4 border-t border-gray-100 px-3 py-1.5 text-xs text-gray-500 dark:border-gray-800 dark:text-gray-400">
          <span>W: {formatNumber(aim.meta_weight, 3)}</span>
          <span>M: {formatNumber(aim.modifier, 3)}</span>
        </div>
      )}

      {/* Expanded detail */}
      {expanded && (
        <div className="space-y-2 border-t border-gray-100 px-3 py-2 dark:border-gray-800">
          <div className="grid grid-cols-2 gap-2 text-xs text-gray-500 dark:text-gray-400">
            <div>
              <span className="block text-[10px] uppercase">Meta Weight</span>
              {formatNumber(aim.meta_weight, 4)}
            </div>
            <div>
              <span className="block text-[10px] uppercase">Modifier</span>
              {formatNumber(aim.modifier, 4)}
            </div>
          </div>

          {aim.warmup_pct != null && (
            <ProgressBar
              value={aim.warmup_pct}
              color={aim.warmup_pct >= 100 ? "bg-captain-green" : "bg-captain-blue"}
              showLabel
              label="Warmup"
            />
          )}

          {isAdmin && (
            <button
              onClick={toggleActive}
              className={`mt-1 flex items-center gap-1 rounded px-2 py-1 text-xs font-medium ${
                aim.status === "ACTIVE"
                  ? "bg-red-500/10 text-red-500 hover:bg-red-500/20"
                  : "bg-green-500/10 text-green-500 hover:bg-green-500/20"
              }`}
            >
              {aim.status === "ACTIVE" ? (
                <><PowerOff className="h-3 w-3" /> Deactivate</>
              ) : (
                <><Power className="h-3 w-3" /> Activate</>
              )}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
