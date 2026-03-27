import { useDashboardStore } from "@/stores/dashboardStore";
import { formatCurrency, formatPct } from "@/utils/formatters";
import { DollarSign, TrendingUp } from "lucide-react";

export function PayoutPanel() {
  const payouts = useDashboardStore((s) => s.payoutPanel);

  if (payouts.length === 0) return null;

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="flex items-center gap-1.5">
          <DollarSign className="h-3.5 w-3.5" /> Payout (Topstep)
        </span>
      </div>
      <div className="space-y-3">
        {payouts.map((p) => (
          <div key={p.account_id} className="space-y-2 rounded border border-gray-200 p-2 dark:border-gray-700">
            <div className="flex items-center justify-between text-sm">
              <span className="font-medium">{p.account_id}</span>
              {p.recommended ? (
                <span className="rounded bg-green-500/20 px-2 py-0.5 text-xs font-medium text-green-600 dark:text-green-400">
                  RECOMMENDED
                </span>
              ) : (
                <span className="text-xs text-gray-400">Not recommended</span>
              )}
            </div>

            <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
              <div className="flex justify-between text-gray-500 dark:text-gray-400">
                <span>Payout</span>
                <span className="font-mono">{formatCurrency(p.amount)}</span>
              </div>
              <div className="flex justify-between text-gray-500 dark:text-gray-400">
                <span>Net (after fee)</span>
                <span className="font-mono">{formatCurrency(p.net_after_commission)}</span>
              </div>
              <div className="flex justify-between text-gray-500 dark:text-gray-400">
                <span>Profit now</span>
                <span className="font-mono">{formatCurrency(p.profit_current)}</span>
              </div>
              <div className="flex justify-between text-gray-500 dark:text-gray-400">
                <span>Profit after</span>
                <span className="font-mono">{formatCurrency(p.profit_after)}</span>
              </div>
              <div className="flex justify-between text-gray-500 dark:text-gray-400">
                <span>MDD% now</span>
                <span className="font-mono">{formatPct(p.mdd_pct_current)}</span>
              </div>
              <div className="flex justify-between text-gray-500 dark:text-gray-400">
                <span>MDD% after</span>
                <span className="font-mono">{formatPct(p.mdd_pct_after)}</span>
              </div>
              <div className="flex justify-between text-gray-500 dark:text-gray-400">
                <span>Tier</span>
                <span>{p.tier_current} → {p.tier_after}</span>
              </div>
              <div className="flex justify-between text-gray-500 dark:text-gray-400">
                <span>Payouts left</span>
                <span>{p.payouts_remaining}</span>
              </div>
              <div className="flex justify-between text-gray-500 dark:text-gray-400">
                <span>Winning days</span>
                <span>{p.winning_days_current ?? 0} / {p.winning_days_required ?? 30}</span>
              </div>
              {p.next_eligible_date && (
                <div className="flex justify-between text-gray-500 dark:text-gray-400">
                  <span>Next eligible</span>
                  <span>{p.next_eligible_date}</span>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
