import { useDashboardStore } from "@/stores/dashboardStore";
import { Panel } from "@/components/ui/panel";
import { Badge } from "@/components/ui/badge";
import { DataCell, DataCellRow } from "@/components/ui/data-cell";
import { formatCurrency } from "@/utils/formatters";

/** Extract display symbol from TopstepX contract_id */
function contractSymbol(contractId: string): string {
  const parts = contractId.split(".");
  if (parts.length < 5) return contractId;
  const instrument = parts[3];
  const monthYear = parts[4];
  const display =
    instrument === "EP" ? "ES" : instrument === "ENQ" ? "NQ" : instrument;
  return `${display}${monthYear}`;
}

export function LiveMarketCell() {
  const lm = useDashboardStore((s) => s.liveMarket);

  const connected = lm?.connected ?? false;
  const symbol = lm ? contractSymbol(lm.contract_id) : "—";
  const price = lm?.last_price;
  const change = lm?.change;
  const changePct = lm?.change_pct;
  const isUp = (change ?? 0) >= 0;

  // Split price into whole and decimal
  const priceStr = price != null ? price.toFixed(2) : "—";
  const dotIdx = priceStr.indexOf(".");
  const priceWhole = dotIdx >= 0 ? priceStr.slice(0, dotIdx) : priceStr;
  const priceDecimal = dotIdx >= 0 ? priceStr.slice(dotIdx) : "";

  return (
    <Panel
      title="LIVE MARKET"
      accent="blue"
      headerRight={
        connected ? (
          <Badge variant="info" size="sm">{symbol}</Badge>
        ) : (
          <Badge variant="neutral" size="sm">OFFLINE</Badge>
        )
      }
    >
      {/* Price */}
      <div className="mb-2 flex items-baseline gap-2">
        <span className="text-[22px] font-bold text-foreground">
          {priceWhole}
        </span>
        <span className="text-[15px] text-muted-foreground">{priceDecimal}</span>
        {change != null && (
          <span
            className="text-[11px] font-semibold"
            style={{ color: isUp ? "#4ade80" : "#f87171" }}
          >
            {isUp ? "+" : ""}
            {change.toFixed(2)}
            {changePct != null && (
              <span className="ml-0.5 text-muted-foreground">
                ({isUp ? "+" : ""}{changePct.toFixed(2)}%)
              </span>
            )}
          </span>
        )}
      </div>

      {/* Bid / Ask / Spread */}
      <DataCellRow className="mb-1.5 grid-cols-3">
        <DataCell label="Bid" value={lm?.best_bid?.toFixed(2) ?? "—"} />
        <DataCell label="Ask" value={lm?.best_ask?.toFixed(2) ?? "—"} />
        <DataCell label="Spread" value={lm?.spread?.toFixed(2) ?? "—"} />
      </DataCellRow>

      {/* Open / High / Low / Vol */}
      <DataCellRow className="grid-cols-4">
        <DataCell label="Open" value={lm?.open?.toFixed(2) ?? "—"} />
        <DataCell label="High" value={lm?.high?.toFixed(2) ?? "—"} />
        <DataCell label="Low" value={lm?.low?.toFixed(2) ?? "—"} />
        <DataCell label="Vol" value={lm?.volume?.toLocaleString() ?? "—"} />
      </DataCellRow>
    </Panel>
  );
}
