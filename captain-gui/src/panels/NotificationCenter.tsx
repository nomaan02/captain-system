import { useState } from "react";
import { useNotificationStore } from "@/stores/notificationStore";
import { priorityColor, priorityDot } from "@/utils/colors";
import { formatTimeAgo } from "@/utils/formatters";
import type { NotificationPriority } from "@/utils/constants";
import { Bell, Filter } from "lucide-react";
import { StatusDot } from "@/components/StatusDot";

const FILTERS: (NotificationPriority | "ALL")[] = ["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW"];

export function NotificationCenter() {
  const notifications = useNotificationStore((s) => s.notifications);
  const markAllRead = useNotificationStore((s) => s.markAllRead);
  const [filter, setFilter] = useState<NotificationPriority | "ALL">("ALL");

  const filtered =
    filter === "ALL"
      ? notifications
      : notifications.filter((n) => n.priority === filter);

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="flex items-center gap-1.5">
          <Bell className="h-3.5 w-3.5" /> Notifications
        </span>
        <div className="flex items-center gap-2">
          <div className="flex gap-1">
            {FILTERS.map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`rounded px-2 py-0.5 text-[10px] transition-colors ${
                  filter === f
                    ? "bg-captain-blue text-white"
                    : "text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800"
                }`}
              >
                {f}
              </button>
            ))}
          </div>
          <button
            onClick={markAllRead}
            className="text-[10px] text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
          >
            Mark read
          </button>
        </div>
      </div>

      <div className="max-h-64 space-y-1 overflow-y-auto">
        {filtered.length === 0 ? (
          <p className="py-4 text-center text-sm text-gray-400">No notifications</p>
        ) : (
          filtered.slice(0, 100).map((n) => (
            <div
              key={n.notif_id}
              className="flex items-start gap-2 rounded px-2 py-1.5 text-xs hover:bg-gray-50 dark:hover:bg-gray-800/50"
            >
              <StatusDot color={priorityDot[n.priority]} />
              <span className="flex-1">{n.message}</span>
              <span className="flex-shrink-0 text-[10px] text-gray-400">
                {formatTimeAgo(n.timestamp)}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
