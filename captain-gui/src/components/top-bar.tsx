import { NavLink } from "react-router-dom";
import { useDashboardStore } from "@/stores/dashboardStore";
import { useNotificationStore } from "@/stores/notificationStore";
import { useAuth } from "@/auth/AuthContext";
import { StatusDot } from "@/components/ui/status-dot";
import { formatCurrency } from "@/utils/formatters";

const navItems = [
  { to: "/", label: "Dashboard" },
  { to: "/system", label: "System", adminOnly: true },
  { to: "/history", label: "History" },
  { to: "/reports", label: "Reports" },
  { to: "/settings", label: "Settings" },
];

function Divider() {
  return <div className="mx-1" style={{ width: 1, height: 16, backgroundColor: "#27272a" }} />;
}

function Metric({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <span className="text-[11px] text-dim">{label}</span>
      <span className="text-xs font-semibold" style={color ? { color } : undefined}>
        {value}
      </span>
    </div>
  );
}

export function TopBar() {
  const { user } = useAuth();
  const connected = useDashboardStore((s) => s.connected);
  const silo = useDashboardStore((s) => s.capitalSilo);
  const positions = useDashboardStore((s) => s.openPositions);
  const apiStatus = useDashboardStore((s) => s.apiStatus);
  const timestamp = useDashboardStore((s) => s.timestamp);
  const unread = useNotificationStore((s) => s.unreadCount);

  const dailyPnl = silo?.daily_pnl ?? 0;
  const weekPnl = silo?.cumulative_pnl ?? 0;
  const tradeCount = positions.length;
  const wins = positions.filter((p) => (p.current_pnl ?? 0) > 0).length;
  const winPct = tradeCount > 0 ? ((wins / tradeCount) * 100).toFixed(0) : "—";
  const totalPnl = positions.reduce((s, p) => s + (p.current_pnl ?? 0), 0);
  const totalLoss = positions.filter((p) => (p.current_pnl ?? 0) < 0).reduce((s, p) => s + Math.abs(p.current_pnl ?? 0), 0);
  const pf = totalLoss > 0 ? (totalPnl / totalLoss).toFixed(2) : "—";

  const pnlColor = (v: number) => (v >= 0 ? "#4ade80" : "#f87171");

  const apiOk = apiStatus?.api_authenticated ?? false;
  const tsNow = timestamp
    ? new Date(timestamp).toLocaleTimeString("en-US", {
        timeZone: "America/New_York",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
      })
    : "—";

  return (
    <header
      className="flex items-center gap-2 bg-card"
      style={{ padding: "6px 12px", borderBottom: "1px solid #1a1a1f" }}
    >
      {/* Logo */}
      <div
        className="flex shrink-0 items-center justify-center rounded"
        style={{
          width: 22,
          height: 22,
          backgroundColor: "#16a34a",
          borderRadius: 4,
        }}
      >
        <span className="text-[11px] font-bold text-black">C</span>
      </div>

      {/* App name */}
      <span
        className="text-xs font-semibold text-foreground"
        style={{ letterSpacing: "0.02em" }}
      >
        CAPTAIN
      </span>

      <Divider />

      {/* Nav */}
      <nav className="flex items-center gap-0.5">
        {navItems
          .filter((item) => !item.adminOnly || user.role === "ADMIN")
          .map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                isActive
                  ? "rounded-sm bg-muted px-1.5 py-px text-[11px] text-[#a1a1aa]"
                  : "px-1.5 py-px text-[11px] text-dim transition-colors hover:text-muted-foreground"
              }
            >
              {item.label}
            </NavLink>
          ))}
      </nav>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Metrics strip */}
      <div className="flex items-center gap-3.5">
        <Metric label="BAL" value={formatCurrency(silo?.total_capital)} />
        <Metric label="DAY" value={`${dailyPnl >= 0 ? "+" : ""}${formatCurrency(dailyPnl)}`} color={pnlColor(dailyPnl)} />
        <Metric label="WEEK" value={`${weekPnl >= 0 ? "+" : ""}${formatCurrency(weekPnl)}`} color={pnlColor(weekPnl)} />
        <Metric label="TRADES" value={`${tradeCount}`} />
        <Metric label="WIN%" value={`${winPct}%`} color={Number(winPct) >= 50 ? "#4ade80" : undefined} />
        <Metric label="PF" value={pf} color={Number(pf) > 1 ? "#4ade80" : undefined} />
        {unread > 0 && (
          <div className="flex items-center gap-1">
            <span className="flex h-3.5 min-w-3.5 items-center justify-center rounded-sm bg-red px-1 text-[9px] font-bold text-black">
              {unread > 99 ? "99+" : unread}
            </span>
          </div>
        )}
      </div>

      <Divider />

      {/* Status dots */}
      <div className="flex items-center gap-3">
        <StatusDot status={connected ? "ok" : "danger"} label="WS" />
        <StatusDot status={apiOk ? "ok" : "off"} label="API" />
        <StatusDot status={connected ? "ok" : "off"} label="QDB" />
      </div>

      {/* Timestamp */}
      <span className="ml-1 text-[11px] text-ghost">{tsNow} ET</span>
    </header>
  );
}
