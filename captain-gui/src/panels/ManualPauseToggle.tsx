import { useCallback } from "react";
import { useAuth } from "@/auth/AuthContext";
import { useWebSocket } from "@/ws/useWebSocket";
import { Pause, Play } from "lucide-react";

interface Props {
  asset: string;
  paused: boolean;
}

export function ManualPauseToggle({ asset, paused }: Props) {
  const { user } = useAuth();
  const { send } = useWebSocket(user.user_id);
  const canPause = user.role === "ADMIN" || user.role === "RISK";

  const toggle = useCallback(() => {
    send({
      type: "command",
      command: paused ? "MANUAL_RESUME" : "MANUAL_PAUSE",
      asset,
      user_id: user.user_id,
    });
  }, [send, asset, paused, user.user_id]);

  if (!canPause) return null;

  return (
    <button
      onClick={toggle}
      className={`flex items-center gap-1 rounded px-2 py-1 text-xs font-medium transition-colors ${
        paused
          ? "bg-green-500/10 text-green-500 hover:bg-green-500/20"
          : "bg-red-500/10 text-red-500 hover:bg-red-500/20"
      }`}
    >
      {paused ? (
        <><Play className="h-3 w-3" /> Resume</>
      ) : (
        <><Pause className="h-3 w-3" /> Pause</>
      )}
    </button>
  );
}
