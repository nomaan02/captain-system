import StatusDot from "../shared/StatusDot";
import { formatTimeAgo } from "../../utils/formatting";

const STALE_THRESHOLD_MS = 15 * 60 * 1000; // 15 minutes

function checkFreshness(timestamp) {
  if (!timestamp) return { status: "error", label: "No data" };
  const age = Date.now() - new Date(timestamp).getTime();
  if (age > STALE_THRESHOLD_MS) return { status: "halted", label: formatTimeAgo(timestamp) };
  return { status: "ok", label: formatTimeAgo(timestamp) };
}

const CheckRow = ({ name, check }) => (
  <div className="flex items-center justify-between py-1.5 border-b border-border-subtle last:border-b-0">
    <div className="flex items-center gap-2">
      <StatusDot status={check.status} />
      <span className="text-xs text-white font-mono">{name}</span>
    </div>
    <span className={`text-[11px] font-mono ${
      check.status === "ok" ? "text-[#10b981]" :
      check.status === "halted" ? "text-[#f59e0b]" :
      "text-[#ef4444]"
    }`}>
      {check.label}
    </span>
  </div>
);

const HealthChecklist = ({ health }) => {
  if (!health) {
    return (
      <div className="text-[#64748b] text-xs font-mono py-4 text-center">
        Loading health data...
      </div>
    );
  }

  const d03 = checkFreshness(health.d03_last_trade_outcome);
  const d11 = checkFreshness(health.d11_last_decision);
  const d05 = checkFreshness(health.d05_last_updated);
  const d12 = checkFreshness(health.d12_last_updated);

  const accounts = health.active_accounts || [];
  const accountCheck = accounts.length > 0
    ? { status: "ok", label: `${accounts.length} active` }
    : { status: "error", label: "None found" };

  return (
    <div>
      <CheckRow name="D03 Trade Outcomes" check={d03} />
      <CheckRow name="D11 Pseudotrader Decisions" check={d11} />
      <CheckRow name="D05 EWMA States" check={d05} />
      <CheckRow name="D12 Kelly Parameters" check={d12} />
      <CheckRow name="D08 Active Accounts" check={accountCheck} />

      {/* Account detail list */}
      {accounts.length > 0 && (
        <div className="mt-2 pl-5">
          {accounts.map((acc) => (
            <div key={acc.account_id} className="flex items-center gap-2 py-0.5">
              <span className="text-[10px] text-[#94a3b8] font-mono">{acc.account_id}</span>
              <span className="text-[9px] text-[#64748b] font-mono uppercase">{acc.status}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default HealthChecklist;
