***PHASE-A***
-- D08 starting_balance
SELECT count(*) total_rows, count(starting_balance) non_null, MIN(starting_balance) min_val, MAX(starting_balance) max_val, MAX(ABS(starting_balance)) max_abs, sum(case when starting_balance != starting_balance then 1 else 0 end) nan_count FROM p3_d08_tsm_state;

-- D08 current_balance
SELECT count(*) total_rows, count(current_balance) non_null, MIN(current_balance) min_val, MAX(current_balance) max_val, MAX(ABS(current_balance)) max_abs, sum(case when current_balance != current_balance then 1 else 0 end) nan_count FROM p3_d08_tsm_state;

-- D08 current_drawdown
SELECT count(*) total_rows, count(current_drawdown) non_null, MIN(current_drawdown) min_val, MAX(current_drawdown) max_val, MAX(ABS(current_drawdown)) max_abs, sum(case when current_drawdown != current_drawdown then 1 else 0 end) nan_count FROM p3_d08_tsm_state;

-- D08 daily_loss_used
SELECT count(*) total_rows, count(daily_loss_used) non_null, MIN(daily_loss_used) min_val, MAX(daily_loss_used) max_val, MAX(ABS(daily_loss_used)) max_abs, sum(case when daily_loss_used != daily_loss_used then 1 else 0 end) nan_count FROM p3_d08_tsm_state;

-- D08 profit_target
SELECT count(*) total_rows, count(profit_target) non_null, MIN(profit_target) min_val, MAX(profit_target) max_val, MAX(ABS(profit_target)) max_abs, sum(case when profit_target != profit_target then 1 else 0 end) nan_count FROM p3_d08_tsm_state;

-- D08 max_drawdown_limit
SELECT count(*) total_rows, count(max_drawdown_limit) non_null, MIN(max_drawdown_limit) min_val, MAX(max_drawdown_limit) max_val, MAX(ABS(max_drawdown_limit)) max_abs, sum(case when max_drawdown_limit != max_drawdown_limit then 1 else 0 end) nan_count FROM p3_d08_tsm_state;

-- D08 max_daily_loss
SELECT count(*) total_rows, count(max_daily_loss) non_null, MIN(max_daily_loss) min_val, MAX(max_daily_loss) max_val, MAX(ABS(max_daily_loss)) max_abs, sum(case when max_daily_loss != max_daily_loss then 1 else 0 end) nan_count FROM p3_d08_tsm_state;

-- D08 commission_per_contract
SELECT count(*) total_rows, count(commission_per_contract) non_null, MIN(commission_per_contract) min_val, MAX(commission_per_contract) max_val, MAX(ABS(commission_per_contract)) max_abs, sum(case when commission_per_contract != commission_per_contract then 1 else 0 end) nan_count FROM p3_d08_tsm_state;

-- D08 margin_per_contract
SELECT count(*) total_rows, count(margin_per_contract) non_null, MIN(margin_per_contract) min_val, MAX(margin_per_contract) max_val, MAX(ABS(margin_per_contract)) max_abs, sum(case when margin_per_contract != margin_per_contract then 1 else 0 end) nan_count FROM p3_d08_tsm_state;

-- D23 l_t
SELECT count(*) total_rows, count(l_t) non_null, MIN(l_t) min_val, MAX(l_t) max_val, MAX(ABS(l_t)) max_abs, sum(case when l_t != l_t then 1 else 0 end) nan_count FROM p3_d23_circuit_breaker_intraday;

-- D25 l_star
SELECT count(*) total_rows, count(l_star) non_null, MIN(l_star) min_val, MAX(l_star) max_val, MAX(ABS(l_star)) max_abs, sum(case when l_star != l_star then 1 else 0 end) nan_count FROM p3_d25_circuit_breaker_params;

-- D28 balance_at_event
SELECT count(*) total_rows, count(balance_at_event) non_null, MIN(balance_at_event) min_val, MAX(balance_at_event) max_val, MAX(ABS(balance_at_event)) max_abs, sum(case when balance_at_event != balance_at_event then 1 else 0 end) nan_count FROM p3_d28_account_lifecycle;

-- D28 fee_charged
SELECT count(*) total_rows, count(fee_charged) non_null, MIN(fee_charged) min_val, MAX(fee_charged) max_val, MAX(ABS(fee_charged)) max_abs, sum(case when fee_charged != fee_charged then 1 else 0 end) nan_count FROM p3_d28_account_lifecycle;

-- D28 payout_amount
SELECT count(*) total_rows, count(payout_amount) non_null, MIN(payout_amount) min_val, MAX(payout_amount) max_val, MAX(ABS(payout_amount)) max_abs, sum(case when payout_amount != payout_amount then 1 else 0 end) nan_count FROM p3_d28_account_lifecycle;

-- D28 payout_net
SELECT count(*) total_rows, count(payout_net) non_null, MIN(payout_net) min_val, MAX(payout_net) max_val, MAX(ABS(payout_net)) max_abs, sum(case when payout_net != payout_net then 1 else 0 end) nan_count FROM p3_d28_account_lifecycle;

-- D28 tradable_balance
SELECT count(*) total_rows, count(tradable_balance) non_null, MIN(tradable_balance) min_val, MAX(tradable_balance) max_val, MAX(ABS(tradable_balance)) max_abs, sum(case when tradable_balance != tradable_balance then 1 else 0 end) nan_count FROM p3_d28_account_lifecycle;

-- D28 reserve_balance
SELECT count(*) total_rows, count(reserve_balance) non_null, MIN(reserve_balance) min_val, MAX(reserve_balance) max_val, MAX(ABS(reserve_balance)) max_abs, sum(case when reserve_balance != reserve_balance then 1 else 0 end) nan_count FROM p3_d28_account_lifecycle;

| total_rows | non_null | min_val | max_val | max_abs | nan_count |
| ---------- | -------- | ------- | ------- | ------- | --------- |
| 0          | 0        | null    | null    | null    | null      |


***PHASE-B***
-- D03 entry_price (target DECIMAL(14, 4); max_abs must be < 1e10)
SELECT count(*) total_rows, count(entry_price) non_null, MIN(entry_price) min_val, MAX(entry_price) max_val, MAX(ABS(entry_price)) max_abs, sum(case when entry_price != entry_price then 1 else 0 end) nan_count FROM p3_d03_trade_outcome_log;

-- D03 signal_entry_price (target DECIMAL(14, 4))
SELECT count(*) total_rows, count(signal_entry_price) non_null, MIN(signal_entry_price) min_val, MAX(signal_entry_price) max_val, MAX(ABS(signal_entry_price)) max_abs, sum(case when signal_entry_price != signal_entry_price then 1 else 0 end) nan_count FROM p3_d03_trade_outcome_log;

-- D03 exit_price (target DECIMAL(14, 4))
SELECT count(*) total_rows, count(exit_price) non_null, MIN(exit_price) min_val, MAX(exit_price) max_val, MAX(ABS(exit_price)) max_abs, sum(case when exit_price != exit_price then 1 else 0 end) nan_count FROM p3_d03_trade_outcome_log;

-- D03 gross_pnl (target DECIMAL(18, 4); max_abs must be < 1e14)
SELECT count(*) total_rows, count(gross_pnl) non_null, MIN(gross_pnl) min_val, MAX(gross_pnl) max_val, MAX(ABS(gross_pnl)) max_abs, sum(case when gross_pnl != gross_pnl then 1 else 0 end) nan_count FROM p3_d03_trade_outcome_log;

-- D03 commission (target DECIMAL(18, 4))
SELECT count(*) total_rows, count(commission) non_null, MIN(commission) min_val, MAX(commission) max_val, MAX(ABS(commission)) max_abs, sum(case when commission != commission then 1 else 0 end) nan_count FROM p3_d03_trade_outcome_log;

-- D03 pnl (target DECIMAL(18, 4))
SELECT count(*) total_rows, count(pnl) non_null, MIN(pnl) min_val, MAX(pnl) max_val, MAX(ABS(pnl)) max_abs, sum(case when pnl != pnl then 1 else 0 end) nan_count FROM p3_d03_trade_outcome_log;

-- D03 slippage (target DECIMAL(18, 4))
SELECT count(*) total_rows, count(slippage) non_null, MIN(slippage) min_val, MAX(slippage) max_val, MAX(ABS(slippage)) max_abs, sum(case when slippage != slippage then 1 else 0 end) nan_count FROM p3_d03_trade_outcome_log;

| total_rows | non_null | min_val | max_val | max_abs | nan_count |
| ---------- | -------- | ------- | ------- | ------- | --------- |
| 9          | 9        | -787.5  | 3150.0  | 3150.0  | 0         |


***PHASE-C***

-- D16 starting_capital (target DECIMAL(18, 2))
SELECT count(*) total_rows, count(starting_capital) non_null, MIN(starting_capital) min_val, MAX(starting_capital) max_val, MAX(ABS(starting_capital)) max_abs, sum(case when starting_capital != starting_capital then 1 else 0 end) nan_count FROM p3_d16_user_capital_silos;

-- D16 total_capital (target DECIMAL(18, 2))
SELECT count(*) total_rows, count(total_capital) non_null, MIN(total_capital) min_val, MAX(total_capital) max_val, MAX(ABS(total_capital)) max_abs, sum(case when total_capital != total_capital then 1 else 0 end) nan_count FROM p3_d16_user_capital_silos;

-- D00 point_value (target DECIMAL(14, 4); max_abs must be < 1e10)
SELECT count(*) total_rows, count(point_value) non_null, MIN(point_value) min_val, MAX(point_value) max_val, MAX(ABS(point_value)) max_abs, sum(case when point_value != point_value then 1 else 0 end) nan_count FROM p3_d00_asset_universe;

-- D00 tick_size (target DECIMAL(14, 4))
SELECT count(*) total_rows, count(tick_size) non_null, MIN(tick_size) min_val, MAX(tick_size) max_val, MAX(ABS(tick_size)) max_abs, sum(case when tick_size != tick_size then 1 else 0 end) nan_count FROM p3_d00_asset_universe;

-- D00 margin_per_contract (target DECIMAL(14, 4))
SELECT count(*) total_rows, count(margin_per_contract) non_null, MIN(margin_per_contract) min_val, MAX(margin_per_contract) max_val, MAX(ABS(margin_per_contract)) max_abs, sum(case when margin_per_contract != margin_per_contract then 1 else 0 end) nan_count FROM p3_d00_asset_universe;

-- D30 open (target DECIMAL(14, 4))
SELECT count(*) total_rows, count(open) non_null, MIN(open) min_val, MAX(open) max_val, MAX(ABS(open)) max_abs, sum(case when open != open then 1 else 0 end) nan_count FROM p3_d30_daily_ohlcv;

-- D30 high (target DECIMAL(14, 4))
SELECT count(*) total_rows, count(high) non_null, MIN(high) min_val, MAX(high) max_val, MAX(ABS(high)) max_abs, sum(case when high != high then 1 else 0 end) nan_count FROM p3_d30_daily_ohlcv;

-- D30 low (target DECIMAL(14, 4))
SELECT count(*) total_rows, count(low) non_null, MIN(low) min_val, MAX(low) max_val, MAX(ABS(low)) max_abs, sum(case when low != low then 1 else 0 end) nan_count FROM p3_d30_daily_ohlcv;

-- D30 close (target DECIMAL(14, 4))
SELECT count(*) total_rows, count(close) non_null, MIN(close) min_val, MAX(close) max_val, MAX(ABS(close)) max_abs, sum(case when close != close then 1 else 0 end) nan_count FROM p3_d30_daily_ohlcv;

| total_rows | non_null | min_val    | max_val      | max_abs      | nan_count |
| ---------- | -------- | ---------- | ------------ | ------------ | --------- |
| 14152      | 14152    | 108.995596 | 60080.926401 | 60080.926401 | 0         |

section 3: pre-migration-snapshot
SELECT 'p3_d08_tsm_state' as table_name, count(*) row_count FROM p3_d08_tsm_state
UNION ALL SELECT 'p3_d23_circuit_breaker_intraday', count(*) FROM p3_d23_circuit_breaker_intraday
UNION ALL SELECT 'p3_d25_circuit_breaker_params', count(*) FROM p3_d25_circuit_breaker_params
UNION ALL SELECT 'p3_d28_account_lifecycle', count(*) FROM p3_d28_account_lifecycle
UNION ALL SELECT 'p3_d03_trade_outcome_log', count(*) FROM p3_d03_trade_outcome_log
UNION ALL SELECT 'p3_d16_user_capital_silos', count(*) FROM p3_d16_user_capital_silos
UNION ALL SELECT 'p3_d00_asset_universe', count(*) FROM p3_d00_asset_universe
UNION ALL SELECT 'p3_d30_daily_ohlcv', count(*) FROM p3_d30_daily_ohlcv;

| table_name                      | row_count |
| ------------------------------- | --------- |
| p3_d08_tsm_state                | 11        |
| p3_d23_circuit_breaker_intraday | 18        |
| p3_d25_circuit_breaker_params   | 2         |
| p3_d28_account_lifecycle        | 0         |
| p3_d03_trade_outcome_log        | 9         |
| p3_d16_user_capital_silos       | 13        |
| p3_d00_asset_universe           | 2442295   |
| p3_d30_daily_ohlcv              | 14152     |


section 4 post-migration-verification

