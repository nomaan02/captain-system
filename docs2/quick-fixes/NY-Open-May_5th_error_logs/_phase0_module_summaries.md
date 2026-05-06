# Phase 0A — Module Summaries (Decimal Boundary remediation)

## 1. `shared/questdb_client.py` — current state

### `_decimal_to_cast_sql` (verbatim, file lines 36–59)

```36:59:shared/questdb_client.py
def _decimal_to_cast_sql(d: Decimal) -> str:
    """Render a Decimal as `cast('<value>' as DECIMAL(<p>, <s>))`.

    The precision/scale are derived from the Decimal's own digits so the
    cast expression always fits the value.  QuestDB then widens or
    narrows at column-assignment time as needed.
    """
    s = format(d, "f")  # expand any scientific notation: 5E-7 -> '0.0000005'
    sign = ""
    if s.startswith("-"):
        sign, s = "-", s[1:]
    if "." in s:
        int_part, frac_part = s.split(".", 1)
        scale = len(frac_part)
    else:
        int_part = s
        scale = 0
    int_digits = max(len(int_part.lstrip("0")), 1)
    precision = int_digits + scale
    if precision > 38:  # QuestDB DECIMAL precision cap
        precision = 38
        if scale > precision:
            scale = precision
    return f"cast('{sign}{s}' as DECIMAL({precision}, {scale}))"
```

**Precision/scale derivation:** `format(d, "f")` expands scientific notation; optional leading `-` is stripped for digit math then re-applied; if there is a fractional part, `scale = len(frac_part)`, else `scale = 0`; `int_digits = max(len(int_part.lstrip("0")), 1)`; `precision = int_digits + scale`; cap `precision` at 38 and clamp `scale` if needed; return SQL literal `cast('<signed string>' as DECIMAL(precision, scale))`.

### Two `register_adapter` calls (verbatim, lines 62–71)

```62:71:shared/questdb_client.py
psycopg2.extensions.register_adapter(
    Decimal,
    lambda d: psycopg2.extensions.AsIs(_decimal_to_cast_sql(d)),
)

# QuestDB's PG wire doesn't handle psycopg2's binary boolean format.
# Send as SQL keyword literals instead.
psycopg2.extensions.register_adapter(
    bool, lambda b: psycopg2.extensions.AsIs("true" if b else "false")
)
```

Global effect: every `Decimal` bound through psycopg2 is emitted as that `cast(... AS DECIMAL(p,s))` string (structural driver of adapter/column mismatch bugs). Every `bool` is emitted as `true`/`false` SQL keywords.

### `get_connection` and `get_cursor` flow

- **`get_connection()` (149–168):** thread-local `_local.conn`; if cached, runs `SELECT 1`; on success returns it; on failure closes (best effort), clears cache, creates new via `_connect()`. `_connect()` (88–122) calls `psycopg2.connect` with env-derived host/port/user/password/db, `connect_timeout=5`, sets `autocommit=True`, retries up to 3 times with delays 1s/2s/4s.
- **`get_cursor()` (171–186):** context manager: `conn = get_connection()`, `cur = conn.cursor()`, `yield cur`; on exception closes connection and clears `_local.conn`, then re-raises.

### `D00_COLUMNS` (exact ordered list, lines 194–200)

`asset_id`, `p1_status`, `p2_status`, `captain_status`, `warm_up_progress`, `aim_warmup_progress`, `locked_strategy`, `roll_calendar`, `exchange_timezone`, `point_value`, `tick_size`, `margin_per_contract`, `session_hours`, `session_schedule`, `p1_data_path`, `p2_data_path`, `data_sources`, `data_quality_flag`

### `read_d00_row` and `update_d00_fields`

- **`read_d00_row(asset_id, cur=None)` (203–223):** `SELECT` + `", ".join(D00_COLUMNS)` from `p3_d00_asset_universe` with `WHERE asset_id = %s LATEST ON last_updated PARTITION BY asset_id`. If `cur` given, uses it; else `with get_cursor()`. Returns `dict(zip(D00_COLUMNS, row))` or `None`.
- **`update_d00_fields(asset_id, updates, cur=None)` (226–252):** Inner `_do(c)`: `read_d00_row`; if missing raises `ValueError`; `current.update(updates)`; `cols = D00_COLUMNS + ["last_updated"]`; `placeholders = ", ".join(["%s"] * len(D00_COLUMNS) + ["now()"])`; **`f"INSERT INTO p3_d00_asset_universe ({col_names}) VALUES ({placeholders})"`** with `tuple(current[k] for k in D00_COLUMNS)` — the lone dynamically built INSERT noted for Phase 3; column order follows `D00_COLUMNS` then `last_updated`.

### What MUST be preserved

- Module header comment (19–35): rationale for cast-based Decimal handling.
- `_decimal_to_cast_sql` lossless (p,s) from the Decimal's string form and 38 precision cap.
- Thread-local connection reuse with health check and discard-on-error.
- Exponential backoff on connect.
- `wait_for_questdb` behaviour.
- Boolean adapter as `true`/`false`.
- D00 read path and merge-then-reinsert semantics; explicit `columns=` override in Phase 3 must not break the dedup key `(last_updated, asset_id)` semantics from schema.

---

## 2. `shared/decimal_boundary.py` — current state

### Public API signatures (exact)

- `def as_money(value: Any, *, default: Decimal = ZERO) -> Decimal:` (line 33)
- `def as_money_or_none(value: Any) -> Decimal | None:` (line 53)
- `def to_float(value: Any, *, default: float = 0.0) -> float:` (line 72)
- `def assert_money_dict(d: dict, *money_fields: str, allow_none: tuple[str, ...] = (),) -> None:` (lines 93–97)
- Module-level `ZERO = Decimal("0")` (line 30)

### Anti-patterns in docstrings / module doc

- `Decimal('0.00') or 0.0 -> 0.0` (falsy-zero collapse)
- `Decimal(value)` with float input (inherits float bit pattern)
- Six private `_money*` helpers per file
- Type-mixed dicts (Decimal vs float) causing `TypeError` on arithmetic (NY/APAC open 2026-04-30 reference)

### Behaviour notes

- `as_money`: Decimal passthrough; `None` / `""` → `default`; else `Decimal(str(value))` with fallback to `default` on `InvalidOperation`, `TypeError`, `ValueError`.
- `as_money_or_none`: `None` / `""` → `None`; Decimal passthrough; else `Decimal(str(value))` or `None` on errors.
- `to_float`: `None` → `default`; Decimal → `float(value)`; else `float(value)` with `TypeError`/`ValueError` → `default`. Doc restricts use to sizing/statistical boundaries, not monetary state mutation.
- `assert_money_dict`: for each `money_fields`, value must be `Decimal` unless field in `allow_none` and value is `None`.

### What MUST be preserved

- `str(value)` / `Decimal(str(...))` conversion path for non-Decimal inputs (avoid float inheritance).
- `as_money` never returns float/int/None.
- `as_money_or_none` preserves NULL semantics; zero Decimal not coerced to None.
- `to_float` as explicit, documented escape hatch with None-safety.
- Semantics of `assert_money_dict` for tests.

---

## 3. `shared/decimal_json.py` and `shared/json_helpers.py` — current state

### `DecimalJSONEncoder` and `dumps_decimal`

- `DecimalJSONEncoder.default`: if `isinstance(obj, Decimal)`, return `str(obj)`; else `super().default(obj)` (lines 17–20).
- `dumps_decimal(obj)`: `json.dumps(obj, cls=DecimalJSONEncoder, default=str)` (lines 23–29). Doc: `default=str` matches prior behaviour for datetimes and non-JSON-native objects.

### `loads_decimal` and `_coerce`

- `loads_decimal(s: str, *, coerce_json_int: bool = True)` (lines 32–43): `parse_int = Decimal if coerce_json_int else int`; `data = json.loads(s, parse_float=Decimal, parse_int=parse_int)`.
- `_coerce` (lines 47–57): dict/list recursion; for **`str` leaves**, `try: return Decimal(obj)` except `InvalidOperation: return obj`. So **any** string leaf that parses as Decimal becomes Decimal (including non-monetary strings that are valid decimals — structural over-coercion risk).
- Returns `_coerce(data)` (line 59).

### `parse_json` vs `parse_json_decimal`

- `parse_json(raw, default)` (`json_helpers.py` 8–17): `None` → `default`; already dict/list → return as-is; else `json.loads(raw)` on str; on `JSONDecodeError`/`TypeError` → `default`. **No** Decimal coercion.
- `parse_json_decimal(raw, default)` (20–31): same guards; requires `str` for JSON path; `loads_decimal(raw)`; catches `JSONDecodeError`/`TypeError`/`ValueError` → `default`.

### What MUST be preserved (under backwards-compat shim)

- Wire payloads that currently rely on `dumps_decimal` + `loads_decimal` round-trip (Decimal as JSON string, floats parsed as Decimal when using default `coerce_json_int=True`).
- `coerce_json_int=False` path for Redis-style payloads where integers must stay `int`.
- `parse_json` unchanged semantics for non-monetary JSON.
- Phase 4: any new wire format needs a **legacy reader** that still accepts existing `loads_decimal` / string-numeric leaves behaviour until cutover is complete.

---

## 4. `shared/canonical_schemas.py` — column-type inventory

> Final type after applying every relevant `CANONICAL_MIGRATIONS` entry. M047 is DEDUP only (no column types).

### p3_d00_asset_universe

| column | type | source |
|--------|------|--------|
| asset_id | SYMBOL | DDL |
| p1_status | STRING | DDL |
| p2_status | STRING | DDL |
| captain_status | STRING | DDL |
| warm_up_progress | DOUBLE | DDL |
| aim_warmup_progress | STRING | DDL |
| locked_strategy | STRING | DDL |
| roll_calendar | STRING | DDL |
| exchange_timezone | STRING | DDL |
| point_value | DECIMAL(14, 6) | DDL + M036 |
| tick_size | DECIMAL(14, 8) | DDL + M037 |
| margin_per_contract | DECIMAL(14, 6) | DDL + M038 |
| session_hours | STRING | DDL |
| session_schedule | STRING | DDL |
| p1_data_path | STRING | DDL |
| p2_data_path | STRING | DDL |
| data_sources | STRING | DDL |
| data_quality_flag | STRING | DDL |
| created | TIMESTAMP | DDL |
| last_updated | TIMESTAMP | DDL |

### p3_d01_aim_model_states

| column | type | source |
|--------|------|--------|
| aim_id | INT | DDL |
| asset_id | SYMBOL | DDL |
| status | STRING | DDL |
| model_object | STRING | DDL |
| warmup_progress | DOUBLE | DDL |
| current_modifier | STRING | DDL |
| last_retrained | TIMESTAMP | DDL |
| missing_data_rate_30d | DOUBLE | DDL |
| last_updated | TIMESTAMP | DDL |

### p3_d02_aim_meta_weights

| column | type | source |
|--------|------|--------|
| aim_id | INT | DDL |
| asset_id | SYMBOL | DDL |
| inclusion_probability | DOUBLE | DDL |
| inclusion_flag | BOOLEAN | DDL |
| recent_effectiveness | DOUBLE | DDL |
| days_below_threshold | INT | DDL |
| last_updated | TIMESTAMP | DDL |

### p3_d04_decay_detector_states

| column | type | source |
|--------|------|--------|
| asset_id | SYMBOL | DDL |
| bocpd_run_length_posterior | STRING | DDL |
| bocpd_cp_probability | DOUBLE | DDL |
| bocpd_cp_history | STRING | DDL |
| cusum_c_up_prev | DOUBLE | DDL |
| cusum_c_down_prev | DOUBLE | DDL |
| cusum_sprint_length | INT | DDL |
| cusum_allowance | DOUBLE | DDL |
| cusum_sequential_limits | STRING | DDL |
| adwin_states | STRING | DDL |
| decay_events | STRING | DDL |
| current_changepoint_probability | DOUBLE | DDL |
| last_updated | TIMESTAMP | DDL |

### p3_d05_ewma_states

| column | type | source |
|--------|------|--------|
| asset_id | SYMBOL | DDL |
| regime | STRING | DDL |
| session | INT | DDL |
| win_rate | DOUBLE | DDL |
| avg_win | DOUBLE | DDL |
| avg_loss | DOUBLE | DDL |
| n_trades | INT | DDL |
| last_updated | TIMESTAMP | DDL |

### p3_d06b_active_transitions

| column | type | source |
|--------|------|--------|
| asset_id | SYMBOL | DDL |
| mode | STRING | DDL |
| new_strategy | STRING | DDL |
| old_strategy | STRING | DDL |
| current_day | INT | DDL |
| total_days | INT | DDL |
| completed | BOOLEAN | DDL |
| started_at | TIMESTAMP | DDL |
| last_updated | TIMESTAMP | DDL |

### p3_d07_correlation_model_states

| column | type | source |
|--------|------|--------|
| correlation_matrix | STRING | DDL |
| dcc_parameters | STRING | DDL |
| last_updated | TIMESTAMP | DDL |

### p2_d07_regime_models

| column | type | source |
|--------|------|--------|
| asset | SYMBOL | DDL |
| model_type | STRING | DDL |
| feature_list | STRING | DDL |
| pettersson_threshold | DOUBLE | DDL |
| regime_label | STRING | DDL |
| training_period | STRING | DDL |
| n_training_obs | INT | DDL |
| best_hyperparams | STRING | DDL |
| cv_score | DOUBLE | DDL |
| trained_at | TIMESTAMP | DDL |
| last_updated | TIMESTAMP | DDL |

### p3_d08_tsm_state

| column | type | source |
|--------|------|--------|
| account_id | SYMBOL | DDL |
| user_id | SYMBOL | DDL |
| name | STRING | DDL |
| classification | STRING | DDL |
| starting_balance | DECIMAL(18, 2) | DDL + M010 |
| current_balance | DECIMAL(18, 2) | DDL + M011 |
| current_drawdown | DECIMAL(18, 2) | DDL + M012 |
| daily_loss_used | DECIMAL(18, 2) | DDL + M013 |
| profit_target | DECIMAL(18, 2) | DDL + M014 |
| max_drawdown_limit | DECIMAL(18, 2) | DDL + M015 |
| max_daily_loss | DECIMAL(18, 2) | DDL + M016 |
| max_contracts | INT | DDL |
| scaling_plan | STRING | DDL |
| commission_per_contract | DECIMAL(18, 2) | DDL + M017 |
| instrument_permissions | STRING | DDL |
| overnight_allowed | BOOLEAN | DDL |
| trading_hours | STRING | DDL |
| margin_per_contract | DECIMAL(18, 2) | DDL + M018 |
| margin_buffer_pct | DOUBLE | DDL |
| pass_probability | DOUBLE | DDL |
| simulation_date | TIMESTAMP | DDL |
| risk_goal | STRING | DDL |
| evaluation_end_date | TIMESTAMP | DDL |
| evaluation_stages | STRING | DDL |
| topstep_optimisation | BOOLEAN | DDL |
| topstep_params | STRING | DDL |
| topstep_state | STRING | DDL |
| fee_schedule | STRING | DDL |
| payout_rules | STRING | DDL |
| scaling_plan_active | BOOLEAN | DDL |
| scaling_tier_micros | INT | DDL |
| last_updated | TIMESTAMP | DDL |

### p3_d12_kelly_parameters

| column | type | source |
|--------|------|--------|
| asset_id | SYMBOL | DDL |
| regime | STRING | DDL |
| session | INT | DDL |
| kelly_full | DOUBLE | DDL |
| shrinkage_factor | DOUBLE | DDL |
| sizing_override | STRING | DDL |
| last_updated | TIMESTAMP | DDL |

### p3_d13_sensitivity_scan_results

| column | type | source |
|--------|------|--------|
| asset_id | SYMBOL | DDL |
| sharpe_stability | DOUBLE | DDL |
| pbo | DOUBLE | DDL |
| dsr | DOUBLE | DDL |
| adjusted_sharpe | DOUBLE | DDL |
| robustness_status | STRING | DDL |
| flags | STRING | DDL |
| perturbation_grid_results | STRING | DDL |
| scan_date | TIMESTAMP | DDL |

### p3_d15_user_session_data

| column | type | source |
|--------|------|--------|
| user_id | SYMBOL | DDL |
| display_name | STRING | DDL |
| auth_token | STRING | DDL |
| role | STRING | DDL |
| tags | STRING | DDL |
| device_sessions | STRING | DDL |
| preferences | STRING | DDL |
| created | TIMESTAMP | DDL |
| last_active | TIMESTAMP | DDL |

### p3_d16_user_capital_silos

| column | type | source |
|--------|------|--------|
| user_id | SYMBOL | DDL |
| status | SYMBOL | DDL |
| role | SYMBOL | DDL |
| starting_capital | DECIMAL(18, 2) | DDL + M034 |
| total_capital | DECIMAL(18, 2) | DDL + M035 |
| accounts | STRING | DDL |
| max_simultaneous_positions | INT | DDL |
| max_portfolio_risk_pct | DOUBLE | DDL |
| correlation_threshold | DOUBLE | DDL |
| user_kelly_ceiling | DOUBLE | DDL |
| capital_history | STRING | DDL |
| telegram_chat_id | STRING | DDL |
| created | TIMESTAMP | DDL |
| last_updated | TIMESTAMP | DDL |

### p3_d17_system_monitor_state

| column | type | source |
|--------|------|--------|
| param_key | STRING | DDL |
| param_value | STRING | DDL |
| category | STRING | DDL |
| last_updated | TIMESTAMP | DDL |

### p3_d25_circuit_breaker_params

| column | type | source |
|--------|------|--------|
| account_id | SYMBOL | DDL |
| model_m | INT | DDL |
| r_bar | DOUBLE | DDL |
| beta_b | DOUBLE | DDL |
| sigma | DOUBLE | DDL |
| rho_bar | DOUBLE | DDL |
| n_observations | INT | DDL |
| p_value | DOUBLE | DDL |
| l_star | DECIMAL(18, 2) | DDL + M020 |
| cold_start | BOOLEAN | DDL |
| last_updated | TIMESTAMP | DDL |

### p3_d26_hmm_opportunity_state

| column | type | source |
|--------|------|--------|
| hmm_params | STRING | DDL |
| current_state_probs | STRING | DDL |
| opportunity_weights | STRING | DDL |
| prior_alpha | STRING | DDL |
| last_trained | TIMESTAMP | DDL |
| training_window | INT | DDL |
| n_observations | INT | DDL |
| cold_start | BOOLEAN | DDL |
| last_updated | TIMESTAMP | DDL |

### p3_d14_api_connection_states

| column | type | source |
|--------|------|--------|
| account_id | SYMBOL | DDL |
| adapter_type | STRING | DDL |
| connection_status | STRING | DDL |
| last_heartbeat | TIMESTAMP | DDL |
| latency_ms | DOUBLE | DDL |
| error_log | STRING | DDL |
| last_updated | TIMESTAMP | DDL |

### p3_d23_circuit_breaker_intraday

| column | type | source |
|--------|------|--------|
| account_id | SYMBOL | DDL |
| session_id | INT | DDL + M043 |
| l_t | DECIMAL(18, 2) | DDL + M019 |
| n_t | INT | DDL |
| l_b | STRING | DDL |
| n_b | STRING | DDL |
| effective_l_halt | DECIMAL(18, 2) | DDL + M044 |
| effective_e_exposure | DECIMAL(18, 2) | DDL + M045 |
| session_opened_at | TIMESTAMP | DDL + M046 |
| last_updated | TIMESTAMP | DDL |

### p3_d03_trade_outcome_log

| column | type | source |
|--------|------|--------|
| trade_id | STRING | DDL |
| signal_id | STRING | DDL + M002 |
| user_id | SYMBOL | DDL |
| account_id | SYMBOL | DDL |
| asset | SYMBOL | DDL |
| direction | INT | DDL |
| entry_price | DECIMAL(14, 6) | DDL + M027 |
| signal_entry_price | DECIMAL(14, 6) | DDL + M028 |
| exit_price | DECIMAL(14, 6) | DDL + M029 |
| contracts | INT | DDL |
| gross_pnl | DECIMAL(18, 4) | DDL + M030 |
| commission | DECIMAL(18, 4) | DDL + M031 |
| pnl | DECIMAL(18, 4) | DDL + M032 |
| slippage | DECIMAL(18, 4) | DDL + M033 |
| outcome | STRING | DDL |
| entry_time | TIMESTAMP | DDL |
| exit_time | TIMESTAMP | DDL |
| regime_at_entry | STRING | DDL |
| **aim_modifier_at_entry** | **DOUBLE** | **DDL — May 5 crash column** |
| aim_breakdown_at_entry | STRING | DDL |
| session | INT | DDL |
| tsm_used | STRING | DDL |
| model_m | INT | DDL + M001 |
| ts | TIMESTAMP | DDL |

### p3_d06_injection_history

| column | type | source |
|--------|------|--------|
| injection_id | STRING | DDL |
| asset | SYMBOL | DDL |
| candidate | STRING | DDL |
| current_strategy | STRING | DDL |
| expected_new | DOUBLE | DDL |
| expected_current | DOUBLE | DDL |
| pseudo_results | STRING | DDL |
| recommendation | STRING | DDL |
| status | STRING | DDL |
| injection_type | STRING | DDL |
| outcome | STRING | DDL |
| pbo | DOUBLE | DDL + M006 |
| dsr | DOUBLE | DDL + M007 |
| transition_days | INT | DDL + M008 |
| tracking_days | INT | DDL + M009 |
| ts | TIMESTAMP | DDL |

### p3_d09_report_archive

| column | type | source |
|--------|------|--------|
| report_id | STRING | DDL |
| report_type | STRING | DDL |
| generated_at | TIMESTAMP | DDL |
| content | STRING | DDL |
| user_id | SYMBOL | DDL |
| ts | TIMESTAMP | DDL |

### p3_d10_notification_log

| column | type | source |
|--------|------|--------|
| notification_id | STRING | DDL |
| user_id | SYMBOL | DDL |
| priority | STRING | DDL |
| event_type | STRING | DDL |
| asset | SYMBOL | DDL |
| message | STRING | DDL |
| action_required | BOOLEAN | DDL |
| gui_delivered | BOOLEAN | DDL |
| gui_read | BOOLEAN | DDL |
| gui_read_at | TIMESTAMP | DDL |
| telegram_delivered | BOOLEAN | DDL |
| telegram_read | BOOLEAN | DDL |
| email_delivered | BOOLEAN | DDL |
| user_response | STRING | DDL |
| response_at | TIMESTAMP | DDL |
| ts | TIMESTAMP | DDL |

### p3_d11_pseudotrader_results

| column | type | source |
|--------|------|--------|
| result_id | STRING | DDL |
| update_type | STRING | DDL |
| sharpe_baseline | DOUBLE | DDL + M003 |
| sharpe_updated | DOUBLE | DDL + M004 |
| sharpe_improvement | DOUBLE | DDL |
| drawdown_change | DOUBLE | DDL |
| winrate_delta | DOUBLE | DDL |
| pbo | DOUBLE | DDL |
| dsr | DOUBLE | DDL |
| recommendation | STRING | DDL |
| pair_series | STRING | DDL + M005 |
| ts | TIMESTAMP | DDL |

### p3_d18_version_history

| column | type | source |
|--------|------|--------|
| version_id | STRING | DDL |
| component | STRING | DDL |
| trigger | STRING | DDL |
| state | STRING | DDL |
| model_hash | STRING | DDL |
| ts | TIMESTAMP | DDL |

### p3_d19_reconciliation_log

| column | type | source |
|--------|------|--------|
| recon_id | STRING | DDL |
| account_id | SYMBOL | DDL |
| user_id | SYMBOL | DDL |
| source | STRING | DDL |
| mismatches | STRING | DDL |
| corrected | BOOLEAN | DDL |
| status | STRING | DDL |
| ts | TIMESTAMP | DDL |

### p3_d21_incident_log

| column | type | source |
|--------|------|--------|
| incident_id | STRING | DDL |
| incident_type | STRING | DDL |
| severity | STRING | DDL |
| component | STRING | DDL |
| details | STRING | DDL |
| affected_users | STRING | DDL |
| system_snapshot | STRING | DDL |
| status | STRING | DDL |
| resolution | STRING | DDL |
| root_cause | STRING | DDL |
| resolved_by | STRING | DDL |
| resolved_at | TIMESTAMP | DDL |
| timestamp | TIMESTAMP | DDL |

### p3_d22_system_health_diagnostic

| column | type | source |
|--------|------|--------|
| mode | STRING | DDL |
| scores | STRING | DDL |
| overall_health | DOUBLE | DDL |
| action_items_generated | INT | DDL |
| critical_count | INT | DDL |
| high_count | INT | DDL |
| queue_total | INT | DDL |
| open_count | INT | DDL |
| stale_count | INT | DDL |
| action_queue | STRING | DDL |
| ts | TIMESTAMP | DDL |

### p3_d22b_asset_rerun_status

| column | type | source |
|--------|------|--------|
| asset | SYMBOL | DDL |
| last_p1p2_rerun_ts | TIMESTAMP | DDL |
| rerun_trigger | STRING | DDL |
| last_updated | TIMESTAMP | DDL |

### p3_d27_pseudotrader_forecasts

| column | type | source |
|--------|------|--------|
| forecast_id | STRING | DDL |
| forecast_type | STRING | DDL |
| account_id | SYMBOL | DDL |
| version | STRING | DDL |
| run_date | STRING | DDL |
| window_start | STRING | DDL |
| window_end | STRING | DDL |
| metrics | STRING | DDL |
| equity_curve | STRING | DDL |
| system_state | STRING | DDL |
| ts | TIMESTAMP | DDL |

### p3_d28_account_lifecycle

| column | type | source |
|--------|------|--------|
| event_id | STRING | DDL |
| account_id | SYMBOL | DDL |
| user_id | SYMBOL | DDL |
| event_type | STRING | DDL |
| from_stage | STRING | DDL |
| to_stage | STRING | DDL |
| trigger | STRING | DDL |
| balance_at_event | DECIMAL(18, 2) | DDL + M021 |
| fee_charged | DECIMAL(18, 2) | DDL + M022 |
| payout_amount | DECIMAL(18, 2) | DDL + M023 |
| payout_net | DECIMAL(18, 2) | DDL + M024 |
| payouts_taken | INT | DDL |
| tradable_balance | DECIMAL(18, 2) | DDL + M025 |
| reserve_balance | DECIMAL(18, 2) | DDL + M026 |
| details | STRING | DDL |
| ts | TIMESTAMP | DDL |

### p3_d29_opening_volumes

| column | type | source |
|--------|------|--------|
| asset_id | SYMBOL | DDL |
| session_date | STRING | DDL |
| session_type | STRING | DDL |
| or_minutes | INT | DDL |
| volume_first_m_min | LONG | DDL |
| or_range_first_m_min | DOUBLE | DDL |
| ts | TIMESTAMP | DDL |

### p3_d30_daily_ohlcv

| column | type | source |
|--------|------|--------|
| asset_id | SYMBOL | DDL |
| trade_date | STRING | DDL |
| open | DECIMAL(14, 6) | DDL + M039 |
| high | DECIMAL(14, 6) | DDL + M040 |
| low | DECIMAL(14, 6) | DDL + M041 |
| close | DECIMAL(14, 6) | DDL + M042 |
| volume | LONG | DDL |
| ts | TIMESTAMP | DDL |

### p3_d31_implied_vol

| column | type | source |
|--------|------|--------|
| asset_id | SYMBOL | DDL |
| trade_date | TIMESTAMP | DDL |
| atm_iv_30d | DOUBLE | DDL |
| realized_vol_20d | DOUBLE | DDL |
| vrp | DOUBLE | DDL |
| ts | TIMESTAMP | DDL |

### p3_d32_options_skew

| column | type | source |
|--------|------|--------|
| asset_id | SYMBOL | DDL |
| trade_date | TIMESTAMP | DDL |
| cboe_skew | DOUBLE | DDL |
| skew_spread_proxy | DOUBLE | DDL |
| ts | TIMESTAMP | DDL |

### p3_d33_opening_volatility

| column | type | source |
|--------|------|--------|
| asset_id | SYMBOL | DDL |
| session_date | TIMESTAMP | DDL |
| session_type | SYMBOL | DDL |
| or_minutes | INT | DDL |
| opening_range_pct | DOUBLE | DDL |
| opening_vol_z | DOUBLE | DDL |
| ts | TIMESTAMP | DDL |

### p3_spread_history

| column | type | source |
|--------|------|--------|
| asset_id | SYMBOL | DDL |
| session_id | INT | DDL |
| spread | DOUBLE | DDL |
| timestamp | TIMESTAMP | DDL |

### p3_session_event_log

| column | type | source |
|--------|------|--------|
| user_id | SYMBOL | DDL |
| event_type | STRING | DDL |
| event_id | STRING | DDL |
| asset | SYMBOL | DDL |
| details | STRING | DDL |
| ts | TIMESTAMP | DDL |

### p3_replay_results

| column | type | source |
|--------|------|--------|
| replay_id | STRING | DDL |
| user_id | SYMBOL | DDL |
| replay_date | STRING | DDL |
| session_type | SYMBOL | DDL |
| config | STRING | DDL |
| results | STRING | DDL |
| summary | STRING | DDL |
| comparison | STRING | DDL |
| created | TIMESTAMP | DDL |
| ts | TIMESTAMP | DDL |

### p3_replay_presets

| column | type | source |
|--------|------|--------|
| preset_id | STRING | DDL |
| user_id | SYMBOL | DDL |
| name | STRING | DDL |
| config | STRING | DDL |
| ts | TIMESTAMP | DDL |

### p3_offline_job_queue

| column | type | source |
|--------|------|--------|
| job_id | STRING | DDL |
| job_type | STRING | DDL |
| asset_id | SYMBOL | DDL |
| priority | STRING | DDL |
| status | STRING | DDL |
| params | STRING | DDL |
| result | STRING | DDL |
| error | STRING | DDL |
| created_at | TIMESTAMP | DDL |
| started_at | TIMESTAMP | DDL |
| completed_at | TIMESTAMP | DDL |
| last_updated | TIMESTAMP | DDL |

### p3_audit_log

| column | type | source |
|--------|------|--------|
| user_id | SYMBOL | DDL |
| action | STRING | DDL |
| detail | STRING | DDL |
| old_value | STRING | DDL |
| new_value | STRING | DDL |
| ts | TIMESTAMP | DDL |

---

## 5. `scripts/lint_decimal_boundary.py` — current state

- **Suppression marker (line 74):** `# decimal-boundary: ok`
- **`OR_NUMBER_RE` (line 61):** `re.compile(r"\bor\s+\d+(?:\.\d+)?\b")`
- **`NOOP_TERNARY_RE` (lines 68–72):** `re.compile(r"(float|Decimal)\s*\(\s*([a-z_][a-z0-9_]*)\s*\)\s+if\s+not\s+isinstance\s*\(\s*\2\s*,\s*(?:float|int|Decimal|\(.*?\))\s*\)\s+else\s+\1\s*\(\s*\2\s*\)", re.IGNORECASE)`
- **`SKIP_GLOBS` (78–86):** `scripts/lint_decimal_boundary.py`, `tests/test_decimal_boundary.py`, `tests/test_decimal_boundary_lint.py`, `shared/decimal_boundary.py`, `shared/canonical_schemas.py`, `MONETARY_DECIMAL_MIGRATION_PLAN.md`, `MONETARY_DECIMAL_MERGE_VALIDATION.md`
- **`_SKIP_DIRNAMES` (142–148):** `.git`, `.venv`, `venv`, `env`, `.env`, `.tox`, `__pycache__`, `node_modules`, `.pytest_cache`, `.cache`, `build`, `dist`, `htmlcov`, `site-packages`, `questdb`, `redis`, `claude-mem`, `.audit-worktrees`, `voicetree-10-4`

**Lint logic:** `lint_file` reads UTF-8; per line, if suppression marker present skip; else if `NOOP_TERNARY_RE` match → finding; else if not `_line_in_scope` skip; else if `OR_NUMBER_RE` → finding. `_line_in_scope`: monetary column name substring in line OR `INGESTION_PATH_RE` match. `POSITION_MONITOR_FUNCTIONS` (101–106) defined but not referenced — possible dead config.

**What MUST be preserved:** Exit codes 0/1, suppression comment contract, `MONETARY_COLUMN_NAMES` set, both regexes' intent, `SKIP_GLOBS` / `_SKIP_DIRNAMES` behaviour, fix-option printouts; Phase 5 should extend, not replace.

---

## 6. Open questions / ambiguities for the orchestrator

1. **`POSITION_MONITOR_FUNCTIONS`** in `lint_decimal_boundary.py` is never used in the lint loop — confirm whether another code path uses it or it is stale.
2. **`canonical_schemas` module doc** flags D21 `timestamp` vs `ts`, D33 `session_date` STRING vs TIMESTAMP, D29/D30 date columns — these are schema/app mismatches outside DECIMAL boundary; out-of-scope for this remediation.
3. **`aim_modifier_at_entry`** stays DOUBLE per Isaac's spec ruling — Phase 1 fix coerces Decimal→float at the producer, NOT changing the schema.
4. **`update_d00_fields`:** placeholder count uses `len(D00_COLUMNS)` for `%s`, with `now()` for `last_updated` — values tuple excludes `last_updated`; matches QuestDB expectations.

---

## 7. Confidence note

All required files were read in full (`questdb_client.py` 253 lines, `decimal_boundary.py` 111, `decimal_json.py` 60, `json_helpers.py` 32, `lint_decimal_boundary.py` 205, `canonical_schemas.py` 1062). No timeouts, permissions, or encoding failures. **No gaps.**
