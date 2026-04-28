---
tags:
  - captain-audit
  - P3-command
---
# Captain Command — Full Block Pseudocode (Blocks 1–10)

| Field | Value |
|--------|--------|
| **Document** | Transfer Part 2 — 34 |
| **Purpose** | Complete pseudocode for all 10 Command blocks: routing, GUI, API, TSM, injection flow, reports, notifications, reconciliation, incidents, data validation. |
| **Last updated** | 2026-04-05 |
| **Source** | `research/V3 P1P2P3 Edits/Program3_Command.md` (1,281 lines — key blocks incorporated) |

## Cross-references

| Reference | Topic |
|-----------|--------|
| [[06_Captain_Command|Part 1 doc 06]] | Captain Command overview |
| [[18_GUI_Dashboard|Part 2 doc 18]] | GUI Dashboard |
| [[19_User_Management|Part 2 doc 19]] | User Management |
| [[26_Notification_System|Part 2 doc 26]] | Notification System |
| [[29_Operational_Policies|Part 2 doc 29]] | Operational Policies |

---

## Block 1 — Core Routing (PG-30)

### Health Endpoint

```
GET /health → {
    status: "OK" | "DEGRADED" | "HALTED",
    uptime_seconds: int,
    last_signal_time: datetime,
    active_users: int,
    circuit_breaker: "ACTIVE" | "HALTED",
    api_connections: {connected: int, total: int},
    last_heartbeat: datetime
}
-- Monitored externally every 30 seconds
-- 3 consecutive failures → external Telegram alert to ADMIN (survives Captain failure)
```

### Message Bus

```
P3-PG-30: "command_router_A"

-- Three message queues
signal_queue:       Online → Command → GUI + API adapters
command_queue:      GUI → Command → Online/Offline
notification_queue: Online/Offline → Command → GUI + Telegram + Push

WHILE Captain is active:

    -- Route signals (per-user delivery)
    WHILE signal_queue.has_messages():
        signal = signal_queue.pop()
        route_to_gui(signal, user_id=signal.user_id)
        FOR EACH ac_id, ac_detail IN signal.per_account:
            IF api_adapter_active(ac_id) AND account_belongs_to_user(ac_id, signal.user_id):
                route_to_api(ac_id, signal, ac_detail)

    -- Route commands
    WHILE command_queue.has_messages():
        command = command_queue.pop()
        SWITCH command.type:
            CASE "TAKEN":           log_trade_confirmation(command.signal_id, taken=True); FORWARD Online
            CASE "SKIPPED":         log_trade_confirmation(command.signal_id, taken=False)
            CASE "ADOPT_STRATEGY":  FORWARD Offline (PG-11)
            CASE "REJECT_STRATEGY": FORWARD Offline (PG-11)
            CASE "PARALLEL_TRACK":  FORWARD Offline (PG-11)
            CASE "SELECT_TSM":      handle_tsm_switch(command)
            CASE "ACTIVATE_AIM":    FORWARD Offline (PG-01)
            CASE "DEACTIVATE_AIM":  FORWARD Offline (PG-01)
            CASE "CONFIRM_ROLL":    confirm_contract_roll(command.asset, command.new_contract)
            CASE "UPDATE_ACTION_ITEM": update_action_item(command)
            CASE "TRIGGER_DIAGNOSTIC": FORWARD Offline (PG-16B, mode="ON_DEMAND")
            CASE "MANUAL_PAUSE":    set_asset_pause(command.asset, paused=True)
            CASE "MANUAL_RESUME":   set_asset_pause(command.asset, paused=False)

    -- Route notifications (user-scoped)
    WHILE notification_queue.has_messages():
        notif = notification_queue.pop()
        target_users = [notif.user_id] IF notif.user_id ELSE get_all_active_user_ids()
        FOR EACH uid IN target_users:
            route_to_gui_notification_centre(notif, user_id=uid)
            route_to_telegram(notif, user_id=uid)
            route_to_push(notif, user_id=uid)
        LOG to P3-D10

    SLEEP(100ms)
```

### Security Enforcement

```
PROHIBITED_FIELDS = [
    "aim_breakdown", "combined_modifier", "regime_probs",
    "kelly_params", "aim_weights", "strategy_logic",
    "ewma_states", "decay_states", "sensitivity_results"
]

FUNCTION sanitise_for_api(signal, ac_id):
    RETURN {
        asset:     signal.asset,
        direction: signal.direction,
        size:      signal.per_account[ac_id].contracts,
        tp:        signal.tp_level,
        sl:        signal.sl_level,
        timestamp: signal.timestamp
    }
    -- Only 6 fields — nothing else
```

---

## Block 2 — GUI Interface (PG-31)

```
P3-PG-31: "gui_data_server_A"

FUNCTION get_dashboard_data(user_id):
    user_silo = P3-D16[user_id]
    user_accounts = user_silo.accounts
    user_tz = get_user_preferences(user_id).display_timezone

    RETURN {
        signals:        get_latest_signals(user_id=user_id),
        regime_states:  get_regime_per_asset(),
        decay_alerts:   get_active_alerts(),
        warmup_gauges:  get_warmup_progress(),
        universe:       P3-D00,
        aim_panel:      {a: {status, warmup_pct, modifier, meta_weight, inclusion} for a in [1..16]},
        positions:      get_open_positions(user_accounts),
        tsm_status:     {ac: get_tsm_summary(ac) for ac in user_accounts},
        capital:        get_capital_summary(user_id),
        notifications:  get_unread_notifications(user_id),
        payout_panel:   get_payout_recommendations(user_accounts)
    }
```

System Overview (ADMIN only) serves additional panels: all users, all accounts, system health (8 dimensions from [[24_P3_Dataset_Schemas|P3-D22]]), action item queue, incident log, parameter editor. See [[18_GUI_Dashboard|doc 18]] for full panel specification.

---

## Block 3 — API + Execution (PG-32)

```
P3-PG-32: "api_plugin_A"

-- Broker adapter management
FOR EACH account ac WHERE api_enabled:
    adapter = load_adapter(tsm_configs[ac].api_type)    -- topstep_adapter / ibkr_adapter
    connection = adapter.connect(credentials_from_vault(ac))

    IF NOT connection.healthy:
        create_incident("API_CONNECTION", "P2_HIGH", "BROKER",
                       "Connection lost for {ac}. Auto-reconnect failed after 3 retries.")
        P3-D14[ac].status = "DISCONNECTED"
        CONTINUE

    P3-D14[ac].status = "CONNECTED"
    P3-D14[ac].last_heartbeat = now()

-- Compliance gate
FUNCTION compliance_check(signal, account):
    -- Verify signal is within TSM constraints
    IF signal.contracts > tsm_configs[account].max_contracts:
        RETURN {approved: False, reason: "EXCEEDS_MAX_CONTRACTS"}
    IF NOT instrument_permitted(signal.asset, tsm_configs[account]):
        RETURN {approved: False, reason: "INSTRUMENT_NOT_PERMITTED"}
    RETURN {approved: True}
```

---

## Block 4 — TSM Management (PG-33)

```
P3-PG-33: "tsm_manager_A"

FUNCTION onboard_account(user_id, tsm_file):
    -- Validate TSM structure
    required_fields = ["starting_balance", "max_drawdown_limit", "classification"]
    FOR EACH field IN required_fields:
        IF field NOT IN tsm_file: REJECT "Missing required field: {field}"

    -- Classify account
    category = tsm_file.classification.category
    IF category NOT IN ["PROP_EVAL", "PROP_FUNDED", "PROP_SCALING", "BROKER_RETAIL", "BROKER_INSTITUTIONAL"]:
        REJECT "Invalid account category"

    -- Load fee schedule
    IF "fee_schedule" IN tsm_file:
        validate_fee_schedule(tsm_file.fee_schedule)
    ELSE:
        tsm_file.fee_schedule = default_fee_schedule(category)

    -- Store
    P3-D08[tsm_file.account_id] = tsm_file
    P3-D16[user_id].accounts.append(tsm_file.account_id)

    LOG "Account {tsm_file.account_id} onboarded for user {user_id}"
```

---

## Block 5 — Injection Flow (PG-34)

GUI workflow for strategy adoption. Receives injection comparison from Offline Block 4, presents RPT-05, captures ADMIN decision (ADOPT/PARALLEL/REJECT), forwards to Offline [[32_P3_Offline_Full_Pseudocode|PG-11]].

---

## Block 6 — Reports (PG-35)

```
P3-PG-35: "report_generator_A"

REPORT_SPECS = {
    "RPT-01": {name: "Daily Signal Report", trigger: "pre-session",
               sources: [signal_queue, P3-D02, D05, D08, D12],
               content: "Direction, size, TP/SL, all AIM modifiers, Kelly base vs adjusted, TSM, regime"},
    "RPT-02": {name: "Weekly Performance", trigger: "end of trading week",
               sources: [P3-D03, D02, D12],
               content: "Win/loss by asset, actual vs predicted edge, AIM contribution, cost analysis"},
    "RPT-03": {name: "Monthly Health", trigger: "first trading day of month",
               sources: [P3-D04, D13, D01, D02, D08],
               content: "BOCPD/CUSUM, AIM-13 sensitivity, warm-up progress, meta-weights, TSM"},
    "RPT-04": {name: "AIM Effectiveness", trigger: "monthly + on demand",
               sources: [P3-D02, D03],
               content: "Per-AIM: modifier accuracy, PnL by direction, meta-weight trajectory, suppression"},
    "RPT-05": {name: "Injection Comparison", trigger: "on P1/P2 completion",
               sources: [P3-D06, D11],
               content: "Current vs proposed: AIM-contextualised performance, pseudotrader, recommendation"},
    "RPT-06": {name: "Regime Transition", trigger: "regime change detected",
               sources: [P3-D04, D05, regime_models],
               content: "Detection method, direction, edge impact, AIM states, historical comparisons"},
    "RPT-07": {name: "TSM Compliance", trigger: "daily (prop accounts)",
               sources: [P3-D08],
               content: "Drawdown vs MDD, pass probability, risk budget, days remaining, sizing recs"},
    "RPT-08": {name: "Probability Accuracy", trigger: "monthly",
               sources: [P3-D03, D05],
               content: "Regime calibration, expected vs actual edge by decile, confidence flags"},
    "RPT-09": {name: "Decision Change Impact", trigger: "on demand + quarterly",
               sources: [P3-D11],
               content: "Parameter change context, counterfactual, before/after pseudotrader"},
    "RPT-10": {name: "Annual Review", trigger: "annually",
               sources: [P3-D03, D06, D02, D04],
               content: "Full-year performance, AIM value-add, decay events, injection history, capital curve"},
    "RPT-11": {name: "Financial Summary Export", trigger: "monthly + on-demand",
               sources: [P3-D03, D08, D16, D19],
               content: "Per-user per-account: net PnL, fees, payouts, capital trajectory, tax fields"}
}

FUNCTION generate_report(report_id):
    spec = REPORT_SPECS[report_id]
    data = gather_data(spec.sources)
    report = render(spec, data)
    P3-D09.archive(report)
    priority = "LOW" IF report_id IN ["RPT-03", "RPT-10", "RPT-11"] ELSE "MEDIUM"
    NOTIFY_GUI("Report {report_id} generated", priority=priority)
    RETURN report
```

---

## Block 7 — Notifications (PG-36)

Full notification spec in [[26_Notification_System|doc 26]]. Telegram bot, 4 priority levels, inline buttons, quiet hours, per-user preferences, delivery logging to [[24_P3_Dataset_Schemas|P3-D10]].

---

## Block 8 — Daily Reconciliation (PG-39)

```
P3-PG-39: "daily_reconciliation_A"

-- Trigger: 19:00 EST daily (SOD boundary)

FOR EACH user IN active_users:
    FOR EACH account ac IN user.accounts:
        -- Step 1: Get broker balance
        IF api_adapter_active(ac):
            broker_balance = get_broker_balance(ac)
            system_balance = P3-D08[ac].current_balance

            IF abs(broker_balance - system_balance) > reconciliation_threshold:
                create_incident("RECONCILIATION", "P2_HIGH", "FINANCE",
                               "Balance mismatch for {ac}: broker={broker_balance}, system={system_balance}")

            P3-D08[ac].current_balance = broker_balance    -- broker is source of truth

        -- Step 2: SOD recalculation
        A = P3-D08[ac].current_balance
        IF P3-D08[ac].max_drawdown_limit is not None:
            P3-D08[ac].topstep_state.mdd_pct = 4500 / A
        P3-D08[ac].topstep_state.risk_per_trade_eff = (4500 * p + phi) / A
        P3-D08[ac].topstep_state.max_trades = floor(e * A / (4500 * p + phi))
        P3-D08[ac].topstep_state.exposure_budget = e * A
        P3-D08[ac].topstep_state.halt_threshold = c * e * A

        -- Step 3: Reset intraday state
        P3-D23[ac].L_t = 0
        P3-D23[ac].n_t = 0
        P3-D23[ac].session_trades = []

        -- Step 4: XFA scaling tier update (end-of-day evaluation)
        IF P3-D08[ac].scaling_plan_active:
            profit = A - P3-D08[ac].starting_balance
            P3-D08[ac].topstep_state.scaling_tier_micros = lookup_scaling_tier(profit)

        -- Step 5: Payout recommendation
        payout_rec = payout_decision(A, profit, tsm_configs[ac].payout_rules)
        IF payout_rec.withdraw:
            NOTIFY user "PAYOUT RECOMMENDED: ${payout_rec.amount}" priority="MEDIUM"

    -- Step 6: Log reconciliation
    P3-D19.append({user, accounts, timestamp: now(), mismatches, corrections})

SAVE P3-D08, P3-D23, P3-D19
```

---

## Block 9 — Incident Response (PG-40)

```
P3-PG-40: "incident_handler_A"

FUNCTION create_incident(category, severity, component, description, affected_users=None):
    incident = {
        incident_id: generate_uuid(),
        category: category,
        severity: severity,        -- P1_CRITICAL / P2_HIGH / P3_MEDIUM / P4_LOW
        component: component,
        description: description,
        timestamp: now(),
        system_state_snapshot: capture_system_state(),
        status: "OPEN",
        affected_users: affected_users or []
    }
    P3-D21.append(incident)

    -- Route notification per severity (see doc 26)
    IF severity == "P1_CRITICAL":
        NOTIFY all ADMIN + DEV, ALL channels, override quiet hours
    ELIF severity == "P2_HIGH":
        NOTIFY ADMIN + RISK, GUI + Telegram
    ELIF severity == "P3_MEDIUM":
        NOTIFY assigned owner, GUI only
    -- P4_LOW: logged only, visible in System Overview

    RETURN incident.incident_id
```

---

## Block 10 — Data Input Validation (PG-41)

```
P3-PG-41: "data_validation_A"

-- Continuous validation of incoming data streams

FOR EACH data_source IN P3-D00.data_sources:
    -- Check freshness
    last_update = data_source.last_received
    IF (now() - last_update) > data_source.max_staleness:
        create_incident("DATA_QUALITY", "P3_MEDIUM", "DATA_FEED",
                       "Data source {data_source.name} stale: last update {last_update}")

    -- Check completeness
    IF data_source.required_fields:
        missing = [f for f in data_source.required_fields if f not in latest_record]
        IF missing:
            create_incident("DATA_QUALITY", "P2_HIGH", "DATA_FEED",
                           "Missing fields in {data_source.name}: {missing}")

    -- Check format
    IF NOT validate_schema(latest_record, data_source.schema):
        create_incident("DATA_QUALITY", "P2_HIGH", "DATA_FEED",
                       "Schema violation in {data_source.name}")
```

## Audit Resolutions

> [!note] 2026-04-11 Gap Analysis — CRITICAL fixes
> The following audit resolutions reference specifications in this document:

- [[G-ONL-028_prohibited_fields_leak|G-ONL-028 — Prohibited Fields Leak]] (PROHIBITED_FIELDS) — CRITICAL RESOLVED
- [[G-CMD-002_rpt12_alpha_decomposition_missing|G-CMD-002 — RPT-12 Alpha Decomposition Missing]] (Block 6) — CRITICAL RESOLVED
- [[G-CMD-003_data_validation_no_monitoring|G-CMD-003 — Data Validation No Monitoring]] (PG-41) — CRITICAL RESOLVED
- [[G-CMD-004_balance_mismatch_no_incident|G-CMD-004 — Balance Mismatch No Incident]] (PG-39) — CRITICAL RESOLVED

## Related Canvases

- [[System 1/Backend/P3 Command.canvas|P3 Command]]
