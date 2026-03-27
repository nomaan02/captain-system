import type { ActionItem } from "@/api/types";
import { formatTimestamp } from "@/utils/formatters";
import { Badge } from "@/components/Badge";
import { ClipboardList } from "lucide-react";

interface Props {
  items: ActionItem[];
}

export function ActionQueue({ items }: Props) {
  return (
    <div className="panel">
      <div className="panel-header">
        <span className="flex items-center gap-1.5">
          <ClipboardList className="h-3.5 w-3.5" /> Action Queue
        </span>
        <span className="text-xs font-normal text-gray-400">{items.length} open</span>
      </div>
      {items.length === 0 ? (
        <p className="py-4 text-sm text-gray-400">No open actions</p>
      ) : (
        <div className="max-h-64 space-y-1 overflow-y-auto">
          {items.map((item, i) => {
            const cls =
              item.status === "CRITICAL" ? "bg-red-500/20 text-red-600"
              : item.status === "STALE" ? "bg-yellow-500/20 text-yellow-700"
              : "bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-300";
            return (
              <div key={i} className="flex items-start justify-between rounded px-2 py-1.5 text-xs hover:bg-gray-50 dark:hover:bg-gray-800/50">
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <Badge label={item.status} className={cls} />
                    <span className="font-medium">{item.dimension}</span>
                  </div>
                  {item.details && (
                    <p className="mt-0.5 text-[10px] text-gray-400">{item.details}</p>
                  )}
                </div>
                <span className="flex-shrink-0 text-[10px] text-gray-400">{formatTimestamp(item.timestamp)}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
