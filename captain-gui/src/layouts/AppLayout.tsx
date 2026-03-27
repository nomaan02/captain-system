import { Outlet } from "react-router-dom";
import { useDashboardStore } from "@/stores/dashboardStore";
import { TopBar } from "@/components/top-bar";

export function AppLayout() {
  const connected = useDashboardStore((s) => s.connected);

  return (
    <div className="flex h-screen flex-col bg-background">
      <TopBar />

      {/* Disconnected banner */}
      {!connected && (
        <div
          className="text-center text-[11px] font-semibold"
          style={{
            backgroundColor: "rgba(248, 113, 113, 0.15)",
            color: "#f87171",
            padding: "3px 12px",
          }}
        >
          WebSocket disconnected — REST polling fallback (10s)
        </div>
      )}

      {/* Content */}
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  );
}
