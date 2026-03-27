import { useDashboardStore } from "@/stores/dashboardStore";
import { Panel } from "@/components/ui/panel";
import { DataCell, DataCellRow } from "@/components/ui/data-cell";
import { ProgressBar } from "@/components/ui/progress-bar";
import { ScrollArea } from "@/components/ui/scroll-area";
import { formatCurrency, formatPct } from "@/utils/formatters";

export function DayStatsCell() {
  const silo = useDashboardStore((s) => s.capitalSilo);
  const positions = useDashboardStore((s) => s.openPositions);
  const payouts = useDashboardStore((s) => s.payoutPanel);
  const scaling = useDashboardStore((s) => s.scalingDisplay);

  const wins = positions.filter((p) => (p.current_pnl ?? 0) > 0).length;
  const losses = positions.filter((p) => (p.current_pnl ?? 0) < 0).length;
  const totalPnl = positions.reduce((s, p) => s + (p.current_pnl ?? 0), 0);
  const grossWins = positions
    .filter((p) => (p.current_pnl ?? 0) > 0)
    .reduce((s, p) => s + (p.current_pnl ?? 0), 0);
  const grossLoss = positions
    .filter((p) => (p.current_pnl ?? 0) < 0)
    .reduce((s, p) => s + Math.abs(p.current_pnl ?? 0), 0);
  const pf = grossLoss > 0 ? (grossWins / grossLoss).toFixed(2) : "—";
  const avgWin = wins > 0 ? grossWins / wins : 0;
  const avgLoss = losses > 0 ? grossLoss / losses : 0;

  return (
    <Panel title="DAY STATS" accent="gray">
      <ScrollArea className="max-h-[280px]">
        {/* Summary row */}
        <DataCellRow className="mb-2 grid-cols-2">
          <DataCell
            label="Day P&L"
            value={`${totalPnl >= 0 ? "+" : ""}${formatCurrency(totalPnl)}`}
            valueColor={totalPnl >= 0 ? "text-green" : "text-red"}
          />
          <DataCell label="Profit Factor" value={pf} />
        </DataCellRow>

        <DataCellRow className="mb-2 grid-cols-3">
          <DataCell label="Wins" value={`${wins}`} valueColor="text-green" />
          <DataCell label="Losses" value={`${losses}`} valueColor="text-red" />
          <DataCell
            label="Win%"
            value={
              wins + losses > 0
                ? `${((wins / (wins + losses)) * 100).toFixed(0)}%`
                : "—"
            }
          />
        </DataCellRow>

        <DataCellRow className="mb-2 grid-cols-2">
          <DataCell label="Avg Win" value={formatCurrency(avgWin)} valueColor="text-green" />
          <DataCell label="Avg Loss" value={formatCurrency(avgLoss)} valueColor="text-red" />
        </DataCellRow>

        {/* Payout info */}
        {payouts.length > 0 && (
          <div className="mt-2">
            <div className="mb-1 text-[11px] text-dim">Payout</div>
            {payouts.map((p) => (
              <div key={p.account_id} className="mb-1 rounded-[3px] bg-card-elevated p-1.5">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="font-semibold text-foreground">{p.account_id}</span>
                  {p.recommended ? (
                    <span className="text-green">REC</span>
                  ) : (
                    <span className="text-dim">—</span>
                  )}
                </div>
                <div className="mt-0.5 flex gap-3 text-[11px] text-dim">
                  <span>Amt: {formatCurrency(p.amount)}</span>
                  <span>Tier: {p.tier_current}</span>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Scaling info */}
        {scaling.length > 0 && (
          <div className="mt-2">
            <div className="mb-1 text-[11px] text-dim">Scaling</div>
            {scaling.map((s) => (
              <div key={s.account_id} className="mb-1">
                <div className="mb-0.5 flex items-center justify-between text-[11px]">
                  <span className="text-foreground">{s.current_tier}</span>
                  <span className="text-dim">
                    {s.available_slots} slots free
                  </span>
                </div>
                <ProgressBar
                  value={s.open_positions_micros}
                  max={s.current_max_micros || 1}
                  color="#8b5cf6"
                />
              </div>
            ))}
          </div>
        )}
      </ScrollArea>
    </Panel>
  );
}
