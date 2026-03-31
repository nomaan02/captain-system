# NEW GUI SETUP GUIDE

> Generated from full analysis of the Locofy-exported code cross-referenced against
> `GUI_INTEGRATION_MAP.md` and the `new_captain_gui.jpg` screenshot.
>
> **No code changes yet.** Review this document before authorizing modifications.

---

## 1. LAYOUT FIXES NEEDED

### 1.1 Critical Structural Problem: Monolithic RiskManagement.jsx

`RiskManagement.jsx` (981 lines) contains **far more than the risk panel**. Locofy exported the
entire page layout as nested absolute-positioned elements inside this single component:

| Lines | Actual Content | Positioning Hack Used |
|---|---|---|
| 4-383 | Risk Management left panel (capital, drawdown, payout, stats, accounts, risk params) | Normal flow inside `w-[643.4px] h-[795.4px]` container |
| 384-590 | Signal & Execution bar + signal cards + session stats (center-bottom) | `absolute right-[-975.5px] bottom-[-257.9px]` — placed ~976px to the right of its parent |
| 591-675 | Top navigation bar (time, nav tabs, account selector, status dots) | `absolute top-[-28px] right-[-975.9px]` — placed ~976px right and ~28px above parent |
| 703-875 | Market ticker strip (MES, MNQ, ES, NQ, MYM, MGC, NKD, ZN, MCL, 6E tabs) | `overflow-hidden` flex inside the absolute-positioned header |
| 888-937 | Chart header (asset name, bid/ask, volume) + chart placeholder ("Placeholder" text) | Nested absolutely inside the header |
| 938-967 | OR Upper/Lower display + INSIDE OR badge | `absolute bottom-[-476.6px]` — pushed 477px below chart header |

**This absolute-positioning approach will break at every viewport.** The elements are only visually
correct at the exact pixel dimensions Locofy captured from the Figma frame (~1920px wide). At any
other size, these sections will detach, overlap, or vanish.

### 1.2 Fixed Pixel Widths That Must Become Proportional

| Element | Current | Problem | Fix |
|---|---|---|---|
| `RiskManagement` root | `w-[643.4px] h-[795.4px]` | Fixed pixel box, won't resize | Use `flex` column with `min-w-[580px] max-w-[660px] w-[33%]` or grid column |
| Signal & Execution `<section>` | `w-[975.7px]` | Fixed width, absolute positioned | Remove absolute pos; make grid/flex child |
| Top nav `<header>` | `w-[976.1px]` | Fixed width, absolute positioned | Remove absolute pos; make full-width top bar |
| Inner nav bar | `w-[1927.2px]` at line 595 | Wider than any display — Locofy artifact | Replace with `w-full` flex container |
| `FrameComponent` wrapper | `w-[975.7px]` | Fixed center width | `flex-1` or grid-assigned column |
| `SystemMessages` root | `w-[303px]` | Fixed right column | `min-w-[280px] max-w-[320px] w-[20%]` or grid column |
| Main layout gap | `gap-[5.3px]` | Arbitrary sub-pixel gap | `gap-1` (4px) or `gap-1.5` (6px) |
| Outer container padding | `pb-[253.4px]` | Arbitrary bottom padding hides overflow | Remove — use proper layout height |
| Left+center container | `max-w-[calc(100%_-_308px)]` | Hardcoded to SystemMessages width | Use flex or grid instead |

### 1.3 Recommended Top-Level Grid Layout

Replace the current flex-based layout in `OptimizedOptimizedOptimizedAdaptContainerContent.jsx`
with CSS Grid. The page has four distinct regions:

```
+------------------------------------------------------------------+
|                        TOP BAR (full width)                       |
+------------------------------------------------------------------+
|                    MARKET TICKER STRIP (full width)               |
+------------------+-----------------------------+-----------------+
|                  |                             |                 |
|  RISK PANEL      |  CENTER (chart + position)  |  RIGHT COLUMN   |
|  (left)          |                             |  (signals +     |
|                  |                             |   trade log +   |
|                  |                             |   system log)   |
+------------------+-----------------------------+-----------------+
|              SIGNAL & EXECUTION BAR (spans center + right)        |
+------------------------------------------------------------------+
```

**Recommended CSS Grid definition:**

```css
.page-grid {
  display: grid;
  grid-template-columns: minmax(580px, 1fr) minmax(500px, 2fr) minmax(280px, 1fr);
  grid-template-rows: auto auto 1fr auto;
  grid-template-areas:
    "topbar    topbar    topbar"
    "ticker    ticker    ticker"
    "risk      center    right"
    "risk      execbar   execbar";
  height: 100vh;
  overflow: hidden;
  background: #0a0f0d;
}
```

### 1.4 Per-Panel Resize Behavior

| Panel | Grid Area | Resize Behavior | Min Width | Max Width | Height |
|---|---|---|---|---|---|
| Top Bar | `topbar` | Full width, fixed height | 100% | 100% | `auto` (~37px) |
| Market Ticker | `ticker` | Full width, horizontal scroll for overflow | 100% | 100% | `auto` (~35px) |
| Risk Panel | `risk` | Flex-grow 1, vertical scroll for overflow | 580px | 660px | Stretch to fill rows 3-4 |
| Center (Chart + Position) | `center` | Flex-grow 2, chart fills available space | 500px | none | `1fr` |
| Right Column | `right` | Flex-grow 1, vertical scroll | 280px | 340px | `1fr` |
| Signal & Exec Bar | `execbar` | Spans center+right, fixed height | — | — | `auto` (~100px) |

### 1.5 Viewport Breakpoint Issues

| Viewport | Issue | Mitigation |
|---|---|---|
| **1440px** | Risk panel (580px) + center (500px min) + right (280px) = 1360px. Fits, but tight. Ticker strip will overflow. | Horizontal scroll on ticker. May need to collapse right column behind a toggle. |
| **1920px** | Comfortable fit. Risk 620px + center 980px + right 320px. | Default target — should work perfectly. |
| **2560px** | Excess space. Center panel grows, chart gets very wide. | Cap center at `max-w-[1200px]` or let chart fill. Risk and right panels can grow slightly. |
| **< 1360px** | Cannot fit all three columns. | Either (a) stack risk panel above center, or (b) make risk panel collapsible, or (c) set `min-width: 1440px` on body with horizontal scroll. Recommend (c) for a trading dashboard — traders use large monitors. |

### 1.6 Additional Layout Artifacts to Fix

| Issue | Location | Fix |
|---|---|---|
| Nested `<main>` inside `<main>` | `OptimizedOptimizedOptimizedAdaptContainerContent.jsx:8-9` | Replace outer with `<div>`, inner with grid children |
| `<section>` used for signal bar | `RiskManagement.jsx:384` | Extract to own component |
| `<header>` used for chart area | `RiskManagement.jsx:591` | Extract to own component; `<header>` is semantic for page header only |
| `mq1125:hidden` hides SystemMessages | `SystemMessages.jsx:6` | Locofy breakpoint class — replace with proper responsive logic or remove |
| `mq1125:pl-[5.3px]` padding shifts | `OptimizedOptimizedOptimizedAdaptContainerContent.jsx:8` | Remove — Locofy artifact |
| `mt-[-170px]` negative margin | `FrameComponent.jsx:6` | Locofy overlap hack — remove, use proper grid placement |
| Hidden divs (display: hidden) | `SystemMessages.jsx:78-91` (empty hidden rows) | Delete — placeholder artifacts |
| `!!m-[0 important]` pattern | Multiple lines in RiskManagement.jsx | Locofy `!important` margin override artifact — clean up |
| Chart placeholder div | `RiskManagement.jsx:932-937` | Replace with chart library container |

---

## 2. INTERACTIVE ELEMENTS MAP

### 2.1 Asset Selector Tabs (Market Ticker Strip)

**Locofy component:** `RiskManagement.jsx:703-875`
- Nested inside `<nav>` elements within the `<header>` section
- Contains tabs for: MES, MNQ, ES, NQ, MYM, MGC, NKD, ZN, MCL, 6E
- Each tab is a `<div>` with static price/change values

**Current onClick:** None. All tabs are static `<div>` elements.
**Needs:** `onClick` handler on each tab wrapper div
**Store action:** `dashboardStore.setSelectedAsset(assetId)` (NEW action) + trigger backend `_get_live_market_data(asset_id)` via WS command
**API call:** Send WS message `{type: "command", command: "SET_SELECTED_ASSET", asset_id}` or switch to client-side filtering if all assets are streamed

### 2.2 Timeframe Selector Pills

**Locofy component:** NOT present in Locofy export. Visible in screenshot below chart header as `15s`, `1m`, `5m`, `15m`.
**Needs:** Build from scratch — new component
**Store action:** `chartStore.setTimeframe(tf)` (NEW store + action)
**API call:** `GET /api/bars/{asset}?timeframe={tf}&limit=500` (NEW endpoint)

### 2.3 Chart Overlay Toggles (OR Upper, OR Lower, Entry, SL, TP, VWAP)

**Locofy component:** NOT present as toggleable elements. OR values are displayed statically at `RiskManagement.jsx:938-967`.
**Needs:** Build toggle buttons from scratch; wire overlay visibility to chart rendering
**Store action:** `chartStore.toggleOverlay(name)` (NEW)
**API call:** OR data from new WS event `or_status`; Entry/SL/TP from `openPositions`; VWAP computation NEW

### 2.4 Auto Trade Toggle Switch

**Locofy component:** `RiskManagement.jsx:406-413`
```jsx
<div className="h-[21.2px] w-[42.4px] relative rounded-[43469100px] bg-[#10b981] shrink-0">
  <div className="absolute top-[3px] left-[24.3px] rounded-[43469100px] bg-[#fff] w-[15.1px] h-[15.1px]" />
</div>
```
- Pure CSS toggle indicator (green bg + white circle), no interactivity

**Current onClick:** None — decorative only
**Needs:** `onClick` or `onChange` handler on wrapper
**Store action:** `dashboardStore.setAutoExecute(bool)` (NEW action)
**API call:** WS command `{type: "command", command: "SET_AUTO_EXECUTE", enabled: true/false, user_id}` (NEW command type)
**Note:** Backend must add `SET_AUTO_EXECUTE` to `COMMAND_TYPES` and handler in `b1_core_routing.route_command()`

### 2.5 View Switcher / Navigation Tabs (Top Bar)

**Locofy component:** `RiskManagement.jsx:604-645`
- "Dashboard" — `<button>` with active styling (green bg): line 605
- "System" — `<div>` with muted styling: line 611
- "Processes" — `<div>` with muted styling: line 618
- "History" — `<button>` with hover handler: line 626
- "Reports" — `<div>` with muted styling: line 632
- "Settings" — `<div>` with muted styling: line 639

**Current onClick:** "Dashboard" and "History" have `<button>` elements with cursor-pointer but no handler. Others are `<div>` elements.
**Needs:** Replace all with React Router `<NavLink>` components matching existing route structure
**Store action:** None (routing only)
**Integration:** Map to existing routes: Dashboard `/`, System `/system`, Processes `/processes`, History `/history`, Reports `/reports`, Settings `/settings`

### 2.6 Account Selector Dropdown

**Locofy component:** `RiskManagement.jsx:676-689`
```jsx
<div className="...">PRAC-V2-551001-43861321</div>
<img src="/.svg" alt="" />  <!-- dropdown chevron -->
```
- Static text with a chevron SVG

**Current onClick:** None
**Needs:** Dropdown/select component; `onClick` to open, select handler to switch
**Store action:** `dashboardStore.setSelectedAccount(accountId)` (NEW action)
**API call:** Filters existing `tsmStatus`, `openPositions`, `payoutPanel` by account — client-side filter, no new endpoint

### 2.7 Trade Log / Order History / Performance Tabs

**Locofy component:** NOT present in Locofy export as tabs. The Trade Log content exists in `SystemMessages.jsx:9-114`, but there are no tab buttons for ORDER HISTORY or PERFORMANCE.
**Needs:** Build tab bar from scratch above the trade log content
**Store action:** Local React state for active tab
**API call:**
- TRADE LOG: Existing `openPositions` data (restyle only)
- ORDER HISTORY: `GET /api/orders/{user_id}` (NEW endpoint)
- PERFORMANCE: `GET /api/performance/{user_id}` (NEW endpoint)

### 2.8 System Log Filter Tabs (All / Errors / Signals / Orders)

**Locofy component:** `SystemMessages.jsx:124-144`
- Four `<button>` elements with cursor-pointer and hover states already defined
- "All" — active styling with filled bg: line 125
- "Errors" — outline styling: line 130
- "Signals" — outline styling: line 135
- "Orders" — outline styling: line 140

**Current onClick:** None — buttons exist but have no handlers
**Needs:** `onClick` handler on each button to set filter state
**Store action:** Local React state `activeFilter` or `notificationStore.setFilter(category)` (NEW action)
**Filter logic:** Adapt existing `guessCategory()` function from current codebase `notifications.tsx:23-27` to classify by content keywords

### 2.9 FILLED/SKIPPED Badges on Signal Cards

**Locofy component:** `RiskManagement.jsx:433-437` (FILLED badge), `RiskManagement.jsx:513-517` (ELEVATED badge)
```jsx
<div className="border-[rgba(16,185,129,0.4)]..."><div>FILLED</div></div>
<div className="border-[rgba(245,158,11,0.4)]..."><div>ELEVATED</div></div>
```
- Display-only badges. The current design shows these as status indicators, not action buttons.

**Current onClick:** None — display only
**Needs:** The TAKEN/SKIP action buttons from the current codebase (`active-signal.tsx:21-35`) should either:
  - (A) Be added as buttons that convert to FILLED/SKIPPED badges after action, or
  - (B) The signal cards show both states: pending signals get TAKE/SKIP buttons, actioned signals show FILLED/SKIPPED badges
**Store action:** Existing `dashboardStore.removeSignal(signalId)` + WS command `TAKEN_SKIPPED`
**Recommendation:** Keep action buttons on pending signals, show badges on completed signals. Requires NOT removing signals from the store after action — instead, mark them with `status: "FILLED"|"SKIPPED"`.

### 2.10 Signal Pipeline Status Pills

**Locofy component:** `RiskManagement.jsx:391-403`
```jsx
<div className="border-[#1e293b]...">WAITING</div>
<div className="border-[#1e293b]...">OR FORMING</div>
<div className="bg-[rgba(59,246,62,0.2)] border-[rgba(59,246,74,0.4)]...text-[#63f63b]">SIGNAL GEN</div>  <!-- active state -->
<div className="border-[#1e293b]...">EXECUTED</div>
```
- Four static pills. "SIGNAL GEN" has active/highlighted styling.

**Current onClick:** None — display only (correct — these should be read-only status indicators)
**Needs:** Dynamic class binding based on current pipeline stage
**Store action:** `dashboardStore.pipelineStage` (NEW field, updated from WS `pipeline_status` event)
**API call:** New WS message type `pipeline_status` from backend OR new field in dashboard snapshot

### 2.11 Chart / Table / Signals Tabs

**Locofy component:** NOT present in Locofy export. Visible in screenshot below asset name.
**Needs:** Build from scratch
**Store action:** Local React state for active view
**No API call** — switches rendering mode of existing data

### 2.12 Scrollable Regions

| Region | Locofy Component | Current Scroll | Needs |
|---|---|---|---|
| Risk Panel | `RiskManagement.jsx:4-383` | Fixed height `h-[795.4px]`, no scroll | Add `overflow-y-auto` with `flex-1` height |
| Signal Cards | `RiskManagement.jsx:416-590` | No scroll (absolute positioned) | Extract to own component, add `overflow-y-auto max-h-[calc(100vh-X)]` |
| Trade Log | `SystemMessages.jsx:9-114` | Fixed height `h-[189px]` with no scroll | Add scroll container |
| System Log | `SystemMessages.jsx:148-284` | No scroll, content overflows | Add `overflow-y-auto flex-1` |
| Market Ticker Strip | `RiskManagement.jsx:703-875` | `overflow-hidden` hides overflow | Change to `overflow-x-auto` for horizontal scroll |

### 2.13 Additional Interactive Elements

| Element | Locofy Location | Type | Current Handler | Needs |
|---|---|---|---|---|
| Status dots (API, WS, QDB, Redis) | `RiskManagement.jsx:647-669` | Display | None | Bind to `dashboardStore.apiStatus` + `dashboardStore.connected` |
| "LIVE" badge | `RiskManagement.jsx:22-24` | Display | None | Bind to `dashboardStore.connected` — show "LIVE" when true, "OFFLINE" when false |
| Account number button | `RiskManagement.jsx:691-695` | Button | `cursor-pointer` but no handler | Wire to account details or copy-to-clipboard |
| "TRADING" badge | `RiskManagement.jsx:696-700` | Display | None | Bind to TSM trading state |
| Dropdown chevron SVG | `RiskManagement.jsx:682-685` | Image | None | Wire to account dropdown open/close |

---

## 3. DATA BINDING PLAN

### 3.1 Top Bar

| UI Element | Locofy Component:Line | Store Field | Notes |
|---|---|---|---|
| Clock `19:24:46 ET` | `RiskManagement.jsx:598` | `dashboardStore.timestamp` → format with `toLocaleTimeString` | Static text "19:24:46" — replace with live value |
| "Dashboard" nav active state | `RiskManagement.jsx:605-609` | React Router `useLocation()` | Replace with `<NavLink>` |
| Account selector text | `RiskManagement.jsx:678` | `dashboardStore.apiStatus?.account_name` | Static "PRAC-V2-551001-43861321" |
| Account number button | `RiskManagement.jsx:693` | `dashboardStore.tsmStatus[0]?.account_id` | Static "Acc No. 233576334" |
| "TRADING" badge | `RiskManagement.jsx:698` | `dashboardStore.tsmStatus[0]?.trading_state` | Derive from TSM status |
| API status dot | `RiskManagement.jsx:650` | `dashboardStore.apiStatus?.api_authenticated` | Static green dot |
| WS status dot | `RiskManagement.jsx:653` | `dashboardStore.connected` | Static green dot |
| QuestDB status dot | `RiskManagement.jsx:660` | `dashboardStore.connected` (derived) | Static green dot |
| Redis status dot | `RiskManagement.jsx:665` | NEW — `dashboardStore.apiStatus?.redis_connected` | **GAP**: Redis health not in current apiStatus |
| "Last tick: 0.3s ago" | `RiskManagement.jsx:672` | `dashboardStore.liveMarket?.timestamp` → compute `Date.now() - lastTick` | Static text |

### 3.2 Market Ticker Strip

| UI Element | Locofy Component:Line | Store Field | Notes |
|---|---|---|---|
| MES price `5429.68` | `RiskManagement.jsx:717` | `dashboardStore.liveMarket?.last_price` (when asset=MES) | Currently only one asset streamed — needs multi-asset |
| MES change `-0.22%` | `RiskManagement.jsx:721` | `dashboardStore.liveMarket?.change_pct` | Same single-asset limitation |
| MNQ price `19284.83` | `RiskManagement.jsx:738` | NEW — multi-asset `liveMarket` | **GAP**: Backend streams only one asset at a time |
| ES price `5429.65` | `RiskManagement.jsx:753` | NEW — multi-asset | Same gap |
| NQ price `19283.92` | `RiskManagement.jsx:767` | NEW — multi-asset | Same gap |
| MYM price `39842.91` | `RiskManagement.jsx:788` | NEW — multi-asset | Same gap |
| MGC price `2634.16` | `RiskManagement.jsx:803` | NEW — multi-asset | Same gap |
| NKD price `38451.03` | `RiskManagement.jsx:820` | NEW — multi-asset | Same gap |
| ZN price `110.27` | `RiskManagement.jsx:835` | NEW — multi-asset | Same gap |
| MCL price `71.90` | `RiskManagement.jsx:850` | NEW — multi-asset | Same gap |
| 6E price `1.08` | `RiskManagement.jsx:865` | NEW — multi-asset | Same gap |

**GAP FLAG**: The backend `_get_live_market_data()` only streams one asset (defaults to ES). To populate all ticker tabs, either:
- (A) Backend: Stream all watchlist assets via `build_live_market_update()` for each asset (NEW)
- (B) Backend: New WS message type `multi_market` with all asset quotes bundled
- (C) Frontend: REST polling per asset (expensive, not recommended)

**New store needed**: `dashboardStore.marketQuotes: Record<string, LiveMarket>` — keyed by asset ID

### 3.3 Risk Management Panel (Left Column)

| UI Element | Locofy Component:Line | Store Field | Notes |
|---|---|---|---|
| CAPITAL `$150,000.00` | `RiskManagement.jsx:34` | `dashboardStore.tsmStatus[0]?.starting_balance` | **GAP (BUG-04 related)**: `starting_balance` queried but not returned in dict |
| EQUITY `$151,287.50` | `RiskManagement.jsx:42` | `dashboardStore.tsmStatus[0]?.current_balance` | Existing data path works |
| CUMULATIVE P&L `+$1,287.50` | `RiskManagement.jsx:49` | Derived: `current_balance - starting_balance` | **BROKEN (BUG-04)**: `capitalSilo.cumulative_pnl` always null. Derive from TSM balance delta |
| MAX DD bar (2/10 filled orange) | `RiskManagement.jsx:71-80` | `dashboardStore.tsmStatus[0]?.mdd_used_pct` | 10 bar segments — compute fill count from percentage |
| MAX DD percentage `18.1%` | `RiskManagement.jsx:84` | `dashboardStore.tsmStatus[0]?.mdd_used_pct` | |
| MAX DD used/limit text | `RiskManagement.jsx:89` | `tsmStatus[0].mdd_used` / `tsmStatus[0].mdd_limit` | |
| MAX DD floor | `RiskManagement.jsx:92` | Derived: `current_balance - mdd_limit` | |
| DAILY DD bar (0/10 filled) | `RiskManagement.jsx:103-112` | `dashboardStore.tsmStatus[0]?.daily_dd_used_pct` | Same 10-segment pattern |
| DAILY DD percentage `0.0%` | `RiskManagement.jsx:116` | `dashboardStore.tsmStatus[0]?.daily_dd_used_pct` | |
| DAILY DD used/limit text | `RiskManagement.jsx:121` | `tsmStatus[0].daily_dd_used` / `tsmStatus[0].daily_dd_limit` | |
| DAILY DD floor | `RiskManagement.jsx:124` | Derived: `current_balance - daily_dd_limit` | |
| TARGET `$4,500.00` | `RiskManagement.jsx:140` | NEW — `tsmStatus[0].profit_target` | **GAP**: Not in current dashboard snapshot |
| REMAINING `$3,212.50` | `RiskManagement.jsx:141` | Derived: `profit_target - cumulative_pnl` | Depends on profit_target + fixed starting_balance |
| Target progress bar | `RiskManagement.jsx:148-150` | Derived: `cumulative_pnl / profit_target * 100` | Width of inner gradient div |
| Target percentage `28.6%` | `RiskManagement.jsx:145` | Derived: same | |
| "~30 trading days to target" | `RiskManagement.jsx:156` | Derived: `remaining / avg_daily_pnl` | **GAP**: Needs `avg_daily_pnl` — compute from D03 closed trades or new backend field |
| Day P&L `+$0.00` | `RiskManagement.jsx:178` | `dashboardStore.capitalSilo?.daily_pnl` | **BROKEN (BUG-04)**: Always null. Must derive |
| Profit Factor `--` | `RiskManagement.jsx:180` | NEW — `daily_trade_stats.profit_factor` | **GAP**: Computed from `openPositions` only (BUG-05) |
| Avg Win `$0.00` | `RiskManagement.jsx:192` | NEW — `daily_trade_stats.avg_win` | **GAP**: Not in current snapshot |
| Avg Loss `$0.00` | `RiskManagement.jsx:194` | NEW — `daily_trade_stats.avg_loss` | **GAP**: Not in current snapshot |
| Wins `0` | `RiskManagement.jsx:204` | NEW — `daily_trade_stats.wins` | **GAP** |
| R:R Ratio `--` | `RiskManagement.jsx:210` | NEW — `daily_trade_stats.rr_ratio` | **GAP** |
| Losses `0` | `RiskManagement.jsx:219` | NEW — `daily_trade_stats.losses` | **GAP** |
| Trades `0` | `RiskManagement.jsx:227` | NEW — `daily_trade_stats.trades_today` | **GAP**: Currently computed from openPositions (BUG-05) |
| Win% `--` | `RiskManagement.jsx:235` | NEW — `daily_trade_stats.win_pct` | **GAP** |
| Net Ticks `--` | `RiskManagement.jsx:242` | NEW — `daily_trade_stats.net_ticks` | **GAP** |
| Payout ID `20319811` | `RiskManagement.jsx:259` | `dashboardStore.tsmStatus[0]?.account_id` | |
| Payout Status `--` | `RiskManagement.jsx:267` | `dashboardStore.payoutPanel[0]?.status` | |
| Payout Amount `$0.00` | `RiskManagement.jsx:275` | `dashboardStore.payoutPanel[0]?.amount` | |
| Payout Tier `Unknown` | `RiskManagement.jsx:283` | `dashboardStore.payoutPanel[0]?.tier` | |
| Method `Systematic` | `RiskManagement.jsx:291` | `dashboardStore.payoutPanel[0]?.method` | NEW field or derive from strategy config |
| Next Eligible `TBD` | `RiskManagement.jsx:299` | `dashboardStore.payoutPanel[0]?.next_eligible_date` | **GAP (BUG-14)**: Missing from backend |
| Account 1 name | `RiskManagement.jsx:312` | `dashboardStore.apiStatus?.account_name` | |
| Account 1 balance | `RiskManagement.jsx:316` | `dashboardStore.tsmStatus[0]?.current_balance` | |
| Account 1 status badge | `RiskManagement.jsx:318-319` | Derived from `tsmStatus[0].trading_state` | |
| Account 2 name | `RiskManagement.jsx:325` | `dashboardStore.tsmStatus[1]?.account_name` (if multi-account) | |
| Account 2 balance | `RiskManagement.jsx:328` | `dashboardStore.tsmStatus[1]?.current_balance` | |
| Account 2 status badge | `RiskManagement.jsx:329-330` | Derived from `tsmStatus[1].trading_state` | |
| Risk Params: Max DD | `RiskManagement.jsx:347` | `dashboardStore.tsmStatus[0]?.mdd_limit` | |
| Risk Params: Daily DD | `RiskManagement.jsx:355` | `dashboardStore.tsmStatus[0]?.daily_dd_limit` | |
| Risk Params: Max Lots | `RiskManagement.jsx:363` | NEW — `tsmStatus[0].max_lots` | **GAP**: Not in current snapshot. Read from TopstepX account rules |
| Risk Params: Consistency | `RiskManagement.jsx:371` | NEW — `tsmStatus[0].consistency_score` or derived | **GAP**: Not computed |
| Footer version/account info | `RiskManagement.jsx:379-382` | Static or `dashboardStore.apiStatus?.account_type` | Low priority |

### 3.4 Chart Area (Center)

| UI Element | Locofy Component:Line | Store Field | Notes |
|---|---|---|---|
| Asset name "MES" | `RiskManagement.jsx:900` | `chartStore.selectedAsset` or `dashboardStore.selectedAsset` | |
| Full name "Micro E-mini S&P" | `RiskManagement.jsx:903` | Frontend constant `ASSET_NAMES[selectedAsset]` | No backend change |
| Open/High prices | `RiskManagement.jsx:908` | `dashboardStore.liveMarket?.open`, `.high` | |
| Bid/Ask | `RiskManagement.jsx:911` | `dashboardStore.liveMarket?.best_bid`, `.best_ask` | |
| Volume `1,767,219` | `RiskManagement.jsx:916` | `dashboardStore.liveMarket?.volume` | |
| LAST PRICE `5429.68` | `RiskManagement.jsx:921` | `dashboardStore.liveMarket?.last_price` | |
| Change `▼ -12.14 (-0.22%)` | `RiskManagement.jsx:928` | `dashboardStore.liveMarket?.change`, `.change_pct` | |
| Chart placeholder | `RiskManagement.jsx:932-937` | NEW — `chartStore.bars[]` | **GAP**: Needs chart library + bar data endpoint |
| OR UPPER `5430.72` | `RiskManagement.jsx:943` | NEW — `dashboardStore.orStatus?.or_high` | **GAP**: OR data not published to GUI |
| OR LOWER `5428.42` | `RiskManagement.jsx:965` | NEW — `dashboardStore.orStatus?.or_low` | Same gap |
| "INSIDE OR" badge | `RiskManagement.jsx:957` | NEW — `dashboardStore.orStatus?.or_state` | Same gap |

### 3.5 Active Position (Center-Bottom)

| UI Element | Locofy Component:Line | Store Field | Notes |
|---|---|---|---|
| "Active Position" label | `FrameComponent.jsx:15` | Display when `openPositions.length > 0` | |
| Direction "LONG" badge | `FrameComponent.jsx:20` | `openPositions[0].direction` | **BROKEN (BUG-01)**: Integer, not string. Normalize: `direction > 0 ? "LONG" : "SHORT"` |
| Asset "MES 2506" | `FrameComponent.jsx:23` | `openPositions[0].asset_id` + contract month | |
| Contracts "x2" | `FrameComponent.jsx:27` | `openPositions[0].contracts` | |
| Order ID "ORD-4829" | `FrameComponent.jsx:29` | `openPositions[0].order_id` | |
| Entry price `5430.25` | `FrameComponent.jsx:39` | `openPositions[0].entry_price` | |
| Current price `5433.50` | `FrameComponent.jsx:44` | `dashboardStore.liveMarket?.last_price` or derive from P&L | |
| P&L `+$32.50 (+13t)` | `FrameComponent.jsx:50-53` | `openPositions[0].current_pnl` | Ticks: `pnl / (contracts * point_value)` — **needs point_value (BUG-03)** |
| SL `5427.00` | `FrameComponent.jsx:60` | `openPositions[0].sl_level` | **BROKEN (BUG-02)**: Always null |
| TP `5436.00` | `FrameComponent.jsx:63` | `openPositions[0].tp_level` | **BROKEN (BUG-02)**: Always null |
| Proximity bar (gradient) | `FrameComponent.jsx:68-71` | Derived from entry, current, SL, TP | Hardcoded padding values in Locofy — must be computed dynamically |
| Distance to SL `3.25pts ($130)` | `FrameComponent.jsx:75` | Derived: `(current - sl) * point_value` | Needs point_value |
| Distance to TP `5.75pts ($230)` | `FrameComponent.jsx:77` | Derived: `(tp - current) * point_value` | Needs point_value |
| Time in trade `00:04:32` | `FrameComponent.jsx:85` | Derived: `Date.now() - openPositions[0].entry_time` | |
| Lots `2` | `FrameComponent.jsx:89` | `openPositions[0].contracts` | Duplicate of x2 above |
| Fill order ID | `FrameComponent.jsx:93` | `openPositions[0].order_id` | |

### 3.6 Signal & Execution Bar

| UI Element | Locofy Component:Line | Store Field | Notes |
|---|---|---|---|
| Pipeline pills (WAITING/OR FORMING/SIGNAL GEN/EXECUTED) | `RiskManagement.jsx:391-403` | NEW — `dashboardStore.pipelineStage` | **GAP**: Needs new WS event |
| Auto Trade toggle state | `RiskManagement.jsx:410-411` | NEW — `dashboardStore.autoExecute` | **GAP**: Needs new WS command + snapshot field |
| Signal card 1: direction SHORT | `RiskManagement.jsx:420-421` | `pendingSignals[0].direction` | **BROKEN (BUG-01)**: Integer |
| Signal card 1: asset MES | `RiskManagement.jsx:425` | `pendingSignals[0].asset` | |
| Signal card 1: strategy `OR_BREAK_RS v1.3` | `RiskManagement.jsx:429` | `pendingSignals[0].strategy_name` + version | NEW field or derive from signal metadata |
| Signal card 1: FILLED badge | `RiskManagement.jsx:435` | Signal action state | **GAP**: Current code removes signals after action |
| Signal card 1: Entry/SL/TP/OR values | `RiskManagement.jsx:440-479` | `pendingSignals[0].entry_price`, `.sl_level`, `.tp_level` + OR from `orStatus` | **NOTE (BUG-11)**: `entry_price` may be missing at signal level |
| Signal card 1: P&L +$162.50 | `RiskManagement.jsx:486` | Derived from entry + current price | |
| Signal card 1: Confidence 72% | `RiskManagement.jsx:492` | `pendingSignals[0].quality_score` | |
| Signal card 2 (same structure) | `RiskManagement.jsx:496-561` | Same pattern for second signal | |
| Session P&L `+$162.50` | `RiskManagement.jsx:567` | NEW — `daily_trade_stats.total_pnl` | **GAP** |
| Win Rate `100%` | `RiskManagement.jsx:574` | NEW — `daily_trade_stats.win_pct` | **GAP** |
| Signals `2` | `RiskManagement.jsx:580` | `pendingSignals.length` or `daily_trade_stats.signals_today` | |
| Pad Comp `60%` | `RiskManagement.jsx:586` | NEW — padding/composition metric | **GAP**: Not in current data model |

### 3.7 Trade Log (Right Column)

| UI Element | Locofy Component:Line | Store Field | Notes |
|---|---|---|---|
| Trade row (time, ticker, direction, P&L, duration) | `SystemMessages.jsx:26-104` | `dashboardStore.openPositions` (but should be **closed trades**) | **BROKEN (BUG-05)**: Needs closed-trade data. Current `openPositions` only has active trades |
| Total: `$+1581 | 18 trades` | `SystemMessages.jsx:107-112` | NEW — `daily_trade_stats.total_pnl`, `.trades_today` | **GAP** |

### 3.8 System Log (Right Column)

| UI Element | Locofy Component:Line | Store Field | Notes |
|---|---|---|---|
| Filter buttons (All/Errors/Signals/Orders) | `SystemMessages.jsx:125-144` | `notificationStore.notifications` + filter | Buttons exist, need handlers |
| "SYSTEM LOG" / "TELEGRAM" tabs | `SystemMessages.jsx:119-122` | Local state for log source | TELEGRAM tab is NEW |
| Log entries with timestamps | `SystemMessages.jsx:148-284` | `notificationStore.notifications` | All entries are static — replace with mapped notification array |

### 3.9 Values Needing NEW Stores or Endpoints

| Value | Required Source | Gap Type |
|---|---|---|
| Multi-asset market quotes (all tickers) | NEW WS stream or REST polling for each asset | Backend: modify `build_live_market_update()` to stream multiple assets |
| `starting_balance` | Fix `_get_tsm_status()` to include it | Backend bug fix |
| `profit_target` | Add to `TsmStatus` from `topstep_state` JSON | Backend extension |
| `daily_trade_stats` (wins, losses, PF, avg win/loss, net ticks) | NEW computed field from D03 closed trades | Backend: new computation in `_get_capital_silo()` or new sub-query |
| `pipelineStage` | NEW WS event `pipeline_status` | Backend: publish OR tracker state changes |
| `autoExecute` state | NEW snapshot field + WS command | Backend: expose runtime `AUTO_EXECUTE` flag |
| `orStatus` (or_high, or_low, or_state) | NEW WS event `or_status` | Backend: publish OR tracker data |
| Bar data (OHLCV) | NEW REST endpoint `/api/bars/{asset}` | Backend: proxy to TopstepX `retrieveBars` or build from QuestDB |
| Order history | NEW REST endpoint `/api/orders/{user_id}` | Backend: query D03 closed trades |
| Performance metrics | NEW REST endpoint `/api/performance/{user_id}` | Backend: aggregate from D03 |
| Redis health | Add to `apiStatus` | Backend: minor extension |
| Max lots per account | Add to `TsmStatus` from TopstepX account rules | Backend: extension |
| Consistency score | Compute from trade history | Backend: new computation |
| `next_eligible_date` for payout | Add to payout query (BUG-14) | Backend bug fix |

---

## 4. CODE STRUCTURE RECOMMENDATIONS

### 4.1 Component Renaming

| Locofy Name | Recommended Name | Reason |
|---|---|---|
| `OptimizedOptimizedOptimizedAdaptContainerContent` | `DashboardPage` | Locofy triple-nested optimization artifact; matches existing `DashboardPage` naming convention |
| `RiskManagement` | Must be **split** (see 4.2) | Currently contains 6 unrelated sections |
| `FrameComponent` | `ActivePosition` | Descriptive of actual content; matches existing `ActiveSignalCell` naming pattern |
| `SystemMessages` | Must be **split** (see 4.2) | Contains both Trade Log and System Log |

### 4.2 Components That Must Be Split

#### `RiskManagement.jsx` (981 lines) → 6 components:

| New Component | Source Lines | Content |
|---|---|---|
| `TopBar.jsx` | 591-700 | Navigation tabs, clock, account selector, status dots. Extract from the `<header>` element. |
| `MarketTicker.jsx` | 703-886 | Asset price tabs (MES, MNQ, ES, etc.) + system info footer. Extract from the `<nav>` elements. |
| `ChartPanel.jsx` | 888-968 | Chart header (asset name, bid/ask, LAST PRICE), chart placeholder, OR range display. |
| `RiskPanel.jsx` | 4-383 | The actual risk management content: capital cards, drawdown, payout target, day stats, accounts, risk params. Keep this as the renamed `RiskManagement`. |
| `SignalCards.jsx` | 416-590 | Individual signal cards with entry/SL/TP/P&L and session summary stats. |
| `SignalExecutionBar.jsx` | 384-415 | Pipeline status pills, auto trade toggle. Wraps SignalCards. |

#### `SystemMessages.jsx` (293 lines) → 2 components:

| New Component | Source Lines | Content |
|---|---|---|
| `TradeLog.jsx` | 9-114 | Trade log table with time/ticker/direction/P&L/duration rows and total |
| `SystemLog.jsx` | 116-284 | System log with filter tabs (All/Errors/Signals/Orders) + timestamped entries |

### 4.3 Components That Should Be Merged or Absorbed

| Component | Recommendation |
|---|---|
| `FrameComponent.jsx` → `ActivePosition.jsx` | Rename only. Keep as separate component — it represents a distinct UI section (active position with proximity bar). However, it should be placed as a child inside `ChartPanel.jsx` layout, not as a sibling. |

### 4.4 New Components Needed (Not in Locofy Export)

| Component | Purpose | Data Source |
|---|---|---|
| `CandlestickChart.jsx` | Interactive chart using lightweight-charts or TradingView widget | `chartStore.bars` |
| `TimeframeSelector.jsx` | 15s/1m/5m/15m pills | `chartStore.timeframe` |
| `ChartOverlayToggles.jsx` | OR/Entry/SL/TP/VWAP toggle buttons | `chartStore.overlays` |
| `AutoTradeToggle.jsx` | Toggle switch with proper state binding | `dashboardStore.autoExecute` |
| `PipelineStatus.jsx` | Status pill strip (WAITING→EXECUTED) | `dashboardStore.pipelineStage` |
| `DrawdownBar.jsx` | Reusable 10-segment progress bar (used for MAX DD and DAILY DD) | Takes `percentage` prop |
| `TargetProgressBar.jsx` | Gradient progress bar for payout target | Takes `current`/`target` props |
| `StatusDot.jsx` | Reusable status indicator with optional pulse | Takes `status` prop |

### 4.5 Zustand Store Imports

| Component | Store Imports |
|---|---|
| `TopBar.jsx` | `useDashboardStore` (connected, apiStatus, timestamp, tsmStatus) |
| `MarketTicker.jsx` | `useDashboardStore` (marketQuotes — NEW, selectedAsset) |
| `ChartPanel.jsx` | `useDashboardStore` (liveMarket, openPositions, orStatus — NEW), `useChartStore` (NEW) |
| `RiskPanel.jsx` | `useDashboardStore` (tsmStatus, capitalSilo, openPositions, payoutPanel, scalingDisplay) |
| `SignalCards.jsx` | `useDashboardStore` (pendingSignals, openPositions, lastAck, liveMarket) |
| `SignalExecutionBar.jsx` | `useDashboardStore` (pipelineStage — NEW, autoExecute — NEW) |
| `ActivePosition.jsx` | `useDashboardStore` (openPositions, liveMarket) |
| `TradeLog.jsx` | `useDashboardStore` (openPositions — for now; eventually closed trades from NEW endpoint) |
| `SystemLog.jsx` | `useNotificationStore` (notifications) |

**New store needed:**
```
src/stores/chartStore.ts
  - bars: Bar[]
  - timeframe: "15s" | "1m" | "5m" | "15m"
  - selectedAsset: string
  - overlays: { or: boolean, entry: boolean, sl: boolean, tp: boolean, vwap: boolean }
  - Actions: setBars, setTimeframe, setSelectedAsset, toggleOverlay
```

### 4.6 Recommended File Structure After Refactoring

```
src/
├── App.jsx                          # Routes: /, /models, /config, /system, etc.
├── index.jsx                        # Entry point (keep as-is)
├── global.css                       # Tailwind imports (keep as-is, extend colors)
│
├── pages/
│   └── DashboardPage.jsx            # Renamed from OptimizedOptimized... — contains CSS Grid layout
│
├── components/
│   ├── layout/
│   │   ├── TopBar.jsx               # Extracted from RiskManagement.jsx:591-700
│   │   └── MarketTicker.jsx         # Extracted from RiskManagement.jsx:703-886
│   │
│   ├── risk/
│   │   ├── RiskPanel.jsx            # Extracted from RiskManagement.jsx:4-383
│   │   ├── DrawdownBar.jsx          # NEW reusable segment bar
│   │   └── TargetProgressBar.jsx    # NEW progress bar
│   │
│   ├── chart/
│   │   ├── ChartPanel.jsx           # Extracted from RiskManagement.jsx:888-968
│   │   ├── CandlestickChart.jsx     # NEW — chart library wrapper
│   │   ├── TimeframeSelector.jsx    # NEW
│   │   └── ChartOverlayToggles.jsx  # NEW
│   │
│   ├── signals/
│   │   ├── SignalExecutionBar.jsx    # Extracted from RiskManagement.jsx:384-415
│   │   ├── SignalCards.jsx           # Extracted from RiskManagement.jsx:416-590
│   │   ├── PipelineStatus.jsx       # NEW
│   │   └── AutoTradeToggle.jsx      # NEW
│   │
│   ├── trading/
│   │   ├── ActivePosition.jsx       # Renamed from FrameComponent.jsx
│   │   └── TradeLog.jsx             # Extracted from SystemMessages.jsx:9-114
│   │
│   └── system/
│       ├── SystemLog.jsx            # Extracted from SystemMessages.jsx:116-284
│       └── StatusDot.jsx            # NEW reusable status indicator
│
├── stores/
│   ├── dashboardStore.ts            # Existing — extend with selectedAsset, pipelineStage, autoExecute, marketQuotes, orStatus
│   ├── notificationStore.ts         # Existing — keep as-is
│   └── chartStore.ts                # NEW — bars, timeframe, overlays
│
├── ws/
│   └── useWebSocket.ts              # Existing — extend to handle: pipeline_status, or_status, bar_update, error, below_threshold
│
├── api/
│   └── client.ts                    # Existing — extend with: bars(), orders(), performance()
│
└── constants/
    ├── assetNames.ts                # NEW — ASSET_NAMES mapping (ticker → full name)
    └── pointValues.ts               # NEW — POINT_VALUES mapping (BUG-03 fallback table)
```

### 4.7 Locofy Artifacts to Clean Up

| Artifact | Location | Action |
|---|---|---|
| `!!m-[0 important]` margin overrides | `RiskManagement.jsx:384, 591, 688, 931` | Remove — use proper layout flow |
| `absolute right-[-975.5px]` positioning | `RiskManagement.jsx:384` | Remove — extract component to grid |
| `absolute top-[-28px] right-[-975.9px]` | `RiskManagement.jsx:591` | Remove — extract component to grid |
| `absolute bottom-[-476.6px]` | `RiskManagement.jsx:931` | Remove — use grid placement |
| `w-[1927.2px]` nav bar | `RiskManagement.jsx:595` | Replace with `w-full` |
| `pb-[253.4px]` bottom padding | Page container:7 | Remove |
| `mt-[-170px]` negative margin | `FrameComponent.jsx:6` | Remove — use grid placement |
| `mq450`, `mq750`, `mq1025`, `mq1125` classes | Throughout all components | Locofy custom breakpoints — replace with standard Tailwind responsive prefixes (`sm:`, `md:`, `lg:`, `xl:`) or remove (trading dashboard is desktop-first) |
| `rounded-[43937340px]`, `rounded-[29325502px]`, `rounded-[43469100px]`, `rounded-[21549516px]` | Multiple locations | Locofy giant border-radius artifact — replace with `rounded-full` |
| `border-[0.9px]`, `border-[1.3px]`, `border-[0.6px]`, `border-[0.8px]` sub-pixel borders | Throughout | Normalize to `border` (1px) or `border-2` (2px) — sub-pixel borders render inconsistently |
| `leading-[4.7px]` (4.7px line height) | `RiskManagement.jsx:878-885` | Impossibly small line-height — text will overlap. Fix to `leading-tight` or `leading-[12px]` |
| Hidden placeholder divs | `SystemMessages.jsx:78-91`, `RiskManagement.jsx:890-891` | Delete — empty hidden elements serve no purpose |
| `PropTypes` imports | All components | Keep if staying in JSX. Remove if migrating to TypeScript (recommended to match existing codebase pattern) |
| `reportWebVitals.jsx` | `src/reportWebVitals.jsx` | Locofy/CRA artifact — can delete if not needed |
| `react-router-dom` scroll behavior | `App.jsx:15-19` | Keep, but the scroll-to-top effect is unnecessary for a single-page dashboard |
| Inline font declarations `font-['JetBrains_Mono']` | Throughout all components | Move to `tailwind.config.js` as `fontFamily: { mono: ['JetBrains Mono', ...] }` then use `font-mono` |
| Inline color values `text-[#0faf7a]`, `bg-[#10b981]` etc. | Throughout | Define as Tailwind theme colors matching existing `captain-gui` CSS variable system. At minimum: `green: #0faf7a`, `red: #ef4444`, `cyan: #06b6d4`, `amber: #fbbf24/#f59e0b`, `surface: #0a0f0d`, `card: #08100f`, `border: #1a3038/#1e293b/#2e4e5a` |
| Duplicate font imports (JetBrains Mono + Inter) | `global.css:4-5` | Keep both — JetBrains Mono for data, Inter for UI labels. But load via `<link>` in `index.html` for better performance, not `@import url()` in CSS |

### 4.8 Tailwind Config Gaps

The current `tailwind.config.js` has:
- Empty `screens: {}` — no responsive breakpoints defined
- `preflight: false` — Tailwind's reset is disabled, but Locofy code assumes it's active (via `global.css` importing `tailwindcss/preflight.css` separately)
- No custom colors, fonts, or spacing defined

**Recommended additions:**
```js
module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: { DEFAULT: '#0a0f0d', dark: '#080e0d', card: '#08100f', elevated: '#0a1614' },
        border: { DEFAULT: '#1e293b', subtle: '#1a3038', accent: '#2e4e5a' },
        captain: {
          green: '#0faf7a',
          red: '#ef4444',
          cyan: '#06b6d4',
          amber: '#f59e0b',
          blue: '#3b82f6',
          orange: '#ff8800',
          pink: '#ff0040',
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'SF Mono', 'Consolas', 'monospace'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
};
```

---

## Summary: Work Order

### Phase 1 — Extract & Restructure (no data wiring)
1. Split `RiskManagement.jsx` into 6 components
2. Split `SystemMessages.jsx` into 2 components
3. Rename `FrameComponent` → `ActivePosition`, page → `DashboardPage`
4. Implement CSS Grid layout in `DashboardPage`
5. Remove all absolute positioning hacks
6. Clean up Locofy artifacts (sub-pixel values, giant border-radii, hidden divs)
7. Update `tailwind.config.js` with theme colors and fonts
8. Verify layout renders correctly at 1440px, 1920px, 2560px

### Phase 2 — Wire Existing Data
9. Import Zustand stores into extracted components
10. Replace all static text with store bindings (existing fields only)
11. Add direction normalization at store boundary (`direction > 0 ? "LONG" : "SHORT"`)
12. Add point_value fallback table for proximity calculations
13. Wire WebSocket event handlers for existing message types
14. Wire system log filter buttons
15. Wire navigation tabs to React Router

### Phase 3 — Build New Features
16. Create `chartStore` and chart library integration
17. Add multi-asset market data streaming
18. Build pipeline status and auto-trade toggle
19. Build new backend endpoints (bars, orders, performance)
20. Wire OR status display
21. Build MODELS and CONFIG page shells
