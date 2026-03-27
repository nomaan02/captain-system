import { useEffect, useState } from "react";
import { api } from "@/api/client";
import { StatusDot } from "@/components/StatusDot";
import { Container } from "lucide-react";

const CONTAINERS = ["questdb", "redis", "captain-offline", "captain-online", "captain-command", "nginx"];

export function DeploymentStatus() {
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    api.status().then(setHealth).catch(() => {});
  }, []);

  const processes = (health as any)?.processes ?? {};

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="flex items-center gap-1.5">
          <Container className="h-3.5 w-3.5" /> Deployment Status
        </span>
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {CONTAINERS.map((name) => {
          const role = name.replace("captain-", "").toUpperCase();
          const st = processes[role] ?? (name === "questdb" || name === "redis" || name === "nginx" ? "ok" : "unknown");
          return (
            <div key={name} className="flex items-center gap-2 rounded border border-gray-200 px-2 py-1.5 text-xs dark:border-gray-700">
              <StatusDot
                color={st === "ok" ? "bg-green-500" : st === "error" ? "bg-red-500" : "bg-yellow-500"}
              />
              <span>{name}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
