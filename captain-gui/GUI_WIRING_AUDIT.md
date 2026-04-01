# Captain GUI — Full UI Wiring Audit

**Date:** 2026-03-31
**Branch:** feature/replay-tab
**Scope:** All 36 .jsx files in src/components/ and src/pages/, 7 Zustand stores, WebSocket hook, API client

---

## Master Issue Table (Prioritized)

### CRITICAL — Functionally broken, user-facing deception

| # | Component | Element | What it should do | Actual behavior |
|---|-----------|---------|-------------------|-----------------|
| C1 | **SignalExecutionBar** | Auto Trade toggle `onClick` | Toggle `AUTO_EXECUTE` on the backend | **No-op.** `setAutoExecute` only writes Zustand local state. No API call, no WS message sent. Backend reads `AUTO_EXECUTE` from env var. User thinks they control trade execution but the toggle does nothing. |
| C2 | **MarketTicker** | 9 non-MES ticker prices | Display live per-asset prices | **Hardcoded stale numbers.** Only MES reads `liveMarket`. The other 9 tickers show static values like `19284.83`, `5429.65` that never update. Store only provides a single `liveMarket` object, not per-asset. |
| C3 | **DashboardPage** | `DEV_MOCK_ENABLED = true` | Gate mock data on dev mode | **Always true.** Not gated on `import.meta.env.DEV`. A production build will inject mock data and skip live API polling. |
| C4 | **SettingsPage** | Theme toggle button | Switch dark/light theme | **Cosmetic only.** Writes to localStorage and updates label, but no `useEffect` applies a class to `<html>` or `<body>`. Zero visual change. |

### HIGH — Data displayed incorrectly or misleadingly

| # | Component | Element | What it should do | Actual behavior |
|---|-----------|---------|-------------------|-----------------|
| H1 | **MarketTicker** | Asset list (MCL, 6E shown) | Show the 10 active traded assets | **Wrong assets.** MCL and 6E are P1-eliminated. **M2K and ZB are active but missing** from the ticker bar. |
| H2 | **TopBar** | QDB + Redis health dots | Show independent service health | **All 3 non-API dots mirror WS `connected`.** If WS is up but QDB/Redis are down, they still show green. |
| H3 | **TopBar** | TRADING badge | Reflect actual trading state | **Always shows "TRADING"** in green regardless of `autoExecute`, `pipelineStage`, or system state. |
| H4 | **TradingViewWidget** | M2K chart symbol | Show Micro Russell 2000 chart | **M2K missing from `TV_SYMBOLS`.** Falls through to MES chart. User sees S&P when they selected Russell. |
| H5 | **ChartPanel** | Timeframe selector | Let user change chart timeframe | **Locked to 5m.** `USE_CUSTOM_CHART = false` hides `TimeframeSelector`. Nothing else calls `setTimeframe`. TradingView widget reads it but user can never change it. |
| H6 | **TradeLog** | Trade history table | Show completed trades with duration, final P&L | **Shows `openPositions` instead.** Named "TRADE LOG" but reads open (not closed) trades. Duration always "---". Header says "TICK" but rows show asset_id. |
| H7 | **ActivePosition** | Current price / tick count | Show price for the position's asset | **`liveMarket` is asset-agnostic.** If position is NQ but `liveMarket` streams MES data, price/ticks/P&L color are all based on the wrong asset. |
| H8 | **RiskPanel** | R:R Ratio | Show risk-reward ratio | **Divides by negative `avg_loss`**, producing negative ratio. Also divides by zero if `avg_loss === 0` -> renders "Infinity". Should use `Math.abs`. |
| H9 | **RiskPanel** | Account balance rows | Match account to TSM data | **Uses array index**, not account ID. `accounts[]` (hardcoded) and `tsmStatus[]` (from backend) are independently sourced -- order/length not guaranteed to match. |
| H10 | **SignalCards** | Session footer P&L | Color green/red by sign | **Always green.** `text-[#10b981]` is hardcoded. Negative daily P&L still renders green. |
| H11 | **ReplaySummary** | What-If button `onClick` | Send config to backend for comparison | **Sends camelCase keys** (`budgetDivisor`, `tpMultiple`) while `handleRun` in ReplayConfigPanel converts to snake_case (`budget_divisor`, `tp_multiple`). Backend likely rejects/ignores. |
| H12 | **ReplaySummary vs WhatIfComparison** | PnL totals | Show consistent PnL numbers | **Inconsistent.** ReplaySummary multiplies `pnl_per_contract * contracts`. WhatIfComparison sums raw `pnl` without multiplication. Comparing "Original" between the two shows different numbers. |

### MEDIUM — Partial functionality, UX confusion, or incorrect behavior

| # | Component | Element | What it should do | Actual behavior |
|---|-----------|---------|-------------------|-----------------|
| M1 | **SystemLog** | Timestamps | Display in America/New_York | Uses `toLocaleTimeString()` without timezone. Shows browser-local time, violating system-wide ET rule. |
| M2 | **RiskPanel** | Header/footer time | Display in America/New_York | Shows **UTC** (`timeZone: "UTC"`) while TopBar shows ET. Contradicts system convention. |
| M3 | **TradeLog** | Entry time format | Display in America/New_York | No timezone specified. Uses browser default. |
| M4 | **SimulatedPosition** | Contract count "xN" | Show position size | **Always null.** Store sets `contracts: null` on breakout, never updates from `sizing_complete`. The "xN" display never appears. |
| M5 | **PipelineStepper** | B3 (AIM) + B5C (CB) stages | Show pipeline progress | **Always "pending."** No store event populates `pipelineStages.B3` or `B5C`. Only B1, B2, B4, B5, B6 ever transition. |
| M6 | **ReplayConfigPanel** | NumberInput fields during replay | Disable all config during active replay | **Inconsistent.** Date/session/riskGoal/CB are disabled. Capital/budgetDivisor/sizing params are NOT disabled. Editable but changes have no effect. |
| M7 | **ModelsPage, HistoryPage** | Page data on direct navigation | Show data regardless of entry path | **Empty if user navigates directly** (e.g., bookmark). These pages have no independent data fetch; they rely on DashboardPage's WebSocket being mounted first. |
| M8 | **HistoryPage** | Trade Outcomes + System Events tabs | Show historical data | **Permanently empty.** `data: []` hardcoded. No backend call, no store selector, no WS event populates these tabs. |
| M9 | **ChartPanel** | OR state badge | Show current OR status | **Defaults to "INSIDE OR"** before data arrives, implying active OR phase when system may not be connected. Should default to "WAITING" or "NO DATA". |
| M10 | **ActivePosition** | Tick calculation | Compute ticks from price distance | **Incorrect formula.** `(pointValue > 100 ? 1 : 0.25)` as tick divisor is wrong for MGC (0.10), MYM (1.0), NKD (5.0), ZB (1/32), ZN (1/64). |
| M11 | **DashboardStore** | Account list | Discover accounts dynamically | **Hardcoded array** with 2 specific account IDs. No API fetch. |
| M12 | **ReplayHistory** | History entries with hover styling | Click to reload a past replay | **No onClick handler.** Hover effect implies interactivity that doesn't exist. |
| M13 | **ReplayConfigPanel** | NumberInput `parseFloat(value) \|\| 0` | Allow entering zero | **Zero snaps to 0 via falsy check but budgetDivisor=0 would cause division-by-zero on backend.** No validation guard. |
| M14 | **SignalCards** | Win % fallback | Show "---" when no stats | Produces **`---%`** (em-dash + percent sign) due to unconditional `%` suffix. |

### LOW — Dead code, minor edge cases, cosmetic issues

| # | Component | Element | Issue |
|---|-----------|---------|-------|
| L1 | **TopBar** | `currentAccount` | Computed but never rendered -- dead code |
| L2 | **RiskPanel** | `openPositions`, `apiStatus` selectors | Destructured from store but never used in JSX |
| L3 | **notificationStore** | `filter` + `setFilter` | Defined in store but never used by any component. SystemLog uses local `useState` instead. |
| L4 | **chartStore** | `setBars` action | Never called anywhere. Only `addBar` is used. |
| L5 | **DashboardPage** | `sendCommand` from useWebSocket | Destructured but never used (silenced with `void`) |
| L6 | **ConfigPage** | Entire page | Placeholder -- "pending backend integration". No state, no handlers, no data. |
| L7 | **ProcessesPage** | `loading` selector | Destructured from store but never rendered. No loading indicator. |
| L8 | **AssetCard** | `status === "blocked"` conditional | Dead render path -- store never sets status to "blocked". |
| L9 | **CandlestickChart** | `fitContent()` on every bar | Prevents user from scrolling back in chart history. Snaps forward on each tick. |
| L10 | **TradingViewWidget** | Widget cleanup | `innerHTML = ""` without calling dispose. Leaks old widget timers/listeners on asset/timeframe change. |
| L11 | **ReplaySummary** | Save button | No loading state, no success/error feedback, no disabled state during save. Can be clicked multiple times. |
| L12 | **ReplaySummary** | Exit reason badge | Everything non-TP gets red styling, including neutral exits like TIMEOUT/EOD. |
| L13 | **BlockDetail B5** | `s.contracts ?? s.total_pnl != null ? ...` | Operator precedence: `??` is lower than `!=`, so ternary never executes when `s.contracts` is non-nullish. |
| L14 | **ChartPanel** | `liveMarket?.change >= 0` when null | `null >= 0` is `true` in JS -- green class applied before data arrives. |
| L15 | **ChartPanel** | Hardcoded strings | `"SYS:SIGNAL_ENGINE v3.2.1"`, `"PROP:150K_CHALLENGE"` never update. |
| L16 | **RiskPanel** | Hardcoded strings | `"SYS:RISK_MGR v2.4.1"`, `"PROP:150K_CHALLENGE"` same issue. |
| L17 | **RiskPanel** | Net Ticks column | Permanently hardcoded to em-dash. Not wired to any data source. |
| L18 | **RiskPanel** | `targetPct` | Can go negative when `cumulativePnl` < 0. CSS treats negative width as 0 (cosmetically OK but semantically wrong). |
| L19 | **TradingViewWidget** | `memo()` wrapper | No props to memoize. Store changes via hooks bypass memo. Does nothing. |
| L20 | **3 chart files** | Entire components | Dead code -- `USE_CUSTOM_CHART = false` means TimeframeSelector, ChartOverlayToggles, CandlestickChart never render. |
| L21 | **CandlestickChart** | VWAP overlay | Toggle exists in UI/store but chart never reads `overlays.vwap`. Dead feature. |
| L22 | **CandlestickChart** | Position overlays | Only draws for `openPositions[0]`. Positions 2-5 get no entry/SL/TP lines. |
| L23 | **ReplayConfigPanel** | Speed pills | Do NOT notify backend via `api.replayControl("speed", ...)`. Only PlaybackControls does. |
| L24 | **SystemLog** | Error `notif_id` | `error-${Date.now()}` -- two errors in same ms get duplicate React keys. |
| L25 | **CollapsiblePanel** | Accessibility | No `aria-expanded` / `aria-controls` on toggle button. |
| L26 | **SignalCards** | NEUTRAL direction | Direction `0` -> `"NEUTRAL"` gets red (SHORT) styling since only "LONG" gets green. |
| L27 | **API client** | 8 unused endpoints | `health`, `status`, `validateInput`, `validateAssetConfig`, `bars`, `orders`, `performance`, `gitPull` -- not called by any store or component. |

---

## Cross-Reference: Store <-> Component Wiring

| Store State | Set By | Read By | Issue |
|---|---|---|---|
| `dashboardStore.filter` | `setFilter` action | **Nothing** | Dead state |
| `dashboardStore.warmupGauges` | `setSnapshot` | **Nothing** | Set but never read by any component |
| `dashboardStore.scalingDisplay` | `setSnapshot` | **Nothing** | Set but never read by any component |
| `dashboardStore.decayAlerts` | `setSnapshot` | HistoryPage | OK (but HistoryPage has no independent fetch) |
| `dashboardStore.lastAck` | `setCommandAck` | **Nothing** | Set but never read by any component |
| `chartStore.setBars` | **Nothing** | CandlestickChart (dead code) | Dead action |
| `notificationStore.filter` | `setFilter` | **Nothing** | Dead -- SystemLog uses local state |
| `replayStore.activeSimPosition.contracts` | Set to `null` on breakout | SimulatedPosition | **Never updated** from sizing_complete |
| `replayStore.pipelineStages.B3` | **Nothing** | PipelineStepper | Never populated |
| `replayStore.pipelineStages.B5C` | **Nothing** | PipelineStepper | Never populated |

---

## WebSocket Message -> Store -> Component Flow

| WS Message Type | Store Action | Components Affected | Status |
|---|---|---|---|
| `dashboard` | `setSnapshot` | All dashboard components | **OK** but only if DashboardPage is mounted |
| `live_market` | `setLiveMarket` | MarketTicker, ChartPanel, ActivePosition | **BROKEN** -- single-asset only, no per-asset keying |
| `signal` | `addSignal` | SignalCards | OK |
| `command_ack` | `setCommandAck` | **Nothing reads `lastAck`** | Dead flow |
| `notification` | `addNotification` | SystemLog | OK |
| `error` | `addNotification` | SystemLog | OK (potential duplicate key) |
| `below_threshold` | `addNotification` | SystemLog | OK |
| `or_status` | `setOrStatus` | ChartPanel | OK |
| `pipeline_status` | `setPipelineStage` | SignalExecutionBar | OK |
| `bar_update` | `addBar` | CandlestickChart (dead code) | Dead -- custom chart disabled |
| `system_overview` | `setOverview` | SystemOverviewPage | OK |
| `replay_*` | `handleWsMessage` | All replay components | OK |

---

## Summary

**Total issues found:** 4 CRITICAL, 12 HIGH, 14 MEDIUM, 27 LOW

The most impactful cluster is the **dashboard data display** (hardcoded prices, wrong assets, asset-agnostic `liveMarket`, misleading health dots) and the **non-functional controls** (Auto Trade toggle, theme toggle).
