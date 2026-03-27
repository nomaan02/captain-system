import { useAuth } from "@/auth/AuthContext";
import { useDashboardStore } from "@/stores/dashboardStore";
import { useDashboardPolling } from "@/hooks/useDashboard";
import { ActiveSignalCell } from "@/cells/active-signal";
import { LiveMarketCell } from "@/cells/live-market";
import { RiskLimitsCell } from "@/cells/risk-limits";
import { RegimeCell } from "@/cells/regime";
import { CircuitBreakerCell } from "@/cells/circuit-breaker";
import { AimRegistryCell } from "@/cells/aim-registry";
import { TodaysTradesCell } from "@/cells/todays-trades";
import { DayStatsCell } from "@/cells/day-stats";
import { NotificationsCell } from "@/cells/notifications";

/** Grid cell wrapper — provides the bg + padding for each cell */
function Cell({
  span = 1,
  children,
}: {
  span?: number;
  children: React.ReactNode;
}) {
  return (
    <div
      style={{
        gridColumn: `span ${span}`,
        backgroundColor: "#0a0a0c",
        padding: "8px 10px",
      }}
    >
      {children}
    </div>
  );
}

export function DashboardPage() {
  const { user } = useAuth();
  const connected = useDashboardStore((s) => s.connected);
  useDashboardPolling(user.user_id, connected);

  return (
    <div
      className="min-h-full"
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
        gap: 1,
        backgroundColor: "#18181b",
      }}
    >
      {/* Row 1 */}
      <Cell span={2}>
        <ActiveSignalCell />
      </Cell>
      <Cell>
        <LiveMarketCell />
      </Cell>

      {/* Row 2 */}
      <Cell>
        <RiskLimitsCell />
      </Cell>
      <Cell>
        <RegimeCell />
      </Cell>
      <Cell>
        <CircuitBreakerCell />
      </Cell>

      {/* Row 3 */}
      <Cell span={3}>
        <AimRegistryCell />
      </Cell>

      {/* Row 4 */}
      <Cell span={2}>
        <TodaysTradesCell />
      </Cell>
      <Cell>
        <DayStatsCell />
      </Cell>

      {/* Row 5 */}
      <Cell span={3}>
        <NotificationsCell />
      </Cell>
    </div>
  );
}
