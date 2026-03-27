import { useDashboardStore } from "@/stores/dashboardStore";
import { Panel } from "@/components/ui/panel";
import { Badge } from "@/components/ui/badge";
import { DataCell, DataCellRow } from "@/components/ui/data-cell";
import { ProgressBar } from "@/components/ui/progress-bar";
import { ScrollArea } from "@/components/ui/scroll-area";
import { formatCurrency, formatPct } from "@/utils/formatters";

export function RiskLimitsCell() {
  const silo = useDashboardStore((s) => s.capitalSilo);
  const tsmStatus = useDashboardStore((s) => s.tsmStatus);

  const dailyPnl = silo?.daily_pnl ?? 0;

  return (
    <Panel
      title="RISK LIMITS"
      accent="gray"
      headerRight={
        <Badge variant={dailyPnl >= 0 ? "go" : "danger"} size="sm">
          {dailyPnl >= 0 ? "+" : ""}{formatCurrency(dailyPnl)}
        </Badge>
      }
    >
      <ScrollArea className="max-h-[220px]">
        {/* Capital summary */}
        <DataCellRow className="mb-2 grid-cols-2">
          <DataCell label="Capital" value={formatCurrency(silo?.total_capital)} />
          <DataCell
            label="Cumulative"
            value={formatCurrency(silo?.cumulative_pnl)}
            valueColor={
              (silo?.cumulative_pnl ?? 0) >= 0 ? "text-green" : "text-red"
            }
          />
        </DataCellRow>

        {/* Per-account TSM */}
        {tsmStatus.length === 0 ? (
          <div className="py-2 text-[11px] text-dim">No accounts loaded</div>
        ) : (
          tsmStatus.map((acct) => (
            <div key={acct.account_id} className="mb-2">
              <div className="mb-1 flex items-center justify-between">
                <span className="text-[11px] font-semibold text-foreground">
                  {acct.account_id}
                </span>
                <span className="text-[11px] text-dim">{acct.tsm_name}</span>
              </div>

              <ProgressBar
                value={acct.mdd_used_pct}
                label="MDD"
                showValue
                className="mb-1"
              />
              <ProgressBar
                value={acct.daily_loss_pct}
                label="Daily"
                showValue
                className="mb-1"
              />

              {acct.pass_probability != null && (
                <div className="text-[11px] text-dim">
                  Pass prob:{" "}
                  <span className="font-semibold text-foreground">
                    {formatPct(acct.pass_probability * 100)}
                  </span>
                </div>
              )}
            </div>
          ))
        )}
      </ScrollArea>
    </Panel>
  );
}
