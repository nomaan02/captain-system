import { Calendar } from "lucide-react";

const SCHEDULE = [
  { event: "SOD Reset", frequency: "Daily 19:00 ET", status: "Automated" },
  { event: "Decay Detection", frequency: "Per-session", status: "Automated" },
  { event: "AIM Rebalance", frequency: "Weekly", status: "Automated" },
  { event: "Kelly Update", frequency: "Per-trade", status: "Automated" },
  { event: "Strategy Injection Check", frequency: "Monthly", status: "Admin review" },
  { event: "P1/P2 Rerun (Level 3)", frequency: "On decay trigger", status: "Admin review" },
  { event: "System Health Diagnostic", frequency: "8h", status: "Automated" },
  { event: "Contract Roll", frequency: "Quarterly", status: "Admin confirm" },
];

export function GovernanceSchedule() {
  return (
    <div className="panel">
      <div className="panel-header">
        <span className="flex items-center gap-1.5">
          <Calendar className="h-3.5 w-3.5" /> Governance Schedule
        </span>
      </div>
      <div className="space-y-1">
        {SCHEDULE.map((s) => (
          <div key={s.event} className="flex items-center justify-between rounded px-2 py-1.5 text-xs">
            <span className="font-medium text-gray-600 dark:text-gray-300">{s.event}</span>
            <div className="flex items-center gap-3 text-gray-400">
              <span>{s.frequency}</span>
              <span className={s.status === "Automated" ? "text-green-500" : "text-yellow-500"}>
                {s.status}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
