import { useState } from "react";
import { useNotificationStore } from "@/stores/notificationStore";
import { Panel } from "@/components/ui/panel";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { NotificationPriority } from "@/utils/constants";

const FILTERS: (NotificationPriority | "ALL")[] = [
  "ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW",
];

const categoryColor: Record<string, string> = {
  trade: "#4ade80",
  signal: "#60a5fa",
  market: "#52525b",
  warn: "#fbbf24",
  system: "#52525b",
};

function guessCategory(msg: string): string {
  const lower = msg.toLowerCase();
  if (lower.includes("trade") || lower.includes("taken") || lower.includes("skipped")) return "trade";
  if (lower.includes("signal")) return "signal";
  if (lower.includes("warn") || lower.includes("decay") || lower.includes("alert")) return "warn";
  if (lower.includes("market") || lower.includes("vix") || lower.includes("regime")) return "market";
  return "system";
}

export function NotificationsCell() {
  const notifications = useNotificationStore((s) => s.notifications);
  const markAllRead = useNotificationStore((s) => s.markAllRead);
  const unread = useNotificationStore((s) => s.unreadCount);
  const [filter, setFilter] = useState<NotificationPriority | "ALL">("ALL");

  const filtered =
    filter === "ALL"
      ? notifications
      : notifications.filter((n) => n.priority === filter);

  return (
    <Panel
      title="NOTIFICATIONS"
      accent="gray"
      collapsible
      storageKey="notifications"
      headerRight={
        <div className="flex items-center gap-2">
          {/* Filter tabs */}
          <div className="flex gap-0.5">
            {FILTERS.map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className="rounded-sm px-1.5 py-px text-[11px] transition-colors"
                style={{
                  backgroundColor: filter === f ? "#18181b" : "transparent",
                  color: filter === f ? "#a1a1aa" : "#52525b",
                }}
              >
                {f}
              </button>
            ))}
          </div>
          {unread > 0 && (
            <button
              onClick={markAllRead}
              className="text-[11px] text-dim transition-colors hover:text-muted-foreground"
            >
              Mark read
            </button>
          )}
        </div>
      }
    >
      <ScrollArea className="max-h-[160px]">
        {filtered.length === 0 ? (
          <div className="py-3 text-center text-[11px] text-dim">No notifications</div>
        ) : (
          filtered.slice(0, 100).map((n, i) => {
            const cat = guessCategory(n.message);
            const time = n.timestamp
              ? new Date(n.timestamp).toLocaleTimeString("en-US", {
                  timeZone: "America/New_York",
                  hour: "2-digit",
                  minute: "2-digit",
                  second: "2-digit",
                  hour12: false,
                })
              : "—";

            return (
              <div
                key={n.notif_id}
                className="grid"
                style={{
                  gridTemplateColumns: "70px minmax(0, 1fr) 50px",
                  fontSize: 11,
                  padding: "3px 0",
                  borderTop: i > 0 ? "1px solid #111113" : undefined,
                }}
              >
                <span style={{ color: "#3f3f46" }}>{time}</span>
                <span style={{ color: "#a1a1aa", fontSize: 12 }}>{n.message}</span>
                <span
                  className="text-right"
                  style={{ color: categoryColor[cat] ?? "#52525b" }}
                >
                  {cat}
                </span>
              </div>
            );
          })
        )}
      </ScrollArea>
    </Panel>
  );
}
