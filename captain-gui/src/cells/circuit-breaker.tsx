import { useEffect, useState } from "react";
import { api } from "@/api/client";
import { useDashboardStore } from "@/stores/dashboardStore";
import { Panel } from "@/components/ui/panel";
import { Badge } from "@/components/ui/badge";
import { StatusDot } from "@/components/ui/status-dot";
import { ProgressBar } from "@/components/ui/progress-bar";
import { ScrollArea } from "@/components/ui/scroll-area";
import { formatPct, formatTimestamp } from "@/utils/formatters";

export function CircuitBreakerCell() {
  const [cbStatus, setCbStatus] = useState("ACTIVE");
  const warmupGauges = useDashboardStore((s) => s.warmupGauges);
  const decayAlerts = useDashboardStore((s) => s.decayAlerts);

  useEffect(() => {
    api.health().then((h) => setCbStatus(h.circuit_breaker)).catch(() => {});
    const interval = setInterval(() => {
      api.health().then((h) => setCbStatus(h.circuit_breaker)).catch(() => {});
    }, 30_000);
    return () => clearInterval(interval);
  }, []);

  const isActive = cbStatus === "ACTIVE";

  return (
    <Panel
      title="CIRCUIT BREAKER"
      accent={isActive ? "green" : "gray"}
      headerRight={
        <Badge variant={isActive ? "go" : "danger"}>
          {isActive ? "ACTIVE" : "HALTED"}
        </Badge>
      }
    >
      <ScrollArea className="max-h-[200px]">
        {/* CB status */}
        <div className="mb-2 flex items-center gap-2">
          <StatusDot status={isActive ? "ok" : "danger"} pulse={!isActive} />
          <span className="text-[11px] text-foreground">
            {isActive ? "System operational" : "Trading paused — circuit breaker tripped"}
          </span>
        </div>

        {/* Decay alerts */}
        {decayAlerts.map((alert, i) => (
          <div
            key={`${alert.asset}-${i}`}
            className="mb-1 rounded-[3px] px-2 py-1 text-[11px]"
            style={{
              backgroundColor:
                alert.level >= 3
                  ? "rgba(248, 113, 113, 0.1)"
                  : "rgba(245, 158, 11, 0.1)",
              color: alert.level >= 3 ? "#f87171" : "#fbbf24",
            }}
          >
            <strong>{alert.asset}</strong> — L{alert.level} decay (cp:{" "}
            {formatPct(alert.cp_prob * 100)})
            <span className="ml-1 text-ghost">{formatTimestamp(alert.timestamp)}</span>
          </div>
        ))}

        {/* Warmup gauges */}
        {warmupGauges.length > 0 && (
          <div className="mt-2">
            <div className="mb-1 text-[11px] text-dim">Warmup</div>
            {warmupGauges.map((g) => (
              <ProgressBar
                key={g.asset_id}
                value={g.warmup_pct ?? 0}
                invertThresholds
                label={g.asset_id}
                showValue
                className="mb-1"
              />
            ))}
          </div>
        )}
      </ScrollArea>
    </Panel>
  );
}
