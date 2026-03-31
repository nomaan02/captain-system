import PropTypes from "prop-types";
import useDashboardStore from "../../stores/dashboardStore";
import { formatCurrency, formatPercent } from "../../utils/formatting";

const RiskPanel = ({ className = "" }) => {
  const tsmStatus = useDashboardStore((s) => s.tsmStatus);
  const capitalSilo = useDashboardStore((s) => s.capitalSilo);
  const payoutPanel = useDashboardStore((s) => s.payoutPanel);
  const openPositions = useDashboardStore((s) => s.openPositions);
  const connected = useDashboardStore((s) => s.connected);
  const timestamp = useDashboardStore((s) => s.timestamp);
  const apiStatus = useDashboardStore((s) => s.apiStatus);
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
      className={`bg-[#080e0d] border-[#1a3038] border-solid border box-border flex flex-col items-end pt-[1.3px] px-px pb-[29px] gap-[9.1px] max-w-full text-left text-[10.7px] text-[rgba(15,175,122,0.7)] font-['JetBrains_Mono'] h-full overflow-y-auto mq450:h-auto ${className}`}
    >
      {/* Header: green dot + RISK MANAGEMENT + timestamp + LIVE badge */}
      <div className="self-stretch flex items-start pt-0 px-0 pb-[3.1px] box-border max-w-full shrink-0 text-[13.8px] text-[#fff]">
        <div className="flex-1 bg-[#0a1614] border-[#1a3038] border-solid border-b box-border flex items-end justify-between pt-[6.1px] px-3 pb-1.5 gap-5 max-w-full mq450:flex-wrap mq450:gap-5">
          <div className="flex items-start gap-[9.2px]">
            <div className="flex flex-col items-start pt-[5.8px] px-0 pb-0">
              <div className="w-[9.2px] h-[9.2px] relative rounded-full bg-[rgba(15,175,122,0.95)]" />
            </div>
            <div className="relative tracking-[2.76px] leading-[20.7px] uppercase shrink-0">
              Risk Management
            </div>
          </div>
          <div className="flex items-start gap-[11.4px] text-[10.7px] text-[rgba(226,232,240,0.4)]">
            <div className="flex flex-col items-start pt-[2.6px] px-0 pb-0">
              <div className="relative leading-[16.1px]">
                {timestamp ? new Date(timestamp).toLocaleTimeString("en-US", { hour12: false, timeZone: "UTC" }) + " UTC" : "—"}
              </div>
            </div>
            <div className={`h-[21.7px] ${connected ? "bg-[#11300b] border-[#55d869]" : "bg-[#300b0b] border-[#d85555]"} border-solid border box-border flex items-start pt-px pb-0 pl-[7px] pr-[5px]`}>
              <div className={`relative leading-[16.1px] ${connected ? "text-[#0faf7a]" : "text-[#ef4444]"}`}>
                {connected ? "LIVE" : "OFFLINE"}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Capital cards row: CAPITAL | EQUITY | CUMULATIVE P&L */}
      <div className="self-stretch flex items-start justify-end py-0 pl-[13px] pr-3 box-border max-w-full shrink-0 text-[rgba(226,232,240,0.5)]">
        <div className="flex-1 flex items-start gap-[6.1px] max-w-full mq750:flex-wrap">
          <div className="flex-1 bg-[#08100f] border-[#2e4e59] border-solid border box-border flex flex-col items-start py-1 pl-2.5 pr-2 min-w-[151px] min-h-[55px]">
            <div className="relative leading-[16.1px]">CAPITAL</div>
            <div className="flex items-start pt-0 px-0 pb-0 text-[18.4px] text-[#fff]">
              <div data-testid="risk-capital-value" className="mt-[-1px] relative leading-[27.6px]">
                {formatCurrency(startingBalance)}
              </div>
            </div>
          </div>
          <div className="flex-1 bg-[#08100f] border-[#2e4e59] border-solid border box-border flex flex-col items-start py-1 pl-2.5 pr-2 min-w-[151px] min-h-[55px]">
            <div className="relative leading-[16.1px]">EQUITY</div>
            <div className="flex items-start pt-0 px-0 pb-0 text-[18.4px] text-[#fff]">
              <div data-testid="risk-equity-value" className="mt-[-1px] relative leading-[27.6px]">
                {formatCurrency(currentBalance)}
              </div>
            </div>
          </div>
          <div className="flex-1 bg-[#08100f] border-[#2e4e59] border-solid border box-border flex flex-col items-start py-1 px-2.5 min-w-[151px] min-h-[55px]">
            <div className="relative leading-[16.1px]">{`CUMULATIVE P&L`}</div>
            <div className="flex items-start pt-0 px-0 pb-0 text-[18.4px]">
              <div data-testid="risk-cumulative-pnl" className={`mt-[-1px] relative leading-[27.6px] ${cumulativePnl >= 0 ? "text-[#0faf7a]" : "text-[#ef4444]"}`}>
                {formatCurrency(cumulativePnl, { showSign: true })}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Drawdown Limits section */}
      <div className="self-stretch flex items-start justify-end py-0 pl-[13px] pr-3 box-border max-w-full shrink-0">
        <div className="flex-1 border-[rgba(46,78,89,0.5)] border-solid border-t box-border flex flex-col items-start pt-[7px] px-0 pb-[0.1px] gap-[5.4px] max-w-full">
          <div className="relative tracking-[1.61px] leading-[16.1px] uppercase shrink-0">
            Drawdown Limits
          </div>
          <div className="self-stretch flex flex-col items-start gap-[8.5px] max-w-full shrink-0 text-[12.3px] text-[rgba(226,232,240,0.6)]">
            {/* MAX DD bar */}
            <div className="self-stretch flex flex-col items-end gap-[3.7px] max-w-full">
              <div className="self-stretch flex items-start gap-[36.1px] max-w-full mq750:gap-[18px] mq750:flex-wrap mq750:overflow-x-auto">
                <div className="flex flex-col items-start py-0 pl-0 pr-[5px]">
                  <div className="relative tracking-[0.31px] leading-[18.4px]">
                    MAX DD
                  </div>
                </div>
                <div className="flex-1 flex flex-col items-start pt-[1.5px] px-0 pb-0 box-border min-w-[445px] max-w-full">
                  <div data-testid="risk-mdd-bar" className="self-stretch flex items-start gap-[3px] mq450:flex-wrap">
                    {Array.from({ length: 10 }, (_, i) => {
                      const filledSegments = Math.round(mddUsedPct / 10);
                      const filled = i < filledSegments;
                      return (
                        <div
                          key={i}
                          className={`h-[15.3px] w-[42.7px] relative border-solid border box-border ${filled ? "bg-[#ff8800] border-[#ff8800]" : "bg-[rgba(226,232,240,0.08)] border-[rgba(226,232,240,0.12)]"}`}
                        />
                      );
                    })}
                  </div>
                </div>
                <div data-testid="risk-mdd-percent" className="relative leading-[18.4px] text-[#ff8800] text-center">
                  {formatPercent(mddUsedPct)}
                </div>
              </div>
              <div className="max-w-full flex items-start justify-between gap-5 max-w-full text-[10.7px] text-[rgba(226,232,240,0.35)] mq450:flex-wrap mq450:gap-5">
                <div className="relative leading-[16.1px]">
                  {`Used: ${formatCurrency(mddUsed)} / ${formatCurrency(mddLimit)}`}
                </div>
                <div className="relative leading-[16.1px]">
                  {`Floor: ${formatCurrency(currentBalance - mddLimit)}`}
                </div>
              </div>
            </div>

            {/* DAILY DD bar */}
            <div className="self-stretch flex flex-col items-end gap-[3.8px] max-w-full">
              <div className="self-stretch flex items-start gap-[26.8px] max-w-full mq750:flex-wrap">
                <div className="relative tracking-[0.31px] leading-[18.4px] shrink-0">
                  DAILY DD
                </div>
                <div className="flex-1 flex flex-col items-start pt-[1.5px] pb-0 pl-0 pr-4 box-border min-w-[305px] max-w-full">
                  <div data-testid="risk-daily-dd-bar" className="self-stretch flex items-start gap-[3px] mq750:flex-wrap">
                    {Array.from({ length: 10 }, (_, i) => {
                      const filledSegments = Math.round(dailyDdUsedPct / 10);
                      const filled = i < filledSegments;
                      return (
                        <div
                          key={i}
                          className={`h-[15.3px] w-[42.7px] relative border-solid border box-border ${filled ? "bg-[#ff8800] border-[#ff8800]" : "bg-[rgba(226,232,240,0.08)] border-[rgba(226,232,240,0.12)]"}`}
                        />
                      );
                    })}
                  </div>
                </div>
                <div data-testid="risk-daily-dd-percent" className="relative leading-[18.4px] text-[#3b82f6] text-center">
                  {formatPercent(dailyDdUsedPct)}
                </div>
              </div>
              <div className="max-w-full flex items-start justify-between gap-5 max-w-full text-[10.7px] text-[rgba(226,232,240,0.35)] mq450:flex-wrap mq450:gap-5">
                <div className="relative leading-[16.1px]">
                  {`Used: ${formatCurrency(dailyDdUsed)} / ${formatCurrency(dailyDdLimit)}`}
                </div>
                <div className="relative leading-[16.1px]">
                  {`Floor: ${formatCurrency(currentBalance - dailyDdLimit)}`}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Payout Target section */}
      <div className="self-stretch flex items-start justify-end py-0 pl-[13px] pr-3 box-border max-w-full shrink-0">
        <div className="flex-1 border-[rgba(46,78,89,0.5)] border-solid border-t box-border flex flex-col items-start pt-[7px] px-0 pb-[0.1px] gap-[5.4px] max-w-full">
          <div className="relative tracking-[1.61px] leading-[16.1px] uppercase">
            Payout Target
          </div>
          <div className="self-stretch bg-[#08100f] border-[#2e4e59] border-solid border box-border flex flex-col items-start pt-1.5 pb-[5px] pl-2.5 pr-2 gap-[4.3px] min-h-[73px] text-[12.3px] text-[rgba(226,232,240,0.6)]">
            <div className="self-stretch flex items-start justify-between gap-5 mq450:flex-wrap mq450:gap-5">
              <div className="flex flex-col items-start pt-[1.2px] px-0 pb-0">
                <div className="relative leading-[18.4px]">
                  <span>{`TARGET: ${formatCurrency(profitTarget)} — REMAINING: `}</span>
                  <span data-testid="risk-payout-remaining" className="text-[#fbbf24]">{formatCurrency(remaining)}</span>
                </div>
              </div>
              <div className="relative text-[13.8px] leading-[20.7px] text-[#0faf7a]">
                {formatPercent(targetPct)}
              </div>
            </div>
            <div data-testid="risk-payout-target-bar" className="self-stretch bg-[rgba(226,232,240,0.06)] border-[rgba(226,232,240,0.1)] border-solid border overflow-hidden flex items-start py-0 px-px">
              <div className="h-[9.6px] relative [background:linear-gradient(90deg,_#0faf7a,_#34d399)]" style={{ width: `${targetPct}%` }} />
            </div>
            <div className="self-stretch flex items-start justify-between gap-5 text-[10.7px] text-[rgba(226,232,240,0.35)] mq450:flex-wrap mq450:gap-5">
              <div className="relative leading-[16.1px] mq450:w-full mq450:h-[13px]">
                $0
              </div>
              <div className="relative leading-[16.1px] text-[#fbbf24]">
                {remaining > 0 ? `~${formatCurrency(remaining)} to go` : "Target reached!"}
              </div>
              <div className="relative leading-[16.1px]">{formatCurrency(profitTarget)}</div>
            </div>
          </div>
        </div>
      </div>

      {/* Day Stats section */}
      <div className="self-stretch flex items-start justify-end py-0 pl-[13px] pr-3 box-border max-w-full shrink-0 text-[rgba(226,232,240,0.45)]">
        <div className="flex-1 border-[rgba(46,78,89,0.5)] border-solid border-t box-border flex items-start pt-[7px] px-0 pb-0 max-w-full">
          <div className="w-[580.9px] flex items-end py-0 pl-0 pr-5 box-border gap-[33.4px] max-w-full mq750:gap-[17px] mq750:flex-wrap">
            <div className="flex-1 flex flex-col items-start gap-[5.2px] min-w-[140px] text-[rgba(15,175,122,0.7)]">
              <div className="relative tracking-[1.61px] leading-[16.1px] uppercase">
                Day Stats
              </div>
              <div className="self-stretch flex flex-col items-start gap-[0.8px] text-[rgba(226,232,240,0.45)]">
                <div className="self-stretch flex items-start justify-between gap-5">
                  <div className="relative tracking-[0.54px] leading-[16.1px] uppercase">{`Day P&L`}</div>
                  <div className="relative tracking-[0.54px] leading-[16.1px] uppercase">
                    Profit Factor
                  </div>
                </div>
                <div className="w-[134.5px] flex items-start justify-between pt-0 px-0 pb-[5.1px] box-border gap-5 text-[15.3px]">
                  <div data-testid="risk-day-pnl" className={`relative leading-[23px] ${(dailyTradeStats?.total_pnl ?? capitalSilo?.daily_pnl ?? 0) >= 0 ? "text-[#0faf7a]" : "text-[#ff0040]"}`}>{formatCurrency(dailyTradeStats?.total_pnl ?? capitalSilo?.daily_pnl ?? 0, { showSign: true })}</div>
                  <div data-testid="risk-profit-factor" className="relative leading-[23px] text-[#e2e8f0]">
                    {dailyTradeStats?.profit_factor ?? "—"}
                  </div>
                </div>
                <div className="w-[180.5px] flex items-start justify-between gap-5">
                  <div className="relative tracking-[0.54px] leading-[16.1px] uppercase">
                    Avg Win
                  </div>
                  <div className="relative tracking-[0.54px] leading-[16.1px] uppercase">
                    Avg Loss
                  </div>
                </div>
                <div className="w-[170.5px] flex items-start justify-between gap-5 text-[15.3px]">
                  <div className="relative leading-[23px] text-[#0faf7a]">{dailyTradeStats?.avg_win != null ? formatCurrency(dailyTradeStats.avg_win) : "$0.00"}</div>
                  <div className="relative leading-[23px] text-[#ff0040] text-center">
                    {dailyTradeStats?.avg_loss != null ? formatCurrency(dailyTradeStats.avg_loss) : "$0.00"}
                  </div>
                </div>
              </div>
            </div>
            <div className="w-[91.1px] flex flex-col items-start py-0 pl-0 pr-5 box-border gap-[0.8px]">
              <div className="relative tracking-[0.54px] leading-[16.1px] uppercase">
                Wins
              </div>
              <div className="flex items-start pt-0 px-0 pb-[5.1px] text-center text-[15.3px] text-[#0faf7a]">
                <div data-testid="risk-wins" className="relative leading-[23px]">{dailyTradeStats?.wins ?? 0}</div>
              </div>
              <div className="relative tracking-[0.54px] leading-[16.1px] uppercase">
                R:R Ratio
              </div>
              <div className="relative text-[15.3px] leading-[23px] text-[#e2e8f0]">
                {dailyTradeStats?.avg_win && dailyTradeStats?.avg_loss ? (dailyTradeStats.avg_win / dailyTradeStats.avg_loss).toFixed(1) : "—"}
              </div>
            </div>
            <div className="flex flex-col items-start py-0 pl-0 pr-[49px] gap-[5.9px]">
              <div className="flex flex-col items-start gap-[0.8px]">
                <div className="relative tracking-[0.54px] leading-[16.1px] uppercase">
                  Losses
                </div>
                <div data-testid="risk-losses" className="relative text-[15.3px] leading-[23px] text-[#ff0040] text-center">
                  {dailyTradeStats?.losses ?? 0}
                </div>
              </div>
              <div className="flex flex-col items-start gap-[0.8px]">
                <div className="relative tracking-[0.54px] leading-[16.1px] uppercase">
                  Trades
                </div>
                <div data-testid="risk-trades" className="relative text-[15.3px] leading-[23px] text-[#e2e8f0] text-center">
                  {dailyTradeStats?.trades_today ?? 0}
                </div>
              </div>
            </div>
            <div className="flex flex-col items-start gap-[0.8px]">
              <div className="relative tracking-[0.54px] leading-[16.1px] uppercase">
                Win%
              </div>
              <div className="flex items-start pt-0 px-0 pb-[5.1px] text-[15.3px] text-[#e2e8f0]">
                <div data-testid="risk-win-pct" className="relative leading-[23px]">{dailyTradeStats?.win_pct != null ? `${dailyTradeStats.win_pct}%` : "—"}</div>
              </div>
              <div className="relative tracking-[0.54px] leading-[16.1px] uppercase">
                Net Ticks
              </div>
              <div className="relative text-[15.3px] leading-[23px] text-[#e2e8f0] text-center">
                &mdash;
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Payout Info section */}
      <div className="flex items-start justify-end py-0 pl-[13px] pr-3 box-border max-w-full shrink-0">
        <div className="border-[rgba(46,78,89,0.5)] border-solid border-t box-border flex flex-col items-start pt-[7px] px-0 pb-0 gap-[5.4px] max-w-full">
          <div className="relative tracking-[1.61px] leading-[16.1px] uppercase">
            Payout Info
          </div>
          <div className="w-full flex items-start flex-wrap content-start gap-x-[6.1px] gap-y-[4.6px] text-[rgba(226,232,240,0.45)]">
            <div className="w-[201px] flex flex-col items-start pt-[17.6px] px-0 pb-0 box-border gap-[0.8px]">
              <div className="mt-[-17.8px] relative tracking-[0.54px] leading-[16.1px] uppercase shrink-0">
                Payout ID
              </div>
              <div className="relative text-[15.3px] leading-[23px] text-[#e2e8f0] shrink-0">
                {payout?.payout_id ?? tsm?.account_id ?? "—"}
              </div>
            </div>
            <div className="w-[201px] flex flex-col items-start pt-[17.6px] px-0 pb-0 box-border gap-[0.8px]">
              <div className="mt-[-17.8px] relative tracking-[0.54px] leading-[16.1px] uppercase shrink-0">
                Status
              </div>
              <div className="relative text-[15.3px] leading-[23px] text-[#e2e8f0] text-center shrink-0">
                {payout?.status ?? "—"}
              </div>
            </div>
            <div className="w-[201px] flex flex-col items-start pt-[17.6px] px-0 pb-0 box-border gap-[0.8px]">
              <div className="mt-[-17.8px] relative tracking-[0.54px] leading-[16.1px] uppercase shrink-0">
                Amount
              </div>
              <div className="relative text-[15.3px] leading-[23px] text-[#e2e8f0] text-center shrink-0">
                {formatCurrency(payout?.amount ?? 0)}
              </div>
            </div>
            <div className="w-[201px] flex flex-col items-start pt-[17.6px] px-0 pb-0 box-border gap-[0.9px]">
              <div className="mt-[-17.9px] relative tracking-[0.54px] leading-[16.1px] uppercase shrink-0">
                Tier
              </div>
              <div className="relative text-[15.3px] leading-[23px] text-[#e2e8f0] shrink-0">
                {payout?.tier ?? "Unknown"}
              </div>
            </div>
            <div className="w-[201px] flex flex-col items-start pt-[17.6px] px-0 pb-0 box-border gap-[0.9px]">
              <div className="mt-[-17.9px] relative tracking-[0.54px] leading-[16.1px] uppercase shrink-0">
                Method
              </div>
              <div className="relative text-[15.3px] leading-[23px] text-[#e2e8f0] text-center shrink-0">
                {payout?.method ?? "Systematic"}
              </div>
            </div>
            <div className="w-[201px] flex flex-col items-start pt-[17.6px] px-0 pb-0 box-border gap-[0.9px]">
              <div className="mt-[-17.9px] relative tracking-[0.54px] leading-[16.1px] uppercase shrink-0">
                Next Eligible
              </div>
              <div className="relative text-[15.3px] leading-[23px] text-[#e2e8f0] shrink-0">
                {payout?.next_eligible_date ?? "TBD"}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Accounts section */}
      <div className="self-stretch flex items-start justify-end py-0 pl-[13px] pr-3 box-border max-w-full shrink-0 text-[13.8px]">
        <div className="flex-1 border-[rgba(46,78,89,0.5)] border-solid border-t box-border flex flex-col items-start pt-[7px] px-0 pb-0 gap-[4.1px] max-w-full">
          <div className="relative text-[10.7px] tracking-[1.61px] leading-[16.1px] uppercase shrink-0">
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
                <div className="flex items-start gap-[8.3px]">
                  <div className="relative leading-[20.7px] shrink-0">
                    {formatCurrency(balance)}
                  </div>
                  <div
                    className={`border-solid border flex items-start py-0 pl-[5px] pr-1 shrink-0 text-[10.7px] ${
                      isActive
                        ? "bg-[#11300b] border-[#55d869] text-[#0faf7a]"
                        : "bg-[#1a0000] border-[#c10000] text-[#c10000]"
                    }`}
                  >
                    <div data-testid="risk-account-status" className="relative leading-[16.1px]">
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
        <div className="flex-1 border-[rgba(46,78,89,0.5)] border-solid border-t box-border flex flex-col items-start pt-[7px] px-0 pb-0 gap-[5.5px] max-w-full">
          <div className="relative tracking-[1.61px] leading-[16.1px] uppercase shrink-0">
            Risk Parameters
          </div>
          <div className="self-stretch flex items-start gap-[6.1px] shrink-0 text-[rgba(226,232,240,0.45)] mq750:flex-wrap">
            <div className="flex-1 flex flex-col items-start pt-[17.5px] px-0 pb-[0.1px] box-border gap-[0.8px] min-w-[112px] max-w-[149px]">
              <div className="mt-[-17.8px] relative tracking-[0.54px] leading-[16.1px] uppercase shrink-0">
                Max DD
              </div>
              <div data-testid="risk-max-dd-param" className="relative text-[15.3px] leading-[23px] text-[#ff8800] shrink-0">
                {formatCurrency(mddLimit)}
              </div>
            </div>
            <div className="flex-1 flex flex-col items-start pt-[17.5px] px-0 pb-[0.1px] box-border gap-[0.8px] min-w-[112px] max-w-[149px]">
              <div className="mt-[-17.8px] relative tracking-[0.54px] leading-[16.1px] uppercase shrink-0">
                Daily DD
              </div>
              <div data-testid="risk-daily-dd-param" className="relative text-[15.3px] leading-[23px] text-[#3b82f6] text-center shrink-0">
                {formatCurrency(dailyDdLimit)}
              </div>
            </div>
            <div className="flex-1 flex flex-col items-start pt-[17.5px] px-0 pb-[0.1px] box-border gap-[0.8px] min-w-[112px] max-w-[149px]">
              <div className="mt-[-17.8px] relative tracking-[0.54px] leading-[16.1px] uppercase shrink-0">
                Max Lots
              </div>
              <div data-testid="risk-max-lots-param" className="relative text-[15.3px] leading-[23px] text-[#e2e8f0] shrink-0">
                {tsm?.max_lots ?? "—"}
              </div>
            </div>
            <div className="flex-1 flex flex-col items-start pt-[17.5px] px-0 pb-[0.1px] box-border gap-[0.8px] min-w-[112px] max-w-[149px]">
              <div className="mt-[-17.8px] relative tracking-[0.54px] leading-[16.1px] uppercase shrink-0">
                Consistency
              </div>
              <div className="relative text-[15.3px] leading-[23px] text-[#e2e8f0] shrink-0">
                {tsm?.consistency_score != null ? formatPercent(tsm.consistency_score) : "—"}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="self-stretch h-[22px] flex items-start justify-end py-0 pl-[13px] pr-3 box-border max-w-full shrink-0 text-[rgba(226,232,240,0.25)]">
        <div className="self-stretch flex-1 border-[rgba(46,78,89,0.3)] border-solid border-t box-border overflow-x-auto flex items-start justify-between pt-0.5 px-0 pb-[1.6px] gap-5 max-w-full">
          <div className="relative leading-[16.1px]">SYS:RISK_MGR v2.4.1</div>
          <div className="relative leading-[16.1px]">PROP:150K_CHALLENGE</div>
          <div className="relative leading-[16.1px]">{timestamp ? `UPD: ${new Date(timestamp).toLocaleTimeString("en-US", { hour12: false, timeZone: "UTC" })}` : "UPD: —"}</div>
        </div>
      </div>
    </div>
  );
};

RiskPanel.propTypes = {
  className: PropTypes.string,
};

export default RiskPanel;
