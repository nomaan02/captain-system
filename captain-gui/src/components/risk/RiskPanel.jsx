import PropTypes from "prop-types";
import useDashboardStore from "../../stores/dashboardStore";
import { formatCurrency, formatPercent } from "../../utils/formatting";

const RiskPanel = ({ className = "" }) => {
  const tsmStatus = useDashboardStore((s) => s.tsmStatus);
  const capitalSilo = useDashboardStore((s) => s.capitalSilo);
  const payoutPanel = useDashboardStore((s) => s.payoutPanel);
  const connected = useDashboardStore((s) => s.connected);
  const timestamp = useDashboardStore((s) => s.timestamp);
  const dailyTradeStats = useDashboardStore((s) => s.dailyTradeStats);
  const selectedAccount = useDashboardStore((s) => s.selectedAccount);
  const accounts = useDashboardStore((s) => s.accounts);

  // Derived values
  const tsm = tsmStatus?.[0];
  const startingBalance = tsm?.starting_balance ?? 150000;
  const currentBalance = tsm?.current_balance ?? startingBalance;
  const cumulativePnl = currentBalance - startingBalance;
  const mddUsedPct = tsm?.mdd_used_pct ?? 0;
  const mddLimit = tsm?.mdd_limit ?? 4500;
  const mddUsed = (mddUsedPct / 100) * mddLimit;
  const dailyDdUsedPct = tsm?.daily_dd_used_pct ?? 0;
  const dailyDdLimit = tsm?.daily_dd_limit ?? 2250;
  const dailyDdUsed = (dailyDdUsedPct / 100) * dailyDdLimit;
  const profitTarget = tsm?.profit_target ?? 4500;
  const remaining = Math.max(0, profitTarget - cumulativePnl);
  const targetPct = profitTarget > 0 ? Math.min(100, (cumulativePnl / profitTarget) * 100) : 0;
  const payout = payoutPanel?.[0];

  return (
    <div
      data-testid="risk-panel"
      className={`bg-[#080e0d] border-[#1a3038] border-solid border box-border flex flex-col items-end pt-px px-px pb-7 gap-2.5 max-w-full text-left text-[11px] text-[rgba(15,175,122,0.7)] font-mono h-full overflow-y-auto sm:h-auto ${className}`}
    >
      {/* Header: green dot + RISK MANAGEMENT + timestamp + LIVE badge */}
      <div className="self-stretch flex items-start pt-0 px-0 pb-1 box-border max-w-full shrink-0 text-sm text-[#fff]">
        <div className="flex-1 bg-[#0a1614] border-[#1a3038] border-solid border-b box-border flex items-end justify-between pt-1.5 px-3 pb-1.5 gap-5 max-w-full flex-nowrap">
          <div className="flex items-start gap-2.5">
            <div className="flex flex-col items-start pt-1.5 px-0 pb-0">
              <div className="size-2.5 relative rounded-full bg-[rgba(15,175,122,0.95)]" />
            </div>
            <div className="relative tracking-[2.76px] leading-5 uppercase shrink-0">
              Risk Management
            </div>
          </div>
          <div className="flex items-start gap-3 text-[11px] text-[rgba(226,232,240,0.4)]">
            <div className="flex flex-col items-start pt-0.5 px-0 pb-0">
              <div className="relative leading-4">
                {timestamp ? new Date(timestamp).toLocaleTimeString("en-US", { hour12: false, timeZone: "America/New_York" }) + " ET" : "—"}
              </div>
            </div>
            <div className={`h-[22px] ${connected ? "bg-[#11300b] border-[#55d869]" : "bg-[#300b0b] border-[#d85555]"} border-solid border box-border flex items-start pt-px pb-0 pl-[7px] pr-[5px]`}>
              <div className={`relative leading-4 ${connected ? "text-[#0faf7a]" : "text-[#ef4444]"}`}>
                {connected ? "LIVE" : "OFFLINE"}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Capital cards row: CAPITAL | EQUITY | CUMULATIVE P&L */}
      <div className="self-stretch flex items-start justify-end py-0 pl-[13px] pr-3 box-border max-w-full shrink-0 text-[rgba(226,232,240,0.5)]">
        <div className="flex-1 flex items-start gap-1.5 max-w-full flex-nowrap">
          <div className="flex-1 min-w-0 bg-[#08100f] border-[#2e4e59] border-solid border box-border flex flex-col items-start py-1 pl-2.5 pr-2 min-h-[55px]">
            <div className="leading-4">CAPITAL</div>
            <div data-testid="risk-capital-value" className="text-lg text-[#fff] leading-7 whitespace-nowrap">
              {formatCurrency(startingBalance)}
            </div>
          </div>
          <div className="flex-1 min-w-0 bg-[#08100f] border-[#2e4e59] border-solid border box-border flex flex-col items-start py-1 pl-2.5 pr-2 min-h-[55px]">
            <div className="leading-4">EQUITY</div>
            <div data-testid="risk-equity-value" className="text-lg text-[#fff] leading-7 whitespace-nowrap">
              {formatCurrency(currentBalance)}
            </div>
          </div>
          <div className="flex-1 min-w-0 bg-[#08100f] border-[#2e4e59] border-solid border box-border flex flex-col items-start py-1 px-2.5 min-h-[55px]">
            <div className="leading-4 whitespace-nowrap">{`CUMULATIVE P&L`}</div>
            <div data-testid="risk-cumulative-pnl" className={`text-lg leading-7 whitespace-nowrap ${cumulativePnl >= 0 ? "text-[#0faf7a]" : "text-[#ef4444]"}`}>
              {formatCurrency(cumulativePnl, { showSign: true })}
            </div>
          </div>
        </div>
      </div>

      {/* Drawdown Limits section */}
      <div className="self-stretch flex items-start justify-end py-0 pl-[13px] pr-3 box-border max-w-full shrink-0">
        <div className="flex-1 border-[rgba(46,78,89,0.5)] border-solid border-t box-border flex flex-col items-start pt-[7px] px-0 pb-0 gap-1.5 max-w-full">
          <div className="relative tracking-[1.61px] leading-4 uppercase shrink-0">
            Drawdown Limits
          </div>
          <div className="self-stretch flex flex-col items-start gap-2 max-w-full shrink-0 text-xs text-[rgba(226,232,240,0.6)]">
            {/* MAX DD bar */}
            <div className="self-stretch flex flex-col items-end gap-1">
              <div className="self-stretch flex items-center gap-3 flex-nowrap">
                <div className="shrink-0 w-[60px] tracking-[0.31px] leading-[18px]">MAX DD</div>
                <div className="flex-1 min-w-0">
                  <div
                    data-testid="risk-mdd-bar"
                    className="flex items-start gap-[3px]"
                    role="progressbar"
                    aria-valuenow={Math.round(mddUsedPct)}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-label="Maximum drawdown usage"
                  >
                    {Array.from({ length: 10 }, (_, i) => {
                      const filledSegments = Math.round(mddUsedPct / 10);
                      const filled = i < filledSegments;
                      return (
                        <div
                          key={i}
                          className={`h-4 flex-1 min-w-0 border-solid border box-border ${filled ? "bg-[#ff8800] border-[#ff8800]" : "bg-[rgba(226,232,240,0.08)] border-[rgba(226,232,240,0.12)]"}`}
                        />
                      );
                    })}
                  </div>
                </div>
                <div data-testid="risk-mdd-percent" className="shrink-0 w-[48px] text-right leading-[18px] text-[#ff8800]">
                  {formatPercent(mddUsedPct)}
                </div>
              </div>
              <div className="self-stretch flex items-start justify-between text-[11px] text-[rgba(226,232,240,0.35)]">
                <div className="leading-4">{`Used: ${formatCurrency(mddUsed)} / ${formatCurrency(mddLimit)}`}</div>
                <div className="leading-4">{`Floor: ${formatCurrency(currentBalance - mddLimit)}`}</div>
              </div>
            </div>

            {/* DAILY DD bar */}
            <div className="self-stretch flex flex-col items-end gap-1">
              <div className="self-stretch flex items-center gap-3 flex-nowrap">
                <div className="shrink-0 w-[60px] tracking-[0.31px] leading-[18px]">DAILY DD</div>
                <div className="flex-1 min-w-0">
                  <div
                    data-testid="risk-daily-dd-bar"
                    className="flex items-start gap-[3px]"
                    role="progressbar"
                    aria-valuenow={Math.round(dailyDdUsedPct)}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-label="Daily drawdown usage"
                  >
                    {Array.from({ length: 10 }, (_, i) => {
                      const filledSegments = Math.round(dailyDdUsedPct / 10);
                      const filled = i < filledSegments;
                      return (
                        <div
                          key={i}
                          className={`h-4 flex-1 min-w-0 border-solid border box-border ${filled ? "bg-[#ff8800] border-[#ff8800]" : "bg-[rgba(226,232,240,0.08)] border-[rgba(226,232,240,0.12)]"}`}
                        />
                      );
                    })}
                  </div>
                </div>
                <div data-testid="risk-daily-dd-percent" className="shrink-0 w-[48px] text-right leading-[18px] text-[#3b82f6]">
                  {formatPercent(dailyDdUsedPct)}
                </div>
              </div>
              <div className="self-stretch flex items-start justify-between text-[11px] text-[rgba(226,232,240,0.35)]">
                <div className="leading-4">{`Used: ${formatCurrency(dailyDdUsed)} / ${formatCurrency(dailyDdLimit)}`}</div>
                <div className="leading-4">{`Floor: ${formatCurrency(currentBalance - dailyDdLimit)}`}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Payout Target section */}
      <div className="self-stretch flex items-start justify-end py-0 pl-[13px] pr-3 box-border max-w-full shrink-0">
        <div className="flex-1 border-[rgba(46,78,89,0.5)] border-solid border-t box-border flex flex-col items-start pt-[7px] px-0 pb-0 gap-1.5 max-w-full">
          <div className="relative tracking-[1.61px] leading-4 uppercase">
            Payout Target
          </div>
          <div className="self-stretch bg-[#08100f] border-[#2e4e59] border-solid border box-border flex flex-col items-start pt-1.5 pb-[5px] pl-2.5 pr-2 gap-1 min-h-[73px] text-xs text-[rgba(226,232,240,0.6)]">
            <div className="self-stretch flex items-center justify-between gap-3 flex-nowrap">
              <div className="leading-[18px] min-w-0 truncate">
                <span>{`TARGET: ${formatCurrency(profitTarget)} — REMAINING: `}</span>
                <span data-testid="risk-payout-remaining" className="text-[#fbbf24]">{formatCurrency(remaining)}</span>
              </div>
              <div className="shrink-0 text-sm leading-5 text-[#0faf7a]">
                {formatPercent(targetPct)}
              </div>
            </div>
            <div
              data-testid="risk-payout-target-bar"
              className="self-stretch bg-[rgba(226,232,240,0.06)] border-[rgba(226,232,240,0.1)] border-solid border overflow-hidden flex items-start py-0 px-px"
              role="progressbar"
              aria-valuenow={Math.round(targetPct)}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label="Payout target progress"
            >
              <div className="h-2.5 relative [background:linear-gradient(90deg,_#0faf7a,_#34d399)]" style={{ width: `${targetPct}%` }} />
            </div>
            <div className="self-stretch flex items-start justify-between text-[11px] text-[rgba(226,232,240,0.35)]">
              <div className="leading-4">$0</div>
              <div className="leading-4 text-[#fbbf24]">
                {remaining > 0 ? `~${formatCurrency(remaining)} to go` : "Target reached!"}
              </div>
              <div className="leading-4">{formatCurrency(profitTarget)}</div>
            </div>
          </div>
        </div>
      </div>

      {/* Day Stats section */}
      <div className="self-stretch flex items-start justify-end py-0 pl-[13px] pr-3 box-border max-w-full shrink-0 text-[rgba(226,232,240,0.45)]">
        <div className="flex-1 border-[rgba(46,78,89,0.5)] border-solid border-t box-border flex items-start pt-[7px] px-0 pb-0 max-w-full">
          <div className="self-stretch flex items-end py-0 pl-0 pr-5 box-border gap-8 max-w-full flex-wrap">
            <div className="flex-1 flex flex-col items-start gap-1.5 min-w-[140px] text-[rgba(15,175,122,0.7)]">
              <div className="relative tracking-[1.61px] leading-4 uppercase">
                Day Stats
              </div>
              <div className="self-stretch flex flex-col items-start gap-px text-[rgba(226,232,240,0.45)]">
                <div className="self-stretch flex items-start justify-between gap-5">
                  <div className="relative tracking-[0.54px] leading-4 uppercase">{`Day P&L`}</div>
                  <div className="relative tracking-[0.54px] leading-4 uppercase">
                    Profit Factor
                  </div>
                </div>
                <div className="w-[135px] flex items-start justify-between pt-0 px-0 pb-1.5 box-border gap-5 text-[15px]">
                  <div data-testid="risk-day-pnl" className={`relative leading-[23px] ${(dailyTradeStats?.total_pnl ?? capitalSilo?.daily_pnl ?? 0) >= 0 ? "text-[#0faf7a]" : "text-[#ff0040]"}`}>{formatCurrency(dailyTradeStats?.total_pnl ?? capitalSilo?.daily_pnl ?? 0, { showSign: true })}</div>
                  <div data-testid="risk-profit-factor" className="relative leading-[23px] text-[#e2e8f0]">
                    {dailyTradeStats?.profit_factor ?? "—"}
                  </div>
                </div>
                <div className="w-[180px] flex items-start justify-between gap-5">
                  <div className="relative tracking-[0.54px] leading-4 uppercase">
                    Avg Win
                  </div>
                  <div className="relative tracking-[0.54px] leading-4 uppercase">
                    Avg Loss
                  </div>
                </div>
                <div className="w-[170px] flex items-start justify-between gap-5 text-[15px]">
                  <div className="relative leading-[23px] text-[#0faf7a]">{dailyTradeStats?.avg_win != null ? formatCurrency(dailyTradeStats.avg_win) : "$0.00"}</div>
                  <div className="relative leading-[23px] text-[#ff0040] text-center">
                    {dailyTradeStats?.avg_loss != null ? formatCurrency(dailyTradeStats.avg_loss) : "$0.00"}
                  </div>
                </div>
              </div>
            </div>
            <div className="w-[91px] flex flex-col items-start py-0 pl-0 pr-5 box-border gap-px">
              <div className="relative tracking-[0.54px] leading-4 uppercase">
                Wins
              </div>
              <div className="flex items-start pt-0 px-0 pb-1.5 text-center text-[15px] text-[#0faf7a]">
                <div data-testid="risk-wins" className="relative leading-[23px]">{dailyTradeStats?.wins ?? 0}</div>
              </div>
              <div className="relative tracking-[0.54px] leading-4 uppercase">
                R:R Ratio
              </div>
              <div className="relative text-[15px] leading-[23px] text-[#e2e8f0]">
                {dailyTradeStats?.avg_win != null && dailyTradeStats?.avg_loss != null && dailyTradeStats.avg_loss !== 0 ? (Math.abs(dailyTradeStats.avg_win) / Math.abs(dailyTradeStats.avg_loss)).toFixed(1) : "—"}
              </div>
            </div>
            <div className="flex flex-col items-start py-0 pl-0 pr-[49px] gap-1.5">
              <div className="flex flex-col items-start gap-px">
                <div className="relative tracking-[0.54px] leading-4 uppercase">
                  Losses
                </div>
                <div data-testid="risk-losses" className="relative text-[15px] leading-[23px] text-[#ff0040] text-center">
                  {dailyTradeStats?.losses ?? 0}
                </div>
              </div>
              <div className="flex flex-col items-start gap-px">
                <div className="relative tracking-[0.54px] leading-4 uppercase">
                  Trades
                </div>
                <div data-testid="risk-trades" className="relative text-[15px] leading-[23px] text-[#e2e8f0] text-center">
                  {dailyTradeStats?.trades_today ?? 0}
                </div>
              </div>
            </div>
            <div className="flex flex-col items-start gap-px">
              <div className="relative tracking-[0.54px] leading-4 uppercase">
                Win%
              </div>
              <div className="flex items-start pt-0 px-0 pb-1.5 text-[15px] text-[#e2e8f0]">
                <div data-testid="risk-win-pct" className="relative leading-[23px]">{dailyTradeStats?.win_pct != null ? `${dailyTradeStats.win_pct}%` : "—"}</div>
              </div>
              <div className="relative tracking-[0.54px] leading-4 uppercase">
                Net Ticks
              </div>
              <div className="relative text-[15px] leading-[23px] text-[#e2e8f0] text-center">
                &mdash;
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Payout Info section */}
      <div className="self-stretch flex items-start justify-end py-0 pl-[13px] pr-3 box-border max-w-full shrink-0 text-[rgba(226,232,240,0.45)]">
        <div className="flex-1 border-[rgba(46,78,89,0.5)] border-solid border-t box-border flex flex-col items-start pt-[7px] px-0 pb-0 gap-1.5 max-w-full">
          <div className="relative tracking-[1.61px] leading-4 uppercase text-[rgba(15,175,122,0.7)]">
            Payout Info
          </div>
          <div className="self-stretch flex items-start gap-8 flex-wrap text-[rgba(226,232,240,0.45)]">
            <div className="flex flex-col items-start gap-px">
              <div className="tracking-[0.54px] leading-4 uppercase">Payout ID</div>
              <div className="text-[15px] leading-[23px] text-[#e2e8f0]">{payout?.payout_id ?? tsm?.account_id ?? "—"}</div>
            </div>
            <div className="flex flex-col items-start gap-px">
              <div className="tracking-[0.54px] leading-4 uppercase">Status</div>
              <div className="text-[15px] leading-[23px] text-[#e2e8f0]">{payout?.status ?? "—"}</div>
            </div>
            <div className="flex flex-col items-start gap-px">
              <div className="tracking-[0.54px] leading-4 uppercase">Amount</div>
              <div className="text-[15px] leading-[23px] text-[#e2e8f0]">{formatCurrency(payout?.amount ?? 0)}</div>
            </div>
            <div className="flex flex-col items-start gap-px">
              <div className="tracking-[0.54px] leading-4 uppercase">Tier</div>
              <div className="text-[15px] leading-[23px] text-[#e2e8f0]">{payout?.tier ?? "Unknown"}</div>
            </div>
            <div className="flex flex-col items-start gap-px">
              <div className="tracking-[0.54px] leading-4 uppercase">Method</div>
              <div className="text-[15px] leading-[23px] text-[#e2e8f0]">{payout?.method ?? "Systematic"}</div>
            </div>
            <div className="flex flex-col items-start gap-px">
              <div className="tracking-[0.54px] leading-4 uppercase">Next Eligible</div>
              <div className="text-[15px] leading-[23px] text-[#e2e8f0]">{payout?.next_eligible_date ?? "TBD"}</div>
            </div>
          </div>
        </div>
      </div>

      {/* Accounts section */}
      <div className="self-stretch flex items-start justify-end py-0 pl-[13px] pr-3 box-border max-w-full shrink-0 text-sm">
        <div className="flex-1 border-[rgba(46,78,89,0.5)] border-solid border-t box-border flex flex-col items-start pt-[7px] px-0 pb-0 gap-1 max-w-full">
          <div className="relative text-[11px] tracking-[1.61px] leading-4 uppercase shrink-0">
            Accounts
          </div>
          {accounts.map((acc, idx) => {
            const isActive = acc.id === selectedAccount;
            const balance = tsmStatus?.[idx]?.current_balance ?? 150000;
            return (
              <div
                data-testid="risk-account"
                key={acc.id}
                className={`self-stretch flex items-start justify-between gap-5 shrink-0 ${
                  isActive ? "text-[#fff]" : "text-[rgba(255,255,255,0.35)]"
                }`}
              >
                <div className="relative leading-[21px]">{acc.id}</div>
                <div className="flex items-start gap-2">
                  <div className="relative leading-5 shrink-0">
                    {formatCurrency(balance)}
                  </div>
                  <div
                    className={`border-solid border flex items-start py-0 pl-[5px] pr-1 shrink-0 text-[11px] ${
                      isActive
                        ? "bg-[#11300b] border-[#55d869] text-[#0faf7a]"
                        : "bg-[#1a0000] border-[#c10000] text-[#c10000]"
                    }`}
                  >
                    <div data-testid="risk-account-status" className="relative leading-4">
                      {isActive ? "ACTIVE" : "INACTIVE"}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Risk Parameters section */}
      <div className="self-stretch flex items-start justify-end py-0 pl-[13px] pr-3 box-border max-w-full shrink-0">
        <div className="flex-1 border-[rgba(46,78,89,0.5)] border-solid border-t box-border flex flex-col items-start pt-[7px] px-0 pb-0 gap-1.5 max-w-full">
          <div className="relative tracking-[1.61px] leading-4 uppercase shrink-0">
            Risk Parameters
          </div>
          <div className="self-stretch flex items-start gap-1.5 shrink-0 text-[rgba(226,232,240,0.45)] flex-wrap">
            <div className="flex-1 flex flex-col items-start gap-px min-w-[112px]">
              <div className="relative tracking-[0.54px] leading-4 uppercase shrink-0">
                Max DD
              </div>
              <div data-testid="risk-max-dd-param" className="relative text-[15px] leading-[23px] text-[#ff8800] shrink-0">
                {formatCurrency(mddLimit)}
              </div>
            </div>
            <div className="flex-1 flex flex-col items-start gap-px min-w-[112px]">
              <div className="relative tracking-[0.54px] leading-4 uppercase shrink-0">
                Daily DD
              </div>
              <div data-testid="risk-daily-dd-param" className="relative text-[15px] leading-[23px] text-[#3b82f6] text-center shrink-0">
                {formatCurrency(dailyDdLimit)}
              </div>
            </div>
            <div className="flex-1 flex flex-col items-start gap-px min-w-[112px]">
              <div className="relative tracking-[0.54px] leading-4 uppercase shrink-0">
                Max Lots
              </div>
              <div data-testid="risk-max-lots-param" className="relative text-[15px] leading-[23px] text-[#e2e8f0] shrink-0">
                {tsm?.max_lots ?? "—"}
              </div>
            </div>
            <div className="flex-1 flex flex-col items-start gap-px min-w-[112px]">
              <div className="relative tracking-[0.54px] leading-4 uppercase shrink-0">
                Consistency
              </div>
              <div className="relative text-[15px] leading-[23px] text-[#e2e8f0] shrink-0">
                {tsm?.consistency_score != null ? formatPercent(tsm.consistency_score) : "—"}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="self-stretch min-h-[22px] flex items-start justify-end py-0 pl-[13px] pr-3 box-border max-w-full shrink-0 text-[rgba(226,232,240,0.25)]">
        <div className="self-stretch flex-1 border-[rgba(46,78,89,0.3)] border-solid border-t box-border overflow-x-auto flex items-start justify-between pt-0.5 px-0 pb-0.5 gap-5 max-w-full">
          <div className="relative leading-4 whitespace-nowrap">SYS:RISK_MGR</div>
          <div className="relative leading-4 whitespace-nowrap">BROKER:TOPSTEPX</div>
          <div className="relative leading-4 whitespace-nowrap">{timestamp ? `UPD: ${new Date(timestamp).toLocaleTimeString("en-US", { hour12: false, timeZone: "America/New_York" })}` : "UPD: —"}</div>
        </div>
      </div>
    </div>
  );
};

RiskPanel.propTypes = {
  className: PropTypes.string,
};

export default RiskPanel;
