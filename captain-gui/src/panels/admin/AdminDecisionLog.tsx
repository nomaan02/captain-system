import { ClipboardCheck } from "lucide-react";

export function AdminDecisionLog() {
  return (
    <div className="panel">
      <div className="panel-header">
        <span className="flex items-center gap-1.5">
          <ClipboardCheck className="h-3.5 w-3.5" /> Admin Decision Log
        </span>
      </div>
      <p className="py-4 text-sm text-gray-400">
        Admin decisions (strategy adoptions, AIM toggles, TSM switches) are logged in P3-D17 session event log.
        View in History → System Events tab.
      </p>
    </div>
  );
}
