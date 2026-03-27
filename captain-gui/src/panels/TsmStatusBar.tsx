import { useDashboardStore } from "@/stores/dashboardStore";
import { ProgressBar } from "@/components/ProgressBar";
import { formatCurrency, formatPct } from "@/utils/formatters";

export function TsmStatusBar() {
  const tsmStatus = useDashboardStore((s) => s.tsmStatus);

  if (tsmStatus.length === 0) {
    return (
      <div className="panel">
        <div className="panel-header">Account Risk</div>
        <p className="text-sm text-gray-400">No accounts loaded</p>
      </div>
    );
  }

  return (
    <div className="panel">
      <div className="panel-header">Account Risk (TSM)</div>
      <div className="space-y-4">
        {tsmStatus.map((acct) => (
          <div key={acct.account_id} className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="font-medium">{acct.account_id}</span>
              <span className="text-xs text-gray-400">{acct.tsm_name}</span>
            </div>
            <div className="text-xs text-gray-500 dark:text-gray-400">
              Balance: {formatCurrency(acct.current_balance)}
            </div>

            {/* MDD bar */}
            <div>
              <ProgressBar
                value={acct.mdd_used_pct}
                color={acct.mdd_used_pct > 80 ? "bg-red-500" : acct.mdd_used_pct > 50 ? "bg-yellow-500" : "bg-captain-blue"}
                showLabel
                label={`MDD ${formatPct(acct.mdd_used_pct)} of ${formatCurrency(acct.mdd_limit)}`}
              />
            </div>

            {/* Daily loss bar */}
            <div>
              <ProgressBar
                value={acct.daily_loss_pct}
                color={acct.daily_loss_pct > 80 ? "bg-red-500" : acct.daily_loss_pct > 50 ? "bg-yellow-500" : "bg-captain-green"}
                showLabel
                label={`Daily ${formatPct(acct.daily_loss_pct)} (${formatCurrency(acct.daily_loss_used)} / ${formatCurrency(acct.daily_loss_limit)})`}
              />
            </div>

            {acct.pass_probability != null && (
              <div className="text-xs text-gray-500">
                Pass probability: <span className="font-mono">{formatPct(acct.pass_probability * 100)}</span>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
