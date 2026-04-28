# GUI trade close & trade log quick fix — execution summary

**Date:** 2026-04-28  
**Scope:** Wire B7 → Redis stream → Captain Command → WebSocket `trade_closed`, hydrate Trade Log from QuestDB snapshots, persist closed trades in the browser, normalize TopstepX User Hub PascalCase JSON keys.

---

## What changed

| Area | Change |
|------|--------|
| **`shared/redis_client.py`** | New consumer group constant `GROUP_COMMAND_GUI_OUTCOMES = "command_gui_outcomes"` (parallel to Offline’s `offline_outcomes` on the same stream). |
| **`captain-online/.../b7_position_monitor.py`** | `INSERT` into `p3_d03_trade_outcome_log` now sets **`exit_time`** (resolution instant). Stream payload adds **`signal_id`**, **`tp_level`**, **`sl_level`**, **`entry_time`**, **`exit_time`**. |
| **`captain-command/.../trade_gui_bridge.py`** | New helper `build_trade_closed_ws_payload()` → `(user_id, { type: trade_closed, ... })`. |
| **`captain-command/.../orchestrator.py`** | Background thread **`_trade_outcomes_gui_forwarder`**: `XREADGROUP` on `stream:trade_outcomes` with group `command_gui_outcomes`, ACK after `gui_push`. |
| **`captain-command/captain_command/main.py`** | `ensure_consumer_group(STREAM_TRADE_OUTCOMES, GROUP_COMMAND_GUI_OUTCOMES)` at startup. |
| **`captain-command/.../b2_gui_data_server.py`** | **`closed_trades`** in dashboard snapshot via **`_get_closed_trades()`** (QuestDB: `user_id` + `outcome IS NOT NULL`, ordered by `ts`). |
| **`captain-gui`** | `dashboardStore`: `loadClosedFromStorage` / `applyTradeClosed`, `trade_closed` WS branch in `useWebSocket.js`, localStorage key **`captain:closedTrades`**. |
| **`shared/topstep_stream.py`** | **`_normalize_hub_payload`**: PascalCase → camelCase for User Hub dicts (e.g. `Id` → `id`). |

---

## Automated tests

Run from repo root with the project venv:

```bash
.venv/bin/python -m pytest tests/test_trade_closed_pipeline.py tests/test_signal_id_flow.py -q
```

Expected: all passed (hub normalization + bridge payload + existing signal/D03 tests).

---

## How to validate on towers (Docker) before market open

Use **fish** (paths assume repo clone at `~/captain-system`; adjust if needed).

### 1. Pull and rebuild

```fish
cd ~/captain-system
git pull
docker compose build captain-command captain-online captain-gui
docker compose up -d
```

### 2. Confirm Command picked up the trade-outcomes consumer

```fish
docker compose logs captain-command --tail 300 | rg -i 'Trade outcomes GUI forwarder|command_gui_outcomes|trade_closed'
```

You should see **`Trade outcomes GUI forwarder started`** shortly after Command becomes healthy.

### 3. Confirm Redis stream consumer groups (two consumers on one stream)

```fish
docker compose exec redis redis-cli XINFO GROUPS stream:trade_outcomes
```

Expect entries for **`offline_outcomes`** and **`command_gui_outcomes`**.

### 4. Confirm dashboard REST returns `closed_trades`

If nginx exposes the API (adjust host/port to match your tower):

```fish
curl -sS -H "Authorization: Bearer YOUR_CAPTAIN_JWT" \
  http://localhost/api/dashboard/primary_user | jq '.closed_trades'
```

After at least one resolved trade in QuestDB for that user, **`closed_trades`** should be a non-empty array (or `[]` if no history).

### 5. Live GUI checks (browser)

1. Log into the GUI with a valid **`captain_jwt`**.
2. Open DevTools → Network → WS → frames.
3. When B7 resolves a position (`TP_HIT` / `SL_HIT` / time exit), Online publishes to **`stream:trade_outcomes`**; Command should emit a WebSocket frame:
   - **`type`: `"trade_closed"`**
   - **`trade_id`**, **`signal_id`** (when present), **`pnl`**, **`outcome`**, etc.
4. **Signals panel:** the matching **`signal_id`** row should disappear when **`trade_closed`** is applied.
5. **Trade Log panel:** new row with PnL; **`captain:closedTrades`** in Application → Local Storage should update.

### 6. Online tower — User Hub logs (optional)

```fish
docker compose logs captain-online --tail 200 | rg 'UserStream ORDER:'
```

After the PascalCase fix, **`id` / `status` / `type`** should often be non-null when the hub sends full objects (still subject to TopstepX delta messages).

---

## Risks & operational notes

| Topic | Note |
|-------|------|
| **No GUI WebSocket connected** | `gui_push` no-ops when no sessions; stream messages are still **ACK**’d so Offline is unaffected and the GUI consumer does not stall PEL. Users reconnecting get **`closed_trades`** from the periodic dashboard snapshot / REST. |
| **`captain:user_events`** | Still published by Online; Command does **not** subscribe yet. Live broker taps are improved via **`_normalize_hub_payload`** only. |
| **D03 `exit_time`** | New writes populate **`exit_time`**; older rows may still have NULL — GUI falls back to **`ts`** via **`_get_closed_trades`**. |
| **Duplicate `trade_closed`** | Frontend dedupes by **`trade_id`**. |

---

## Files touched (reference)

- `shared/redis_client.py`
- `captain-online/captain_online/blocks/b7_position_monitor.py`
- `captain-command/captain_command/blocks/trade_gui_bridge.py`
- `captain-command/captain_command/blocks/orchestrator.py`
- `captain-command/captain_command/main.py`
- `captain-command/captain_command/blocks/b2_gui_data_server.py`
- `captain-gui/src/stores/dashboardStore.js`
- `captain-gui/src/ws/useWebSocket.js`
- `shared/topstep_stream.py`
- `tests/test_trade_closed_pipeline.py`
