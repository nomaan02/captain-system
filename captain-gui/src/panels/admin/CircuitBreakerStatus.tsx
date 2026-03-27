import { useEffect, useState } from "react";
import { api } from "@/api/client";
import { Badge } from "@/components/Badge";
import { ShieldAlert, RefreshCw } from "lucide-react";

interface HealthData {
  status: string;
  circuit_breaker: string;
  uptime_seconds: number;
  active_users: number;
  api_connections: { connected: number; total: number };
  last_signal_time: string | null;
  last_heartbeat: string | null;
}

export function CircuitBreakerStatus() {
  const [health, setHealth] = useState<HealthData | null>(null);

  const refresh = () => api.health().then((h) => setHealth(h as any)).catch(() => {});

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 30_000);
    return () => clearInterval(interval);
  }, []);

  if (!health) return null;

  const cbColor = health.circuit_breaker === "ACTIVE"
    ? "bg-green-500/20 text-green-600"
    : "bg-red-500/20 text-red-600";

  const sysColor = health.status === "OK"
    ? "bg-green-500/20 text-green-600"
    : "bg-yellow-500/20 text-yellow-700";

  const uptimeHrs = (health.uptime_seconds / 3600).toFixed(1);

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="flex items-center gap-1.5">
          <ShieldAlert className="h-3.5 w-3.5" /> Circuit Breaker / System Status
        </span>
        <button onClick={refresh} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
          <RefreshCw className="h-3.5 w-3.5" />
        </button>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div>
          <div className="text-[10px] uppercase text-gray-500 dark:text-gray-400">System</div>
          <Badge label={health.status} className={sysColor} />
        </div>
        <div>
          <div className="text-[10px] uppercase text-gray-500 dark:text-gray-400">Circuit Breaker</div>
          <Badge label={health.circuit_breaker} className={cbColor} />
        </div>
        <div>
          <div className="text-[10px] uppercase text-gray-500 dark:text-gray-400">Uptime</div>
          <span className="text-sm font-mono">{uptimeHrs}h</span>
        </div>
        <div>
          <div className="text-[10px] uppercase text-gray-500 dark:text-gray-400">Active Users</div>
          <span className="text-sm font-mono">{health.active_users}</span>
        </div>
        <div>
          <div className="text-[10px] uppercase text-gray-500 dark:text-gray-400">API Connections</div>
          <span className="text-sm font-mono">{health.api_connections.connected}/{health.api_connections.total}</span>
        </div>
        <div>
          <div className="text-[10px] uppercase text-gray-500 dark:text-gray-400">Last Signal</div>
          <span className="text-xs font-mono">{health.last_signal_time ?? "—"}</span>
        </div>
      </div>
    </div>
  );
}
