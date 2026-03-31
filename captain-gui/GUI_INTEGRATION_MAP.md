# GUI Integration Map — New Captain Dashboard

> Generated from screenshot analysis (`docs/new_captain_gui.jpg`) cross-referenced
> against the full `captain-gui/src/` codebase and `captain-command/` backend.
>
> **Purpose:** Wire the new frontend to the existing backend with zero guesswork.

---

## 0. BROKEN DATA PATHS — DO NOT CARRY FORWARD

The current GUI has **16 data-path issues** (4 critical, 3 moderate, 9 low). These
must be fixed during integration, NOT carried over. Each entry states what the
current code does wrong and what the new GUI should do instead.

### CRITICAL — Broken in visible UI

#### BUG-01: `direction` is integer everywhere, frontend expects string

**Where:** `OpenPosition.direction`, `PendingSignal.direction`, `WsSignalMessage.signal.direction`

**Backend sends:** `1` (long), `-1` (short), `0` (neutral) — integers from B6 signal output and D03 trade log.

**Frontend expects:** `"LONG"` / `"SHORT"` strings. Every comparison like `sig.direction === "LONG"` silently fails.

**Symptoms:** Direction badges show raw `1` / `-1`. All positions/signals styled as SHORT (red). TAKEN/SKIPPED commands send integer direction back to backend.

**Current files affected:**
- `active-signal.tsx:63` — `sig.direction === "LONG"` (always false)
- `active-signal.tsx:154` — `pos.direction === "LONG"` (always false)
- `todays-trades.tsx:48` — `pos.direction === "LONG"` (always false)
- `top-bar.tsx:44` — direction not checked, but would be wrong if used

**Fix for new GUI:** Either:
- (A) Backend fix in `_get_open_positions()`, `_get_pending_signals()`, and B6 signal output: convert `1 → "LONG"`, `-1 → "SHORT"` before sending
- (B) Frontend normalization layer: `direction > 0 ? "LONG" : "SHORT"` at the store ingestion boundary (in `setSnapshot`, `addSignal`)

**Recommendation:** (A) — fix at the source. The Command orchestrator already does this for auto-execute (`1→"BUY"`, `-1→"SELL"` in `orchestrator.py:272-275`). Add the same mapping to the GUI data path.

---

#### BUG-02: `tp_level` and `sl_level` always `null` on open positions

**Where:** `_get_open_positions()` in `b2_gui_data_server.py:310-317`

**Backend sends:** `"tp_level": None, "sl_level": None` — hardcoded. The D03 table (`p3_d03_trade_outcome_log`) does not store TP/SL levels.

**Frontend expects:** `tp_level: number`, `sl_level: number` (non-nullable in the interface).

**Symptoms:** ProximityBar renders with `tp=null, sl=null` → division by zero → NaN positioning. TP/SL data cells show `$0.00`. The entire position proximity visualization is non-functional.

**Current files affected:**
- `active-signal.tsx:183-194` — ProximityBar and TP/SL DataCells

**Fix for new GUI:** Either:
- (A) Store TP/SL in D03 at trade creation time (requires Online B7 change)
- (B) Join D03 against `p3_session_event_log` where `event_type='SIGNAL_RECEIVED'` to recover TP/SL from the signal detail JSON
- (C) Cache TP/SL in the Command orchestrator when a signal is TAKEN, and inject into the dashboard response

**Recommendation:** (A) — add `tp_level` and `sl_level` columns to D03, populate at trade entry. Most correct long-term.

---

#### BUG-03: ProximityBar hardcodes ES point value (50)

**Where:** `active-signal.tsx:155`

```typescript
const approxCurrent = pos.entry_price + pnl / (pos.contracts * 50 || 1);
```

**Problem:** Multiplier `50` is correct for ES only. Other assets:
| Asset | Actual Point Value | Error Factor with 50 |
|---|---|---|
| MES | 5 | 10x over |
| NQ | 20 | 2.5x over |
| MNQ | 2 | 25x over |
| MYM | 0.5 | 100x over |
| ZB | 1000 | 20x under |
| ZN | 1000 | 20x under |

**Symptoms:** For a MYM position, the estimated current price could be 100x wrong, placing the ProximityBar marker completely off-screen.

**Fix for new GUI:** Either:
- (A) Backend: include `point_value` in the `OpenPosition` payload (read from `p3_d00_asset_universe.locked_strategy` JSON or a constants map)
- (B) Frontend: maintain a `POINT_VALUES` lookup table matching `shared/constants.py`

**Recommendation:** (A) + (B) — backend should send it, frontend should have a fallback table.

---

#### BUG-04: `daily_pnl` and `cumulative_pnl` always null in CapitalSilo

**Where:** `_get_capital_silo()` in `b2_gui_data_server.py:247-293`

**Backend sends:** `"daily_pnl": None, "cumulative_pnl": None` across all three code paths (UserStream, REST, QuestDB). Comments say "Computed by reconciliation" but reconciliation never writes these back.

**Symptoms:** TopBar `DAY` and `WEEK` metrics permanently show `+$0.00`. The `RiskLimitsCell` daily P&L badge always shows `+$0.00`.

**Current files affected:**
- `top-bar.tsx:41-42` — `dailyPnl` and `weekPnl` always 0
- `top-bar.tsx:117-118` — "DAY +$0.00", "WEEK +$0.00"
- `risk-limits.tsx:13` — daily P&L badge always green `+$0.00`

**Fix for new GUI:**
- Compute `daily_pnl` in `_get_capital_silo()`: `current_balance - start_of_day_balance` (SOD balance can come from D08 `starting_balance` or a cached value)
- Compute `cumulative_pnl`: `current_balance - starting_balance` (already available in TSM data)
- OR derive from D03 trade outcomes: `SUM(pnl) WHERE entry_time > today`

---

### MODERATE — Misleading data displayed

#### BUG-05: TopBar metrics computed from open positions only

**Where:** `top-bar.tsx:43-48`

**Problem:** `TRADES`, `WIN%`, and `PF` are computed from `openPositions` (trades where `outcome IS NULL`). Once a trade closes, it disappears. Outside of the ~30-minute trading session, there are 0 open positions → all metrics show `0` / `--`.

**Symptoms:** TRADES=0, WIN%=--, PF=-- for 23+ hours per day. During trading, WIN% reflects unrealized P&L of open positions, not actual win rate.

**Fix for new GUI:**
- New backend field: `daily_trade_stats` in the dashboard snapshot containing: `{trades_today, wins, losses, win_pct, profit_factor, total_pnl}` computed from D03 closed trades (`WHERE outcome IS NOT NULL AND entry_time > today`)
- Frontend: read from this new field instead of computing from `openPositions`

---

#### BUG-06: PendingSignal `direction` is integer (via `**detail` spread)

**Where:** `_get_pending_signals()` in `b2_gui_data_server.py:347-351`

The `**detail` spread injects the full signal dict (from B6) into the response. The `direction` field in that dict is an integer (same root cause as BUG-01).

**Same fix as BUG-01** — normalize at the backend before sending.

---

### LOW — Type mismatches / missing fields (not visibly broken)

| ID | Issue | Where | Impact |
|---|---|---|---|
| BUG-07 | `AimState.aim_id` is `int` from backend, TS type says `string` | `types.ts:40` | No visible error — `aim-registry.tsx` defensively coerces with `String()` |
| BUG-08 | Backend sends `asset_id` on AimState, frontend type omits it | `b2:391`, `types.ts:39-46` | Extra field silently dropped, blocks future per-asset AIM UI |
| BUG-09 | `AimState.meta_weight` always `null` — D02 join missing | `b2:394` | Not currently rendered, but data gap |
| BUG-10 | `DecayAlert.level` always `null` — escalation level not queried | `b2:460` | CB cell shows `L${null}` → "Lnull" |
| BUG-11 | `WsSignalMessage.contracts` / `entry_price` missing at signal level | `types.ts:253-254` | Type definition wrong, fields not currently rendered |
| BUG-12 | `WsSignalMessage.per_account` shape wrong, no `risk_amount` | `types.ts:263` | Type undersized (2 of 11 fields), `risk_amount` doesn't exist |
| BUG-13 | WsNotification drops `sound`, `action_required`, `data`, `event_type`, `asset` | `useWebSocket.ts:118-126` | Features like notification sounds impossible |
| BUG-14 | `PayoutEntry` missing `winning_days_*` and `next_eligible_date` | `b2:170-183` | Optional fields, show dashes — but data never available |
| BUG-15 | `below_threshold` WS event type unhandled in dispatch | `useWebSocket.ts:100-133` | Event silently dropped |
| BUG-16 | `error` WS event type unhandled in dispatch | `useWebSocket.ts:100-133` | Backend errors never shown to user |

---

### Integration Checklist

Before wiring any data path in the new GUI, cross-reference this list:

- [ ] **Direction normalization** — Do NOT use `=== "LONG"` unless backend is confirmed to send strings
- [ ] **TP/SL on positions** — Do NOT render ProximityBar until backend sends real TP/SL values
- [ ] **Point values** — Do NOT hardcode 50; use per-asset lookup
- [ ] **P&L fields** — Do NOT rely on `capitalSilo.daily_pnl`; it's null. Derive from TSM balance or trade log
- [ ] **TopBar metrics** — Do NOT compute win%/PF from `openPositions`; need closed-trade stats
- [ ] **AIM types** — `aim_id` arrives as integer; handle accordingly
- [ ] **Decay level** — `level` is null; either fix backend query or don't render "L{level}"
- [ ] **WS dispatch** — Handle `error` and `below_threshold` event types

---

## 1. DATA CONNECTIONS

Every dynamic value visible in the new GUI screenshot, mapped to its current source.

### 1.1 Top Bar — Time & Connection

| UI Element | Location in Screenshot | Current Data Source | Variable Path | Update Frequency |
|---|---|---|---|---|
| Clock `19:24:68 CT` | Top-left corner | `dashboardStore.timestamp` → formatted via `toLocaleTimeString("en-US", {timeZone: "America/New_York"})` | `useDashboardStore((s) => s.timestamp)` | Every 60s (dashboard snapshot) |
| WS status dot | Top-right status area | `dashboardStore.connected` | `useDashboardStore((s) => s.connected)` | Real-time (WebSocket open/close) |
| API status dot | Top-right status area | `dashboardStore.apiStatus.api_authenticated` | `useDashboardStore((s) => s.apiStatus)` | Every 60s (dashboard snapshot) |
| QDB status dot | Top-right status area | Derived from `dashboardStore.connected` | `useDashboardStore((s) => s.connected)` | Real-time |
| "Websocket connected to Topstep gateway" | Right-side log area | **NEW** — Not surfaced in current frontend. Backend has `apiStatus.market_stream` and `apiStatus.user_stream` but these are only shown as status dots, not as text | `dashboardStore.apiStatus.market_stream` / `apiStatus.user_stream` | 60s |

### 1.2 Risk Management Panel (Left Column)

| UI Element | Location in Screenshot | Current Data Source | Variable Path | Update Frequency |
|---|---|---|---|---|
| Starting capital `$150,000.00` | Top-left, first value | `TsmStatus.current_balance` or seed value from `p3_d08_tsm_state.starting_balance` | `useDashboardStore((s) => s.tsmStatus)` → `.starting_balance` | 60s — **NOTE:** `starting_balance` is queried in `_get_tsm_status()` but NOT included in the returned dict. Gap — see §7 |
| Current balance `$151,287.50` | Top-left, second value | `TsmStatus.current_balance` (from `p3_d08_tsm_state`) | `useDashboardStore((s) => s.tsmStatus[0]?.current_balance)` | 60s |
| P&L `+$1,287.50` | Top-left, third value (green) | Derived: `current_balance - starting_balance`. Currently `capitalSilo.cumulative_pnl` | `useDashboardStore((s) => s.capitalSilo?.cumulative_pnl)` | 60s — **BROKEN (BUG-04):** always null. Must derive from TSM balance delta |
| DRAWDOWN section — `MAX DD` | Left panel, below header | `TsmStatus.mdd_used_pct` and `TsmStatus.mdd_limit` | `useDashboardStore((s) => s.tsmStatus)` → `.mdd_used_pct` | 60s |
| DRAWDOWN — percentage bar + value | Left panel | `TsmStatus.mdd_used_pct` | Same as above | 60s |
| MAX DD percentage value `18.1%` | Left panel | `TsmStatus.mdd_used_pct` | `tsmStatus[0].mdd_used_pct` | 60s |
| DAILY P&L | Left panel | `capitalSilo.daily_pnl` | `useDashboardStore((s) => s.capitalSilo?.daily_pnl)` | 60s — **BROKEN (BUG-04):** always null |
| TARGET `$4,900` → REMAINING `$3,312.50` | Left panel | **NEW** — The profit target for evaluation accounts. Backend has `starting_balance` in `p3_d08_tsm_state` and can derive target from TSM `topstep_state.profit_target`. Not currently exposed | N/A | N/A |
| "90 trading days to target (avg $187.77/day)" | Left panel | **NEW** — Requires: profit target, current profit, trading days elapsed. None of these are in the current dashboard snapshot | N/A | N/A |
| OEL SWITCH values `-80.00` / `+80.00` | Left panel | **NEW** — "Open Equity Limit" is a TopstepX-specific risk parameter. Not currently tracked in the frontend or dashboard snapshot | N/A | N/A |
| PROFIT SWITCH | Left panel | **NEW** — TopstepX profit switch parameter. Not in current data model | N/A | N/A |
| Profit Info section: Account `20319811` | Left panel | `TsmStatus.account_id` | `useDashboardStore((s) => s.tsmStatus[0]?.account_id)` | 60s |
| `\u2014/u2014` (user ID display) | Left panel | **NEW** — Currently hardcoded as `primary_user` in auth context. The display of `/u2014` suggests a user/account reference | `useAuth().user.user_id` | Static |
| State: `Unknown`, `Systematic`, `TBD` | Left panel | **NEW** — Strategy state labels. The `p3_d00_asset_universe.captain_status` exists but is not displayed in this format | N/A | N/A |
| Account details: `PRAC-V2-551001-43861321` | Left panel | `apiStatus.account_name` | `useDashboardStore((s) => s.apiStatus?.account_name)` | 60s |
| `$150,000.00` (account starting balance) | Left panel | See starting_balance gap above | `tsmStatus` — needs backend change | 60s |
| Secondary account `109675-V2-533201-199xxx35` | Left panel | `tsmStatus` (second entry if multiple accounts) | `useDashboardStore((s) => s.tsmStatus)` | 60s |
| `$4,000.00` / `$2,250.00` / `30` / `34.2%` | Bottom-left | **PARTIAL** — Some are in `DayStatsCell` (daily P&L, win%). Others like trade count `30` and specific dollar values may be **NEW** aggregate statistics not currently computed | Various from `openPositions` | 60s |

### 1.3 Chart Panel (Center)

| UI Element | Location in Screenshot | Current Data Source | Variable Path | Update Frequency |
|---|---|---|---|---|
| "MES Micro E-mini S&P" header | Center-top | **NEW** — Asset full name. Current `LiveMarketCell` extracts symbol from `contract_id` via `contractSymbol()` but doesn't show the full name | `liveMarket.contract_id` → needs name mapping | 1Hz (symbol), static (name) |
| Quote line: `@ $441.82 ↑ $425.58` | Center, below header | `liveMarket.open`, `liveMarket.change` | `useDashboardStore((s) => s.liveMarket)` | 1Hz (WebSocket `live_market`) |
| `Bid/Ask $429.56 / $429.81` | Center, below header | `liveMarket.best_bid`, `liveMarket.best_ask` | `useDashboardStore((s) => s.liveMarket)` | 1Hz |
| `Vol 1,707,219` | Center, below header | `liveMarket.volume` | `useDashboardStore((s) => s.liveMarket?.volume)` | 1Hz |
| LAST PRICE `5429.68` (large, right side) | Top-right area | `liveMarket.last_price` | `useDashboardStore((s) => s.liveMarket?.last_price)` | 1Hz |
| Candlestick chart | Center | **NEW** — No charting exists in current frontend. Current `LiveMarketCell` shows only text values. Needs OHLC bar data | N/A — see §7 | N/A |
| OR UPPER / OR LOWER lines on chart | Center chart overlay | **NEW** — OR range data is computed by `captain-online/blocks/or_tracker.py` and stored in memory, but NOT published to the GUI. The OR tracker writes to `p3_session_event_log` | N/A — see §7 | Per-session |
| `INSIDE OR` label with `$436.72` / `$428.42` | Bottom of chart | **NEW** — Same as above. OR range values not currently sent to frontend | N/A | Per-session |
| Entry, SL, TP lines on chart | Chart overlays | `openPositions[].entry_price`, `.sl_level`, `.tp_level`. Exists as data, NOT as chart overlays | `useDashboardStore((s) => s.openPositions)` | 60s |
| VWAP line | Chart overlay | **NEW** — VWAP not computed or stored anywhere in the system | N/A | N/A |
| Price labels `$438.25`, `$428.50`, `$442.50` | Chart Y-axis | **NEW** — Derived from chart data | N/A | N/A |
| `+$21.50`, `-$7.50` P&L annotations | Right of chart | **NEW** — Per-trade P&L on chart. Data exists in `openPositions[].current_pnl` but not rendered on a chart | `openPositions` | 60s |

### 1.4 Trades & Signals Panel (Right Column)

| UI Element | Location in Screenshot | Current Data Source | Variable Path | Update Frequency |
|---|---|---|---|---|
| Signal cards (FILLED/SKIPPED badges) | Right panel, scrollable | `pendingSignals` (for pending) and signals via WS `signal` event | `useDashboardStore((s) => s.pendingSignals)` | On event (WS `signal`) + 60s |
| Signal entry price, TP, SL values | Right panel, per signal | `WsSignalMessage.signal.entry_price`, `.tp_level`, `.sl_level` | From WS `signal` event payload | On event — **NOTE (BUG-11):** `entry_price` not at signal level; TP/SL are present in B6 output but `entry_price` is not included in the signal dict |
| Signal confidence/quality | Right panel | `PendingSignal.quality_score`, `.confidence_tier` | `pendingSignals[].quality_score` | On event |
| Signal timestamp | Right panel | `PendingSignal.timestamp` | `pendingSignals[].timestamp` | On event |
| P&L per signal: `+$142.50`, `Confidence: 72%` | Right panel | `WsSignalMessage.signal.quality_score` (confidence), P&L from `openPositions` | Mixed sources | Mixed |
| Direction: `OR_BREAK_SHORT` | Right panel | **BROKEN (BUG-01/03):** WS signal `direction` is actually an integer (`1`/`-1`), NOT a string. The `OR_BREAK_SHORT` label format is also NEW | `signal.direction` (integer!) + signal type prefix | On event |
| Signal pipeline status pills: `WAITING`, `OR FORMING`, `SIGNAL GEN`, `EXECUTED` | Right panel, below signals | **NEW** — No pipeline stage tracking exists in the frontend. The OR tracker has internal states (`WAITING`, `FORMING`, `LOCKED`, `MONITORING`, `DONE`) but these are NOT published to the GUI | N/A — see §7 | N/A |
| Auto Trade toggle state | Right panel | **NEW** — `AUTO_EXECUTE` env var exists on the backend (`captain-command/orchestrator.py`), but there is no way to read or toggle it from the GUI | N/A — see §7 | N/A |

### 1.5 Live Terminal (Bottom)

| UI Element | Location in Screenshot | Current Data Source | Variable Path | Update Frequency |
|---|---|---|---|---|
| System log entries with timestamps | Bottom panel | `notifications` from `notificationStore` | `useNotificationStore((s) => s.notifications)` | On event (WS `notification`) + 60s |
| Log categories (trade, signal, market, warn, system) | Bottom panel | Derived from notification message text via `guessCategory()` in `notifications.tsx` | Same as above | Same |
| "Auto connection restored after X minutes" | Bottom panel | **NEW** — Connection state change events. Current code has disconnect banner but no notification for reconnection | N/A | N/A |
| "Redis connection restored" | Bottom panel | **NEW** — Redis health events not surfaced to frontend | N/A | N/A |
| Specific log messages about TopstepX API calls | Bottom panel | **PARTIAL** — These could be `notification` events but most backend log messages go to `logger` not to the notification system | Would need backend changes | N/A |

### 1.6 Signal & Execution Bar (Bottom-Center)

| UI Element | Location in Screenshot | Current Data Source | Variable Path | Update Frequency |
|---|---|---|---|---|
| Signal entry/TP/SL numeric values: `$438.25`, `$442.50`, `$438.75` | Bottom bar | `WsSignalMessage.signal.entry_price`, `.tp_level`, `.sl_level` | From `pendingSignals` or `openPositions` | On event / 60s |
| `SIGNAL GEN` / `EXECUTED` labels | Bottom bar | **NEW** — Pipeline stage labels. Not tracked in current frontend | N/A — see §7 | N/A |
| `DIY` / `AUTO` mode indicator | Bottom bar | **NEW** — Maps to `AUTO_EXECUTE` setting. Not readable from GUI | N/A | N/A |

---

## 2. INTERACTIVE ELEMENTS

Every clickable, toggleable, or input-accepting element identified in the new GUI.

### 2.1 Asset Selector Tabs (Chart Header)

**Screenshot location:** Center-top, tabs showing `MES`, `MNQ`, `ES`, `NQ`, `MYM`, `MGC`

**Current handler:** Does not exist. The current `LiveMarketCell` reads from a single `liveMarket` state object which is populated from a hardcoded `ES` contract in `_get_live_market_data(asset_id="ES")`.

**What needs to be built (NEW):**
- Frontend: New state for `selectedAsset` (could live in `dashboardStore` or a new `chartStore`)
- Backend: `_get_live_market_data()` already accepts an `asset_id` param but the orchestrator always calls it with default `"ES"`. Need to:
  1. Send `selectedAsset` to backend via WebSocket command
  2. Have `build_live_market_update()` use the user's selected asset
  3. OR stream all assets and filter client-side

### 2.2 Timeframe Selector Pills

**Screenshot location:** Below chart header — `15s`, `1m`, `5m`, `15m`

**Current handler:** Does not exist. No charting exists in the current frontend.

**What needs to be built (NEW):**
- Frontend: Timeframe state + chart data fetching
- Backend: Historical bar data endpoint. Options:
  1. Query TopstepX historical bars API (`/api/History/retrieveBars`)
  2. Query QuestDB for stored bar data (if ingested)
  3. Build bars client-side from tick/quote data

### 2.3 Chart Overlay Toggles

**Screenshot location:** Chart area — `OR Upper`, `OR Lower`, `Entry`, `SL`, `TP`, `VWAP`

**Current handler:** Does not exist. No chart overlays in current frontend.

**What needs to be built (NEW):**
- Frontend: Toggle state per overlay (local React state or store)
- Data sources:
  - `OR Upper/Lower`: OR tracker state (NEW endpoint needed)
  - `Entry/SL/TP`: Already in `openPositions` — just needs chart rendering
  - `VWAP`: NEW — needs computation from bar data

### 2.4 Auto Trade Toggle Switch

**Screenshot location:** Right panel, labeled "Auto Trade" with on/off switch

**Current handler:** Does not exist. `AUTO_EXECUTE` is an environment variable on the backend, not controllable from GUI.

**What needs to be built (NEW):**
- Frontend: Toggle component + WebSocket command
- Backend: New command type (e.g., `SET_AUTO_EXECUTE`) in `COMMAND_TYPES`
- Backend handler in `b1_core_routing.route_command()` to update runtime `AUTO_EXECUTE` flag
- Requires: new REST endpoint or WS command, plus state persistence

### 2.5 View Switcher Tabs (Top Nav)

**Screenshot location:** Top bar — `TRADING`, `MODELS`, `CONFIG`

**Current handler:** The current `TopBar` has nav items: `Dashboard`, `System`, `Processes`, `History`, `Reports`, `Settings`. These are React Router `NavLink` components.

**Current code:** `captain-gui/src/components/top-bar.tsx:8-15`
```typescript
const navItems = [
  { to: "/", label: "Dashboard" },
  { to: "/system", label: "System", adminOnly: true },
  { to: "/processes", label: "Processes" },
  { to: "/history", label: "History" },
  { to: "/reports", label: "Reports" },
  { to: "/settings", label: "Settings" },
];
```

**Integration:** Replace nav items. `TRADING` → `/` (Dashboard), `MODELS` and `CONFIG` are NEW pages that need routes and page components.

### 2.6 Account Selector Dropdown

**Screenshot location:** Left panel, showing account `20319811`

**Current handler:** Account info displayed read-only in `RiskLimitsCell` and `TopBar`. No dropdown selector exists.

**What needs to be built (NEW if multi-account):**
- If single account: display-only (current behavior, just restyled)
- If multi-account: new dropdown that filters `tsmStatus`, `openPositions`, `payoutPanel` by selected `account_id`

### 2.7 Trade Log Tab Bar

**Screenshot location:** Bottom area — `TRADE LOG`, `ORDER HISTORY`, `PERFORMANCE`

**Current handler:** `TodaysTradesCell` shows a single trade table. No tabs.

**What needs to be built (NEW):**
- `TRADE LOG`: Restyle of current `TodaysTradesCell` (data exists)
- `ORDER HISTORY`: **NEW** — Requires order history endpoint. Backend has `p3_d03_trade_outcome_log` for closed trades. May need TopstepX `get_order_history()` from `shared/topstep_client.py`
- `PERFORMANCE`: **NEW** — Aggregated performance stats. Some data exists in `DayStatsCell` calculations. May need dedicated endpoint for historical performance

### 2.8 System Log Filter Tabs

**Screenshot location:** Bottom terminal — `All`, `Errors`, `Signals`, `Orders`

**Current handler:** `NotificationsCell` has priority-based filter tabs: `ALL`, `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`.

**Current code:** `captain-gui/src/cells/notifications.tsx:8-9`
```typescript
const FILTERS: (NotificationPriority | "ALL")[] = [
  "ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW",
];
```

**Integration:** Replace priority filters with category filters. The `guessCategory()` function in `notifications.tsx:23-27` already classifies by content — adapt filter logic to use categories instead of priorities.

### 2.9 FILLED/SKIPPED Badges on Signal Cards

**Screenshot location:** Right panel, on individual signal cards

**Current handler:** `ActiveSignalCell` has TAKEN/SKIP buttons that send WebSocket commands.

**Current code:** `captain-gui/src/cells/active-signal.tsx:21-35` — `handleAction()` sends `TAKEN_SKIPPED` command via WebSocket.

**Integration:** The new design appears to show these as status badges (display-only after action), not as action buttons. The current code removes the signal on action (`removeSignal`). New design may need to keep actioned signals visible with a FILLED/SKIPPED badge. Requires storing action state per signal.

### 2.10 Signal Pipeline Status Pills

**Screenshot location:** Right panel — `WAITING`, `OR FORMING`, `SIGNAL GEN`, `EXECUTED`

**Current handler:** Does not exist.

**What needs to be built (NEW):**
- Backend: Publish OR tracker state transitions as a new WS message type (e.g., `pipeline_status`)
- OR tracker states map: `WAITING` → `FORMING` → `LOCKED`/`MONITORING` → `DONE`
- Frontend: New status display component subscribing to pipeline state

### 2.11 Chart Interaction: CHART / TABLE / SIGNALS Tabs

**Screenshot location:** Center panel, below asset name — tabs for different chart views

**Current handler:** Does not exist. No chart/table/signals view switcher.

**What needs to be built (NEW):**
- Frontend: Tab state (local) switching between chart canvas, data table, and signal list views
- `CHART`: The candlestick chart (NEW)
- `TABLE`: Tabular OHLCV data (NEW — needs bar data endpoint)
- `SIGNALS`: Signal history overlay or list (data exists in `pendingSignals`)

### 2.12 Scrollable Regions

| Region | Scroll Behavior |
|---|---|
| Risk Management panel (left) | Vertical scroll for overflow — use Radix `ScrollArea` |
| Signal cards (right) | Vertical scroll — current `ActiveSignalCell` uses `ScrollArea` max-h 320px |
| System log (bottom) | Vertical scroll — current `NotificationsCell` uses `ScrollArea` max-h 160px |
| Trade log (bottom-center) | Vertical scroll — current `TodaysTradesCell` uses `ScrollArea` max-h 200px |
| Chart (center) | Pan/zoom — needs chart library (e.g., lightweight-charts, TradingView) |

### 2.13 Additional Interactive Elements Identified

| Element | Type | Current Status |
|---|---|---|
| Percentage display `18.1%` next to drawdown | Display-only | Exists in `RiskLimitsCell` as `ProgressBar` |
| `100%` indicator at bottom-right | Display-only | **NEW** — possibly scaling utilization or system health |
| Gear/settings icon | Button | **NEW** if present — would open settings panel |
| Fullscreen/expand icon on chart | Button | **NEW** — chart fullscreen toggle |

---

## 3. ZUSTAND STORES

### 3.1 `dashboardStore` — Main Dashboard State

**File:** `captain-gui/src/stores/dashboardStore.ts`

**State Shape:**
```typescript
interface DashboardState {
  connected: boolean;                    // WS connection status
  timestamp: string | null;              // Last snapshot time
  capitalSilo: CapitalSilo | null;       // {total_capital, daily_pnl, cumulative_pnl, status}
  openPositions: OpenPosition[];         // Active trades
  pendingSignals: PendingSignal[];       // Unacted signals
  aimStates: AimState[];                 // AIM model states
  tsmStatus: TsmStatus[];               // Per-account risk limits
  decayAlerts: DecayAlert[];             // BOCPD decay events
  warmupGauges: WarmupGauge[];           // Asset warmup progress
  regimePanel: RegimePanel | null;       // Regime classification data
  payoutPanel: PayoutEntry[];            // Topstep payout info
  scalingDisplay: ScalingEntry[];        // Scaling tier info
  liveMarket: LiveMarket | null;         // Real-time market data
  apiStatus: ApiStatus | null;           // TopstepX connection status
  lastAck: WsCommandAck | null;         // Last command acknowledgment
}
```

**Actions:**
| Action | Signature | Purpose |
|---|---|---|
| `setConnected` | `(c: boolean) => void` | Toggle WS connected state |
| `setSnapshot` | `(s: DashboardSnapshot) => void` | Merge full dashboard snapshot (preserves newer liveMarket) |
| `setLiveMarket` | `(lm: LiveMarket) => void` | Incremental merge — only non-null fields overwrite |
| `addSignal` | `(sig: WsSignalMessage["signal"]) => void` | Prepend new signal to list |
| `setCommandAck` | `(ack: WsCommandAck) => void` | Store last command ack |
| `removeSignal` | `(signalId: string) => void` | Remove signal after TAKEN/SKIPPED |

**Subscribers (current components → new GUI mapping):**

| Component | Store Fields Used | New GUI Element |
|---|---|---|
| `TopBar` | `connected`, `capitalSilo`, `openPositions`, `apiStatus`, `timestamp` | Top bar (time, balance, P&L, status dots) |
| `DashboardPage` | `connected` (for polling) | Root page |
| `AppLayout` | `connected` (disconnect banner) | Disconnect banner |
| `ActiveSignalCell` | `pendingSignals`, `openPositions`, `lastAck` | Signal cards (right panel) + open positions |
| `LiveMarketCell` | `liveMarket` | Chart header quote data, LAST PRICE |
| `RiskLimitsCell` | `capitalSilo`, `tsmStatus` | Risk Management panel (left) |
| `RegimeCell` | `regimePanel` | Not clearly visible in new design — may be removed or embedded |
| `CircuitBreakerCell` | `warmupGauges`, `decayAlerts` | Not clearly visible — may be in system log or status area |
| `AimRegistryCell` | `aimStates` | Not visible in new design — likely moved to MODELS tab |
| `TodaysTradesCell` | `openPositions` | Trade Log tab (bottom) |
| `DayStatsCell` | `capitalSilo`, `openPositions`, `payoutPanel`, `scalingDisplay` | Risk Management panel (left) stats |
| `NotificationsCell` | (none — uses notificationStore) | System log (bottom) |

### 3.2 `notificationStore` — Notifications

**File:** `captain-gui/src/stores/notificationStore.ts`

**State Shape:**
```typescript
interface NotificationState {
  notifications: Notification[];   // Capped at 500
  unreadCount: number;
}
```

**Actions:**
| Action | Signature | Purpose |
|---|---|---|
| `addNotification` | `(n: Notification) => void` | Prepend + cap at 500 |
| `setNotifications` | `(ns: Notification[]) => void` | Bulk replace (REST load) |
| `markAllRead` | `() => void` | Reset unread counter |

**Subscribers:** `NotificationsCell` → System log (bottom panel), `TopBar` → unread badge

**New GUI mapping:** The "LIVE TERMINAL" panel at the bottom of the new design.

### 3.3 `systemOverviewStore` — Admin Panel

**File:** `captain-gui/src/stores/systemOverviewStore.ts`

**State Shape:**
```typescript
interface SystemOverviewState {
  overview: SystemOverview | null;
}
```

**Actions:** `setOverview(o: SystemOverview)`

**Subscribers:** `SystemOverviewPage` + 17 admin panels

**New GUI mapping:** Not visible in new design screenshot. Likely stays as a separate page (ADMIN-only).

### 3.4 `themeStore` — Theme Toggle

**File:** `captain-gui/src/stores/themeStore.ts`

**State Shape:**
```typescript
interface ThemeState {
  theme: "dark" | "light";
}
```

**Actions:** `toggle()` — persists to localStorage

**Subscribers:** `SettingsPage`, `ThemeApplier`

**New GUI mapping:** The new design is dark-only. This store may be unnecessary.

---

## 4. WEBSOCKET SUBSCRIPTIONS

**Connection:** Singleton WebSocket at `ws://{host}/ws/{user_id}`

**File:** `captain-gui/src/ws/useWebSocket.ts`

### 4.1 Message Types

| WS Event Type | Payload Shape | Store Updated | New GUI Element |
|---|---|---|---|
| `"connected"` | `{type, user_id}` | Resets retry counter | Status dot (top bar) |
| `"dashboard"` | Full `DashboardSnapshot` (14 fields) | `dashboardStore.setSnapshot()` | ALL panels — risk, market, signals, trades |
| `"live_market"` | `LiveMarket` (13 fields: connected, contract_id, last_price, best_bid, best_ask, spread, change, change_pct, open, high, low, volume, timestamp) | `dashboardStore.setLiveMarket()` — incremental merge | Chart header (quote data), LAST PRICE display |
| `"signal"` | `{type, signal: {signal_id, asset, direction, contracts, tp_level, sl_level, entry_price, quality_score, confidence_tier, combined_modifier, regime_state, session, aim_breakdown, per_account, timestamp}}` | `dashboardStore.addSignal()` | Signal cards (right panel) |
| `"command_ack"` | `{type, command, action?, signal_id?, account_id?, tsm_name?}` | `dashboardStore.setCommandAck()` | Ack banner on signal cards |
| `"notification"` | `{type, notif_id, priority, message, timestamp, source}` | `notificationStore.addNotification()` | System log entries (bottom) |
| `"system_overview"` | Full `SystemOverview` | `systemOverviewStore.setOverview()` | Admin page (not in new design main view) |
| `"below_threshold"` | `{type, items: [{asset, reason}]}` | Not currently handled in dispatch | **UNUSED** — could surface as notifications |
| `"error"` | `{type, message}` | Not currently handled in dispatch | Should show in system log |
| `"validation_result"` | `{type, valid, message?}` | Not currently handled in dispatch | Form validation feedback |
| `"echo"` | `{type, data}` | Not currently handled in dispatch | Debug only |

### 4.2 Outbound Messages (Client → Server)

| Command | Payload Fields | Trigger |
|---|---|---|
| `TAKEN_SKIPPED` | `{type:"command", command:"TAKEN_SKIPPED", action:"TAKEN"\|"SKIPPED", signal_id, asset, direction, user_id}` | TAKEN/SKIP button on signal card |
| `ACTIVATE_AIM` | `{type:"command", command:"ACTIVATE_AIM", aim_id, user_id}` | AIM card activate button |
| `DEACTIVATE_AIM` | `{type:"command", command:"DEACTIVATE_AIM", aim_id, user_id}` | AIM card deactivate button |
| `validate_input` | `{type:"validate_input", input_type, value, context}` | Form validation (inline) |

### 4.3 Reconnection Behavior

| Parameter | Value |
|---|---|
| Base delay | 2000ms |
| Max delay | 30000ms |
| Backoff | Exponential (2x per retry) |
| Max retries | Infinity |
| Disconnect banner delay | 4000ms |
| Eviction code | 4001 (no reconnect) |
| Max sessions per user | 3 |

---

## 5. REST API CALLS

### 5.1 Existing Endpoints

| Endpoint | Method | Request | Response | When Called | New GUI Element |
|---|---|---|---|---|---|
| `/api/health` | GET | — | `HealthResponse {status, uptime_seconds, last_signal_time, active_users, circuit_breaker, api_connections, last_heartbeat}` | Every 30s by `CircuitBreakerCell` | Circuit breaker status (if shown) |
| `/api/status` | GET | — | `{status, uptime_seconds, processes, active_ws_sessions, api_connections}` | Not currently called from frontend | Possible backend for expanded status |
| `/api/dashboard/{user_id}` | GET | — | `DashboardSnapshot` (full 14-field payload) | On mount + 10s polling (WS fallback) | ALL panels (REST fallback) |
| `/api/system-overview` | GET | — | `SystemOverview` | On `SystemOverviewPage` mount | Admin page |
| `/api/processes/status` | GET | — | `ProcessesStatus {timestamp, processes, blocks, locked_strategies, api_connections}` | Every 15s on `ProcessesPage` | Processes page |
| `/api/reports/types` | GET | — | `ReportType[]` | On `ReportsPage` mount | Reports page |
| `/api/reports/generate` | POST | `{report_type, user_id, params}` | `ReportResult` | User clicks Generate | Reports page |
| `/api/validate/input` | POST | `{input_type, value, context}` | `{valid, message?}` | Form validation | Settings/config forms |
| `/api/validate/asset-config` | POST | `{asset_config}` | `{valid, errors?}` | Asset config validation | Config page |
| `/api/notifications/preferences/{user_id}` | GET | — | Preferences dict | Not called from current frontend | Settings page |
| `/api/notifications/preferences` | POST | `{user_id, preferences}` | `{status}` | Not called from current frontend | Settings page |
| `/api/notifications/read` | POST | `{notif_id, user_id}` | `{status}` | Not called from current frontend | Mark notification read |
| `/api/notifications/test` | POST | `{user_id, event_type, priority, message}` | `{status}` | Not called from current frontend | Admin test |

### 5.2 API Client Code

**File:** `captain-gui/src/api/client.ts`

```typescript
const BASE = "/api";
// Methods: health(), status(), dashboard(userId), systemOverview(),
//          processesStatus(), reportTypes(), generateReport(),
//          validateInput(), validateAssetConfig()
```

**Vite proxy:** `/api/*` → `http://localhost:8000`, `/ws/*` → `ws://localhost:8000`

---

## 6. STYLING PATTERNS

### 6.1 CSS Variables (Dark Mode)

**File:** `captain-gui/src/index.css`

```css
/* Surfaces */
--background: #060608;        /* Page bg */
--card: #0a0a0c;              /* Panel bg */
--card-elevated: #111113;     /* Elevated card bg */
--muted: #18181b;             /* Muted bg, borders */

/* Text tiers (4 levels) */
--foreground: #e4e4e7;        /* Primary text */
--muted-foreground: #71717a;  /* Secondary text */
--dim-foreground: #52525b;    /* Tertiary text */
--ghost-foreground: #3f3f46;  /* Quaternary (timestamps, labels) */

/* Borders */
--border: #18181b;
--border-subtle: #111113;

/* Status colors */
--green: #4ade80;             /* Positive P&L, ACTIVE, GO */
--red: #f87171;               /* Negative P&L, DANGER, LOSS */
--amber: #fbbf24;             /* WARNING, caution */
--blue: #60a5fa;              /* INFO, market stream */

/* Tinted backgrounds (10-12% opacity) */
--green-tint: rgba(74, 222, 128, 0.1);
--red-tint: rgba(248, 113, 113, 0.1);
--amber-tint: rgba(245, 158, 11, 0.12);
--blue-tint: rgba(59, 130, 246, 0.12);

/* Layout */
--radius: 3px;
--brand: #16a34a;
```

### 6.2 Tailwind Config

**File:** `captain-gui/tailwind.config.js`

- All colors use CSS variables (dynamic theming)
- Legacy `captain-*` color namespace for backward compat
- Custom animations: `collapsible-down`/`collapsible-up` (200ms)
- Plugin: `tailwindcss-animate`
- Dark mode: `class` strategy

### 6.3 Font

```css
font-family: 'SF Mono', SFMono-Regular, Consolas, 'Liberation Mono', Menlo, monospace;
```

### 6.4 Component Conventions

- **Panels:** 3px accent bar (green/blue/gray), 11px title tracking 0.05em
- **Badges:** 5 variants (go/danger/warning/info/neutral), 2 sizes
- **Text sizes:** 9px (micro), 10px (tiny), 11px (label), 12px (body), 13px (emphasis)
- **Spacing:** 1px grid gaps, 8-10px cell padding
- **Borders:** 1px `#18181b` or `#111113`
- **Status dots:** 5 states (ok/warning/danger/info/off) with optional pulse

---

## 7. NEW ELEMENTS — GAP ANALYSIS

Everything visible in the new GUI that does NOT exist in the current frontend.

### 7.1 Candlestick Chart (CRITICAL — Largest New Feature)

**What:** Full interactive candlestick chart with OHLC bars, overlay lines, pan/zoom.

**What's needed:**
- **Charting library** — Recommend [lightweight-charts](https://github.com/nickvdyck/lightweight-charts-react-wrapper) (TradingView's open-source library) or [TradingView widget](https://www.tradingview.com/widget/)
- **NEW REST endpoint:** Historical bar data. Options:
  1. `/api/bars/{asset}?timeframe=15s&limit=500` — proxy to TopstepX `retrieveBars` API
  2. Stream 15s bars via new WS message type `bar_update`
- **NEW Zustand store:** `chartStore` for bar data, selected asset, timeframe, overlays
- **NEW WS message type:** `bar_update` for real-time bar streaming (or use existing `live_market` to build bars client-side from ticks)

### 7.2 Opening Range (OR) Overlay Lines

**What:** OR Upper and OR Lower horizontal lines on the chart, with `INSIDE OR` / `BREAKOUT` labels.

**What's needed:**
- **NEW WS message type:** `or_status` with payload `{or_high, or_low, or_state, or_direction, session}`
- **Backend source:** `captain-online/captain_online/blocks/or_tracker.py` already computes this. Need to publish via Redis → Command → GUI
- Can derive from existing `p3_session_event_log` entries for historical OR ranges
- **Recommendation:** New WS subscription, updates per-session

### 7.3 Pipeline Status Tracker

**What:** Visual pills showing signal generation pipeline stage: `WAITING` → `OR FORMING` → `SIGNAL GEN` → `EXECUTED`

**What's needed:**
- **NEW WS message type:** `pipeline_status` with payload `{stage, asset, timestamp}`
- **Backend source:** OR tracker state machine transitions + Online orchestrator stage
- **Recommendation:** New field in dashboard snapshot OR dedicated WS event
- **New store field:** `dashboardStore.pipelineStage` or separate small store

### 7.4 Auto Trade Toggle

**What:** Toggle switch to enable/disable auto-execution.

**What's needed:**
- **NEW command type:** Add `SET_AUTO_EXECUTE` to `COMMAND_TYPES`
- **NEW backend handler:** In `b1_core_routing.route_command()`, toggle runtime flag
- **NEW in dashboard snapshot:** `auto_execute: boolean` field so GUI can reflect current state
- **NEW REST endpoint (optional):** `GET /api/auto-execute` to read current state

### 7.5 Profit Target Tracking

**What:** `TARGET: $4,900` → `REMAINING: $3,312.50` with progress bar and "90 trading days to target" calculation.

**What's needed:**
- **Backend:** Expose `starting_balance` and `profit_target` from `p3_d08_tsm_state.topstep_state` JSON in the `tsm_status` payload
- **Fix in `_get_tsm_status()`:** Add `starting_balance` to the returned dict (it's already queried but not included)
- **Frontend:** Derive `remaining = target - (current_balance - starting_balance)`, `days_to_target = remaining / avg_daily_pnl`
- **Recommendation:** Modify existing `TsmStatus` interface + `_get_tsm_status()` backend function

### 7.6 OEL Switch / Profit Switch Display

**What:** TopstepX-specific risk parameters (Open Equity Limit, Profit Switch) shown in risk panel.

**What's needed:**
- **Backend:** Read from TopstepX account data via REST API or UserStream
- The `_user_stream.account_data` already has these fields if TopstepX sends them
- **NEW fields in dashboard snapshot:** `oel_switch`, `profit_switch` (or embed in `tsm_status`)
- **Recommendation:** Add to existing `_get_tsm_status()` or create new `_get_account_rules()` sub-query

### 7.7 Asset Full Name Display

**What:** "MES Micro E-mini S&P" — full descriptive name, not just ticker.

**What's needed:**
- **Frontend only:** Static mapping of contract symbols to full names
- ```typescript
  const ASSET_NAMES: Record<string, string> = {
    MES: "Micro E-mini S&P", ES: "E-mini S&P 500",
    MNQ: "Micro E-mini Nasdaq", NQ: "E-mini Nasdaq 100",
    MYM: "Micro E-mini Dow", MGC: "Micro Gold",
    NKD: "Nikkei", ZB: "30-Year Treasury", ZN: "10-Year Treasury",
    M2K: "Micro Russell 2000",
  };
  ```
- **Recommendation:** Frontend constant — no backend change needed

### 7.8 MODELS Page

**What:** Visible as a tab in the top nav — likely shows AIM states, regime panel, model validation.

**What's needed:**
- **Frontend:** New page component at `/models` route
- **Data:** Can reuse existing `aimStates`, `regimePanel`, and `systemOverview.diagnostic_health` data
- **Recommendation:** New page, existing stores. The current `AimRegistryCell` and `RegimeCell` content can be moved/expanded here

### 7.9 CONFIG Page

**What:** Visible as a tab in the top nav — likely shows strategy parameters, account config, system settings.

**What's needed:**
- **Frontend:** New page component at `/config` route
- **Data:** Can reuse `api.processesStatus()` for locked strategies, add new endpoints for editable config
- **Recommendation:** New page. For display-only config: existing data. For editable config: new endpoints

### 7.10 Order History Tab

**What:** "ORDER HISTORY" tab in the trade log area.

**What's needed:**
- **NEW REST endpoint:** `/api/orders/{user_id}` — could proxy TopstepX `get_order_history()` from `shared/topstep_client.py` or query `p3_d03_trade_outcome_log` for all trades (not just open)
- **Recommendation:** New endpoint returning closed trades from `p3_d03_trade_outcome_log WHERE outcome IS NOT NULL`

### 7.11 Performance Tab

**What:** "PERFORMANCE" tab showing aggregated trading metrics.

**What's needed:**
- **NEW REST endpoint:** `/api/performance/{user_id}` — aggregate from `p3_d03_trade_outcome_log`
- Metrics: total P&L, win rate, profit factor, Sharpe-like ratio, drawdown curve, equity curve
- **Recommendation:** New endpoint. Consider caching — expensive aggregate query

### 7.12 Session Equity Curve

**What:** Possible small equity curve visible in the risk panel area.

**What's needed:**
- **NEW:** Time-series of equity values throughout the session
- Could build from trade outcomes + starting balance
- **Recommendation:** Derive from `openPositions` P&L snapshots or new `equity_history` WS stream

### 7.13 Countdown Timers

**What:** The "90 trading days to target" and possibly session countdown timers.

**What's needed:**
- **Frontend only:** Compute from `session_registry.json` session times + current time
- OR range countdown: derive from OR tracker state (`or_end_time - now`)
- **Recommendation:** Frontend computation from existing data + `config/session_registry.json`

### 7.14 Connection Health Log Messages

**What:** Log entries like "Websocket connected to Topstep gateway", "Auto connection restored after X minutes", "Redis connection restored".

**What's needed:**
- **Backend:** Publish infrastructure events as notifications instead of just logging them
- Add `route_notification()` calls in `api.py` (WS open/close), `orchestrator.py` (Redis reconnect), `b3_api_adapter.py` (API health changes)
- **Recommendation:** Straightforward — add notification publishing at key lifecycle points in existing code

---

## Summary Table — New vs Existing

| Category | Existing (Reuse) | Must Fix First (Broken) | Modified (Extend) | New (Build) |
|---|---|---|---|---|
| **Data** | liveMarket, aimStates (with coercion), regimePanel, apiStatus, notifications | direction (int→string) on openPositions + pendingSignals + signals; tp_level/sl_level null on positions; daily_pnl/cumulative_pnl null on capitalSilo; point_value missing on positions; decay level null | tsmStatus (add starting_balance, profit_target), dashboard snapshot (add auto_execute, pipeline_stage, daily_trade_stats) | Bar data endpoint, OR status WS event, pipeline status WS event, order history endpoint, performance endpoint |
| **Stores** | notificationStore | dashboardStore ingestion (direction normalization at setSnapshot/addSignal boundary) | dashboardStore (add selectedAsset, pipelineStage, autoExecute) | chartStore (bars, timeframe, overlays) |
| **Components** | notification log, status dots | ProximityBar (remove hardcoded 50), signal cards (direction display), TopBar metrics (need closed-trade stats) | Top bar (new nav), trade table (add tabs) | Candlestick chart, OR overlays, pipeline tracker, auto-trade toggle, asset selector, timeframe pills, equity curve |
| **Pages** | Settings | Dashboard (fix broken cells before restyle) | — | MODELS page, CONFIG page |
| **WS Events** | live_market, command_ack, notification | signal (direction is int), dashboard (multiple null fields) | Add handling for `error` and `below_threshold` types | or_status, pipeline_status, bar_update |
| **REST Endpoints** | health, system-overview, processes/status, reports, validate | `/api/dashboard` (fix null fields) | `/api/dashboard` (extend payload) | `/api/bars/{asset}`, `/api/orders/{user_id}`, `/api/performance/{user_id}` |

### Priority Order for Integration

1. **Fix backend data bugs first** — direction normalization, TP/SL storage, P&L computation (BUG-01 through BUG-04)
2. **Extend existing endpoints** — add starting_balance, profit_target, daily_trade_stats, point_value to dashboard snapshot
3. **Build new backend endpoints** — bars, OR status, pipeline status, order history, performance
4. **Build new frontend** — chart, overlays, new pages, restyled layout
