import { useDashboardStore } from "@/stores/dashboardStore";
import { formatCurrency } from "@/utils/formatters";
import { Activity } from "lucide-react";

/** Extract a human-readable symbol from a TopstepX contract_id.
 *  "CON.F.US.MES.M26" → "MESM6", "CON.F.US.EP.M26" → "ESM6" */
function contractSymbol(contractId: string): string {
  const parts = contractId.split(".");
  if (parts.length < 5) return contractId;
  const instrument = parts[3]; // MES, EP, ENQ, etc.
  const monthYear = parts[4]; // M26, H26, etc.
  // EP → ES display name
  const display = instrument === "EP" ? "ES" : instrument === "ENQ" ? "NQ" : instrument;
  return `${display}${monthYear}`;
}

export function LiveMarketPanel() {
  const lm = useDashboardStore((s) => s.liveMarket);

  if (!lm || !lm.connected) {
    return (
      <div className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900">
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-400">
          Live Market
        </h3>
        <p className="text-sm text-gray-500">Market stream disconnected</p>
      </div>
    );
  }

  const symbol = contractSymbol(lm.contract_id);
  const price = lm.last_price;
  const bid = lm.best_bid;
  const ask = lm.best_ask;
  const spread = lm.spread;
  const change = lm.change;
  const changePct = lm.change_pct;
  const isUp = change != null && change >= 0;

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-400">
          Live Market
        </h3>
        <div className="flex items-center gap-1.5">
          <Activity className="h-3 w-3 text-green-500" />
          <span className="text-[10px] font-medium text-green-500">{symbol}</span>
        </div>
      </div>

      <div className="flex items-baseline gap-3">
        <span className="text-2xl font-bold tabular-nums">
          {price != null ? formatCurrency(price) : "---"}
        </span>
        {change != null && (
          <span className={`text-sm font-medium tabular-nums ${isUp ? "text-green-400" : "text-red-400"}`}>
            {isUp ? "+" : ""}{change.toFixed(2)}
            {changePct != null && (
              <span className="ml-1 text-xs">
                ({isUp ? "+" : ""}{changePct.toFixed(2)}%)
              </span>
            )}
          </span>
        )}
      </div>

      <div className="mt-2 grid grid-cols-3 gap-2 text-xs text-gray-400">
        <div>
          <span className="block text-[10px] uppercase">Bid</span>
          <span className="tabular-nums text-gray-300">
            {bid != null ? bid.toFixed(2) : "---"}
          </span>
        </div>
        <div>
          <span className="block text-[10px] uppercase">Ask</span>
          <span className="tabular-nums text-gray-300">
            {ask != null ? ask.toFixed(2) : "---"}
          </span>
        </div>
        <div>
          <span className="block text-[10px] uppercase">Spread</span>
          <span className="tabular-nums text-gray-300">
            {spread != null ? spread.toFixed(2) : "---"}
          </span>
        </div>
      </div>
    </div>
  );
}
