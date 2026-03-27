import { useEffect, useState } from "react";
import { api } from "@/api/client";
import { ShieldCheck, ShieldAlert } from "lucide-react";

export function CircuitBreakerBanner() {
  const [cbStatus, setCbStatus] = useState<string>("ACTIVE");

  useEffect(() => {
    api.health().then((h) => setCbStatus(h.circuit_breaker)).catch(() => {});
    const interval = setInterval(() => {
      api.health().then((h) => setCbStatus(h.circuit_breaker)).catch(() => {});
    }, 30_000);
    return () => clearInterval(interval);
  }, []);

  if (cbStatus === "ACTIVE") {
    return (
      <div className="flex items-center gap-2 rounded-lg bg-green-500/10 px-4 py-2 text-sm text-green-600 dark:text-green-400">
        <ShieldCheck className="h-4 w-4" />
        Circuit Breaker: ACTIVE
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 rounded-lg bg-red-500/15 px-4 py-2 text-sm font-medium text-red-600 dark:text-red-400">
      <ShieldAlert className="h-4 w-4" />
      Circuit Breaker: HALTED — Trading is paused
    </div>
  );
}
