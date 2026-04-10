# Structural UX Audit

**Branch:** `ux-audit-overhaul`
**Date:** 2026-04-10
**Auditor:** Claude Code (automated)
**Stack:** React 18 + Vite + Tailwind + Zustand
**Scope:** All 57 files under `src/`

---

## Severity Key

| Tag | Meaning |
|-----|---------|
| **CRITICAL** | Broken layout, unreadable text, inaccessible control, or data integrity issue |
| **MEDIUM** | Degraded experience at edge cases, inconsistency, or usability friction |
| **LOW** | Minor polish issue, dead code, or cosmetic inconsistency |

---

## src/

### App.jsx (`src/App.jsx`)

- **[CRITICAL] EMPTY STATES:** `RequireAuth` returns `null` during auth loading (line 27). User sees a blank white screen with no skeleton, spinner, or feedback while JWT is validated. On slow connections this can last several seconds.
- **[LOW] NAVIGATION:** No `<title>` set for `/models` route in the `switch` block (line 60-83). Browser tab shows stale title when navigating to Models page.

### index.jsx (`src/index.jsx`)

No issues found.

### reportWebVitals.jsx (`src/reportWebVitals.jsx`)

No issues found.

---

## src/api/

### client.js (`src/api/client.js`)

- **[MEDIUM] NAVIGATION:** On 401 response, `window.location.href = "/login"` (hard navigation) discards all in-memory Zustand state. A React Router `navigate()` would preserve the SPA shell and allow return-to-origin after re-auth.

---

## src/auth/

### AuthContext.jsx (`src/auth/AuthContext.jsx`)

- **[MEDIUM] EMPTY STATES:** `loading` state is `true` during initial token validation but no consumer shows a loading indicator — the only consumer is `RequireAuth` in App.jsx which renders `null`.

---

## src/components/aim/

### AimDetailModal.jsx (`src/components/aim/AimDetailModal.jsx`)

- **[MEDIUM] SIZING:** Close button is `px-2` with no explicit min-height/min-width (line 86-89). Touch target is approximately 20x20px — well below the 44px WCAG minimum.
- **[MEDIUM] SIZING:** All body text is `text-[10px]`. Per-asset table cells, validation checks, and configuration values are dense and hard to scan at normal viewing distances.
- **[LOW] NAVIGATION:** Modal traps focus via click-outside and Escape handlers, but does not implement proper focus trapping (Tab can reach elements behind the backdrop).
- **[LOW] NAVIGATION:** No `role="dialog"` or `aria-modal="true"` on the modal container.

### AimRegistryPanel.jsx (`src/components/aim/AimRegistryPanel.jsx`)

- **[CRITICAL] SIZING:** Activate/Deactivate buttons are `py-0.5 text-[9px]` (line 170). Rendered height is approximately 18-20px — critically small for an action that changes live system state.
- **[MEDIUM] SIZING:** Tier badge is `text-[8px]` absolutely positioned in corner (line 184). At 8px this is sub-readable on many displays.
- **[MEDIUM] SIZING:** AIM card content is `text-[10px]` throughout with `p-2` padding. Cards are very dense.
- **[LOW] CONSISTENCY:** Grid uses `grid-cols-4 2xl:grid-cols-4 xl:grid-cols-4 lg:grid-cols-3 md:grid-cols-2 sm:grid-cols-2`. The `2xl`, `xl`, and default all specify 4 columns — redundant breakpoints.

---

## src/components/chart/

### CandlestickChart.jsx (`src/components/chart/CandlestickChart.jsx`)

- **[LOW] CONSISTENCY:** Dead code — `USE_CUSTOM_CHART` is `false` in ChartPanel.jsx (line 12). This component is imported but never rendered. 187 lines of unused code.

### ChartOverlayToggles.jsx (`src/components/chart/ChartOverlayToggles.jsx`)

- **[LOW] CONSISTENCY:** Dead code — only rendered when `USE_CUSTOM_CHART` is true, which is hardcoded `false`. Buttons at `text-[8px]` would be unreadable if ever enabled.

### ChartPanel.jsx (`src/components/chart/ChartPanel.jsx`)

- **[CRITICAL] SIZING:** System info footer bar uses `text-[6.3px]` (line 26). This is physically unreadable on virtually all displays — 6.3px is roughly 4.7pt. Content includes important system identifiers ("SYS:SIGNAL_ENGINE", "BROKER:TOPSTEPX", timestamp).
- **[MEDIUM] SIZING:** Price display at `text-[45.8px]` (line 71) has no responsive scaling. On narrow center panels (user can resize below 400px) the price will overflow or wrap mid-number.
- **[MEDIUM] SIZING:** Asset name at `text-[21.2px]` and OHLC data at `text-[15.2px]` use fractional pixel sizes that produce inconsistent subpixel rendering across browsers.
- **[MEDIUM] OVERFLOW:** OHLC line and Bid/Ask line sit in a flex row with no `overflow-hidden` or `text-overflow` truncation. With long asset names or wide spreads, content can overflow.
- **[LOW] EMPTY STATES:** When `liveMarket` is null, most values show "—" which is correct, but the OR values section shows "—" with no context about whether OR is not yet formed or data is unavailable.

### TimeframeSelector.jsx (`src/components/chart/TimeframeSelector.jsx`)

- **[LOW] CONSISTENCY:** Dead code — never rendered. Buttons at `text-[9px]`.

### TradingViewWidget.jsx (`src/components/chart/TradingViewWidget.jsx`)

- **[LOW] OVERFLOW:** Widget container uses `position: absolute` with `inset: 0` inside a relative parent. If parent height is 0 (before layout paint), the iframe may flash or mis-size on initial render.

---

## src/components/layout/

### MarketTicker.jsx (`src/components/layout/MarketTicker.jsx`)

- **[CRITICAL] CONSISTENCY:** 9 of 10 tickers display **hardcoded** prices and percentages (lines 64-237). Only MES is wired to `liveMarket` store (lines 31-41). MNQ shows "19284.83", ES shows "5429.65", etc. — these are stale snapshot values baked into JSX, not live data. This is a data integrity issue: users may believe they are seeing live prices when they are not.
- **[CRITICAL] SIZING:** Change percentages use `text-[7.5px]` (line 34, 68, etc.). At 7.5px (approximately 5.6pt) these are sub-readable.
- **[MEDIUM] SIZING:** Ticker prices at `text-[9.8px]` and symbol names at `text-[9px]` are below comfortable reading size. Combined with `leading-[13.5px]` the effective hit area for each clickable ticker is approximately 35px tall.
- **[MEDIUM] NAVIGATION:** Tickers are clickable `<div>` elements with `cursor-pointer` but no `role="button"`, `tabIndex`, `onKeyDown`, or focus-visible styling. Keyboard users cannot navigate or select tickers.
- **[MEDIUM] OVERFLOW:** `overflow-x-auto` on the `<nav>` is correct, but there is no visual scroll indicator. Users may not realize more tickers exist off-screen on narrow viewports.
- **[LOW] SIZING:** Status dots at `w-[4.5px] h-[4.5px]` (line 27) — imperceptibly small, easy to miss.

### TopBar.jsx (`src/components/layout/TopBar.jsx`)

- **[CRITICAL] SIZING:** "Last tick" timestamp uses `text-[6.4px]` (line 202). This is sub-readable (approximately 4.8pt). Contains operationally important information about data freshness.
- **[CRITICAL] SIZING:** Health status dots are `w-[5.5px] h-[5.5px]` (lines 190-200). These convey critical system health information (API, WS, QDB, Redis connectivity) but are barely visible.
- **[MEDIUM] SIZING:** Account dropdown button is `h-[20px]` with `text-[8.6px]` (line 107). Touch target is well below 44px minimum. Dropdown items are also `py-[5px] text-[8.6px]` (line 127).
- **[MEDIUM] SIZING:** Git Pull button is `h-[20px]` with `text-[8.2px]` (line 163). Small touch target for an action that triggers a server-side git pull + container rebuild.
- **[MEDIUM] SIZING:** Nav tabs are `text-[9.1px]` with `px-[7px]` padding (line 9). Touch targets are approximately 28px wide by 20px tall.
- **[MEDIUM] NAVIGATION:** Nav tabs use `NavLink` (accessible) but account dropdown, Git Pull, and dropdown items are buttons with no `focus-visible` styling. Keyboard focus is invisible.
- **[MEDIUM] NAVIGATION:** Account dropdown closes on outside click but has no `aria-expanded`, `aria-haspopup`, or keyboard arrow-key navigation for the dropdown menu.
- **[LOW] SIZING:** Overall bar height is `h-[36.6px]` — fractional pixel values can cause subpixel rendering artifacts.

---

## src/components/replay/

### AssetCard.jsx (`src/components/replay/AssetCard.jsx`)

- **[MEDIUM] SIZING:** Direction badges at `text-[7px]` and session badges at `text-[6px]`. Session badges at 6px are effectively unreadable.
- **[LOW] EMPTY STATES:** Loading and error states are handled with skeleton shimmer and error message respectively.

### BatchPnlReport.jsx (`src/components/replay/BatchPnlReport.jsx`)

- **[MEDIUM] SIZING:** View toggle buttons ("Daily" / "Overall") are `text-[8px]` (approximately 6pt). Tiny click targets.
- **[MEDIUM] SCROLL:** Day rows container uses `max-h-[200px]` overflow-y-auto. On long replays (e.g., 30+ days) this is fine, but the scrollbar is browser-default and invisible on macOS/trackpad until hovering.
- **[LOW] EMPTY STATES:** Correctly hides entirely when no batch data exists.

### BlockDetail.jsx (`src/components/replay/BlockDetail.jsx`)

- **[MEDIUM] OVERFLOW:** Container uses `max-h-[300px] overflow-y-auto` but inner `GenericDetail` also uses `max-h-[200px]`. Nested scroll containers are confusing — user may scroll the inner container to the bottom and not realize the outer container also scrolls.
- **[MEDIUM] SIZING:** Reason column truncated at `max-w-[150px]` with no tooltip or expand mechanism. Important diagnostic text is silently clipped.

### PipelineStepper.jsx (`src/components/replay/PipelineStepper.jsx`)

- **[MEDIUM] NAVIGATION:** Stage buttons are clickable divs with no `role="button"`, `tabIndex`, or keyboard support. Users cannot Tab through pipeline stages.
- **[MEDIUM] SIZING:** Circle indicators at `w-[14px] h-[14px]` with stage buttons at `min-w-[72px]`. Touch targets are small but acceptable for non-critical UI.

### PlaybackControls.jsx (`src/components/replay/PlaybackControls.jsx`)

- **[MEDIUM] SIZING:** Play/Pause button is `w-[24px] h-[24px]` — below 44px touch target minimum for a primary action control.
- **[MEDIUM] SIZING:** Speed pills at `text-[8px]`. Small text and small click targets.
- **[MEDIUM] SIZING:** Progress bar is `h-[3px]` — nearly invisible. Users can click to seek but the 3px height makes it very difficult to target.
- **[LOW] NAVIGATION:** No keyboard shortcuts for Play/Pause/Speed despite being the primary replay interaction.

### ReplayConfigPanel.jsx (`src/components/replay/ReplayConfigPanel.jsx`)

- **[MEDIUM] SIZING:** Labels use `text-[8px]` (via `Label` component, line 9). Below comfortable reading size.
- **[MEDIUM] SIZING:** Toggle switches at `h-[16px] w-[32px]` with `12px` knobs (lines 302-303, 319-320). Small but usable on desktop; too small for touch.
- **[MEDIUM] SIZING:** Run Replay button is `py-[6px] text-[11px]` — adequate but on the small side for a primary action.
- **[LOW] EMPTY STATES:** Preset selector hidden when no presets exist — appropriate behavior.

### ReplayHistory.jsx (`src/components/replay/ReplayHistory.jsx`)

- **[LOW] SCROLL:** `max-h-[200px]` overflow container. Appropriate for the sidebar context.
- **[LOW] EMPTY STATES:** Empty state handled with "No replay history" message.

### ReplaySummary.jsx (`src/components/replay/ReplaySummary.jsx`)

- **[MEDIUM] SIZING:** What-If and Save buttons at `py-[4px] text-[9px]` — small touch targets for action buttons.
- **[MEDIUM] SCROLL:** Trades table uses `max-h-[160px]` — very limited vertical space. With 10 assets each producing a trade, the table is already scrolling.

### SimulatedPosition.jsx (`src/components/replay/SimulatedPosition.jsx`)

No issues found. Empty state handled. Sizing is adequate.

### WhatIfComparison.jsx (`src/components/replay/WhatIfComparison.jsx`)

- **[MEDIUM] SCROLL:** Per-asset contracts scrollable at `max-h-[120px]` — very tight. Easy to miss that content is scrollable.
- **[LOW] OVERFLOW:** 4-column comparison grid may overflow on narrow right panels (panel is fixed 280px).

---

## src/components/risk/

### RiskPanel.jsx (`src/components/risk/RiskPanel.jsx`)

- **[CRITICAL] OVERFLOW:** Drawdown bar segments are 10 fixed-width blocks at `w-[42.7px]` each (line 115) totaling 427px + 9 gaps. Parent requires `min-w-[445px]` (line 107). When the left panel is resized below 470px, the bar overflows its container and causes horizontal scroll or clipping. Same issue for Daily DD bar with `min-w-[305px]` (line 141).
- **[CRITICAL] SIZING:** Fractional pixel dimensions throughout suggest Figma auto-export. Values like `text-[10.7px]`, `text-[12.3px]`, `text-[15.3px]`, `leading-[16.1px]`, `gap-[9.1px]`, `pb-[29px]` produce inconsistent subpixel rendering and make the component feel "off" compared to hand-tuned components.
- **[MEDIUM] OVERFLOW:** Payout Info cards use fixed `w-[201px]` (lines 300, 308, 316, 324, 332, 340). Six 201px cards total 1206px + gaps, requiring ~1250px. They wrap via `flex-wrap` but the wrapping behavior is ungoverned — cards stack unevenly at intermediate widths.
- **[MEDIUM] SIZING:** Risk parameter cards use `min-w-[112px] max-w-[149px]` (lines 399, 407, 415, 423). Four cards need minimum 448px + gaps. At narrow panel widths they cannot wrap cleanly.
- **[MEDIUM] CONSISTENCY:** Uses `font-['JetBrains_Mono']` directly instead of `font-mono` Tailwind class used everywhere else. This creates an implicit dependency on JetBrains Mono being loaded.
- **[MEDIUM] OVERFLOW:** Footer uses `overflow-x-auto` (line 437) suggesting the developer already knew content can overflow. Three footer labels ("SYS:RISK_MGR", "BROKER:TOPSTEPX", "UPD: ...") will clip on narrow panels.
- **[LOW] CONSISTENCY:** Uses responsive utility classes `mq450`, `mq750`, `mq1025` that appear to be custom breakpoints from Figma export, inconsistent with Tailwind's `sm:`, `md:`, `lg:` convention used elsewhere.
- **[LOW] SIZING:** `pb-[29px]` bottom padding is an odd value suggesting Figma pixel-perfect export rather than intentional spacing.

---

## src/components/shared/

### CollapsiblePanel.jsx (`src/components/shared/CollapsiblePanel.jsx`)

- **[MEDIUM] NAVIGATION:** Toggle button has no `focus-visible` styling. Keyboard users cannot see which panel header is focused.
- **[LOW] SIZING:** Arrow indicators use Unicode characters (`\u25BC` / `\u25B6`) at `text-xs`. Size and alignment vary across fonts.

### DataTable.jsx (`src/components/shared/DataTable.jsx`)

- **[MEDIUM] SCROLL:** `overflow-x-auto` on the table wrapper is correct, but no visual scroll indicator exists. On tables with many columns (like HistoryPage signal columns), the rightmost columns may be hidden with no affordance that horizontal scroll is possible.
- **[LOW] EMPTY STATES:** Empty state handled via `emptyMessage` prop.

### StatBox.jsx (`src/components/shared/StatBox.jsx`)

No issues found. `min-h-[55px]` is adequate.

### StatusBadge.jsx (`src/components/shared/StatusBadge.jsx`)

- **[LOW] SIZING:** `text-[10px]` with `whitespace-nowrap`. Adequate but on the small side.

### StatusDot.jsx (`src/components/shared/StatusDot.jsx`)

No issues found.

---

## src/components/signals/

### SignalCards.jsx (`src/components/signals/SignalCards.jsx`)

- **[MEDIUM] SIZING:** Direction badges at `text-[8px] leading-[12px]` (line 25-26). Below comfortable reading size.
- **[MEDIUM] SIZING:** Confidence tier badge at `text-[7px] leading-[10px]` (line 71). Sub-readable on most displays.
- **[MEDIUM] SIZING:** Clear button at `text-[8px]` with `px-[6px] py-[1px]` (line 103). Touch target is approximately 30x14px — well below minimum.
- **[LOW] EMPTY STATES:** Empty state "No pending signals" is handled.
- **[LOW] CONSISTENCY:** Uses `text-[11px]` for asset name, `text-[10px]` for P&L, `text-[9px]` for strategy/entry/SL/TP, `text-[8px]` for direction, `text-[7px]` for confidence — five different font sizes in one row.

### SignalExecutionBar.jsx (`src/components/signals/SignalExecutionBar.jsx`)

- **[MEDIUM] OVERFLOW:** Fixed-width inner container at `w-[558.7px]` (line 20). At narrower center panel widths, the title + pipeline pills will overflow. The `mq750:flex-wrap` class handles wrapping but `w-[558.7px]` prevents the container from shrinking.
- **[LOW] SIZING:** Pipeline stage pills at `text-[12.1px]` — a rare fractional size. `min-w-[60px]` is acceptable.
- **[LOW] CONSISTENCY:** Uses `mq750` and `mq450` custom breakpoints (Figma export classes) instead of standard Tailwind breakpoints.

---

## src/components/system/

### SystemLog.jsx (`src/components/system/SystemLog.jsx`)

- **[MEDIUM] SIZING:** Filter buttons at `text-[8.6px]` (line 157). Small click targets for frequently-used filters.
- **[MEDIUM] SIZING:** Category labels in log entries use inline `fontSize: "8px"` (lines 115, 243). At 8px these labels (ERR, SIG, ORD) are barely legible.
- **[MEDIUM] CONSISTENCY:** Mixes Tailwind classes (`text-[9.7px]`, `font-['JetBrains_Mono']`) with inline styles (`style={{ fontSize: "8px" }}`). Two different styling approaches in one component.
- **[MEDIUM] SCROLL:** Log entries have no `line-height` constraint specified for the message text. Dense log messages with long text cause entries to blur together. `leading-[13.6px]` at `text-[9.7px]` gives very tight spacing.
- **[LOW] EMPTY STATES:** Empty states handled for both log and telegram views.
- **[LOW] NAVIGATION:** Tab switching between "SYSTEM LOG" and "TELEGRAM" uses buttons with no focus-visible styling.

---

## src/components/trading/

### ActivePosition.jsx (`src/components/trading/ActivePosition.jsx`)

- **[CRITICAL] OVERFLOW:** SL/TP gradient bar uses hardcoded padding: `pl-[346px] pr-[265px]` (line 108). These absolute pixel values position the entry marker on the gradient bar. When the center panel is resized to less than ~650px, the padding exceeds the container width and the bar breaks completely. The `mq750` and `mq1025` overrides (`pl-[86px] pr-[66px]` and `pl-[173px] pr-[132px]`) help at those breakpoints but leave gaps between breakpoints.
- **[CRITICAL] SIZING:** ENTRY/CURRENT labels at `text-[7.2px]` (line 79, 85). SL/TP distance labels at `text-[7.2px]` (line 100, 103, 115, 117). At 7.2px (approximately 5.4pt), these are sub-readable. They contain operationally critical information (entry price, stop loss, take profit).
- **[MEDIUM] SIZING:** P&L display at `text-[18.4px]` — fractional pixel value from Figma export.
- **[MEDIUM] SIZING:** Direction badge at `text-[8.2px]`, contracts/order info at `text-[8.2px]`, time/lots/fill info at `text-[8.2px]` — consistently small but borderline readable.
- **[MEDIUM] CONSISTENCY:** Uses `mq450`, `mq750`, `mq1025` Figma breakpoints inconsistently with the rest of the app.
- **[LOW] EMPTY STATES:** Empty state "No active position" is handled cleanly.

### TradeLog.jsx (`src/components/trading/TradeLog.jsx`)

- **[MEDIUM] SIZING:** Column headers at `text-[8.6px]` (line 28). Data rows at `text-[10.8px]`.
- **[MEDIUM] OVERFLOW:** Trade rows use `gap-[33px]` and `gap-[33.3px]` for fixed column spacing (lines 29, 36). On very narrow right panels, the TIME and ASSET columns can overlap with P&L and DUR columns.
- **[LOW] EMPTY STATES:** Empty state "No trades today" handled.
- **[LOW] SIZING:** Total footer at `text-[9.7px]` — adequate.

---

## src/constants/

### assetNames.js (`src/constants/assetNames.js`)

No issues found.

### blockRegistry.js (`src/constants/blockRegistry.js`)

No issues found.

### pointValues.js (`src/constants/pointValues.js`)

No issues found.

---

## src/pages/

### LoginPage.jsx (`src/pages/LoginPage.jsx`)

- **[MEDIUM] SIZING:** Submit button at `py-2 text-[10px]` (line 56). Height is approximately 30px — below 44px touch target minimum.
- **[LOW] SIZING:** Input field at `text-xs px-3 py-2` — adequate.
- **[LOW] NAVIGATION:** Input has `autoFocus` which is good for desktop but can cause viewport jump on mobile.

### DashboardPage.jsx (`src/pages/DashboardPage.jsx`)

- **[CRITICAL] CONSISTENCY:** DEV mock data is injected on every mount when `import.meta.env.DEV` is true (lines 24-142). This means the dashboard always shows fake 2026-03-30 session data in development, making it impossible to test real backend data flow without modifying code. `DEV_MOCK_ENABLED` should be a `.env` variable, not hardcoded to dev mode.
- **[MEDIUM] SIZING:** `ResizeHandle` width/height is 5px (lines 148-149). Resize handles are difficult to grab — standard is 8-12px with a visible drag indicator.
- **[MEDIUM] SCROLL:** Panel `minSize` values (10, 5, 15, etc.) allow panels to be resized very small. At `minSize={5}` (SignalCards panel), the panel can shrink to 5% of total height, rendering content unreadable.
- **[LOW] EMPTY STATES:** No loading skeleton or spinner shown while initial API data loads (the `api.dashboard()` call on line 194). Dashboard renders with empty components until data arrives.

### HistoryPage.jsx (`src/pages/HistoryPage.jsx`)

- **[MEDIUM] EMPTY STATES:** When WebSocket is not connected and no cached data exists, shows "Connect to the dashboard first to load data" (line 67). This is a poor UX — the page should fetch its own data independently (acknowledged by TODO comment on line 4).
- **[MEDIUM] SIZING:** Tab buttons at `px-3 py-1.5 text-[10px]` (line 94). Touch targets are approximately 60x24px — passable but small.
- **[LOW] CONSISTENCY:** Two tabs ("Trade Outcomes" and "System Events") always show empty data arrays (lines 76, 79). These tabs exist but have no data source wired up.

### ModelsPage.jsx (`src/pages/ModelsPage.jsx`)

- **[MEDIUM] EMPTY STATES:** Same dependency issue as HistoryPage — requires DashboardPage WS connection to be mounted first (line 2 TODO comment). Shows "Connect to the dashboard first" when visited directly.
- **[MEDIUM] SIZING:** AIM registry uses `grid-cols-1` (line 30) — a single column list for potentially 270 AIM state rows (10 assets x 27 AIMs). This will produce a very long scrollable list.
- **[LOW] CONSISTENCY:** This page duplicates AIM display logic already present in `AimRegistryPanel`. Two different representations of AIM data exist in the app.

### ConfigPage.jsx (`src/pages/ConfigPage.jsx`)

- **[MEDIUM] EMPTY STATES:** Entire page is a stub with placeholder text (lines 7-9). "Pending backend endpoint integration" gives no timeline or workaround.
- **[LOW] CONSISTENCY:** Page uses the standard header + card pattern correctly. No structural issues beyond being empty.

### DashboardPage.jsx

_(Covered above)_

### ProcessesPage.jsx (`src/pages/ProcessesPage.jsx`)

- **[MEDIUM] SIZING:** Block trigger badges at `text-[8px]` (line 150). Small but consistent with similar badges elsewhere.
- **[MEDIUM] SIZING:** Block source file paths at `text-[9px]` (line 155). Dense text.
- **[LOW] EMPTY STATES:** Error banner is handled. Strategy table uses DataTable's `emptyMessage`. API connections section shows connected count.
- **[LOW] SCROLL:** Page has `overflow-y-auto` on the container. Correct for a long-form page.

### ReplayPage.jsx (`src/pages/ReplayPage.jsx`)

- **[MEDIUM] OVERFLOW:** Fixed 3-column grid `grid-cols-[280px_1fr_280px]` (line 132). Left and right columns are fixed at 280px. Below approximately 700px viewport width, the center column gets crushed to near-zero width.
- **[MEDIUM] NAVIGATION:** `ResizableBottomPanel` drag handle at `h-[5px]` (line 91). Very thin drag target. Standard resize handles are 8-12px.
- **[LOW] EMPTY STATES:** Empty states handled for idle, running, and asset grid states.
- **[LOW] CONSISTENCY:** ErrorBoundary wraps each section — good defensive pattern.

### ReportsPage.jsx (`src/pages/ReportsPage.jsx`)

- **[MEDIUM] OVERFLOW:** 3-column grid with `grid-cols-3` (line 56). Report type list is `col-span-1` and generation area is `col-span-2`. Below approximately 600px the columns become too narrow for their content.
- **[MEDIUM] SCROLL:** Report type list uses `max-h-[calc(100vh-140px)]` with `overflow-y-auto`. Appropriate but the `140px` offset is a magic number that may break if TopBar height changes.
- **[LOW] EMPTY STATES:** Loading, error, and empty states all handled correctly.

### SettingsPage.jsx (`src/pages/SettingsPage.jsx`)

- **[LOW] CONSISTENCY:** Theme toggle button uses the standard green button style. No issues.
- **[LOW] EMPTY STATES:** Account shows "Loading..." as placeholder — appropriate.

### SystemOverviewPage.jsx (`src/pages/SystemOverviewPage.jsx`)

- **[MEDIUM] SIZING:** Multiple sections have `text-[10px]` throughout. Governance schedule table, data quality rows, and circuit breaker details are dense.
- **[MEDIUM] EMPTY STATES:** Several placeholder sections display "available via RPT-XX" messages referencing report IDs. These are stub sections that don't provide actionable content.
- **[MEDIUM] SCROLL:** Page uses `overflow-y-auto` — correct for a long-form dashboard page. No issues.
- **[LOW] CONSISTENCY:** Uses Recharts `RadarChart` for system health visualization. The chart has proper empty state handling.

---

## src/stores/

### dashboardStore.js (`src/stores/dashboardStore.js`)

- **[MEDIUM] CONSISTENCY:** Direction normalization converts integers (`1`/`-1`) to strings (`"LONG"`/`"SHORT"`) in `_normSignal` helper. If backend sends unexpected values (e.g., `0`, `null`, `"BUY"`), the signal falls through with original value intact, potentially showing raw integers in the UI.
- **[LOW] SCROLL:** Signal archiving to `localStorage` via `clearSignals` — no size limit. Over months of use, `localStorage` could accumulate significant data.

### replayStore.js (`src/stores/replayStore.js`)

No structural issues found. Config state, pipeline tracking, and asset results are well-organized.

### chartStore.js (`src/stores/chartStore.js`)

No issues found.

### notificationStore.js (`src/stores/notificationStore.js`)

- **[LOW] SCROLL:** Notifications array grows unbounded. No max-size cap or auto-pruning. Over a long session, thousands of notifications could accumulate in memory.

### processesStore.js (`src/stores/processesStore.js`)

No issues found.

### reportsStore.js (`src/stores/reportsStore.js`)

No issues found.

### systemOverviewStore.js (`src/stores/systemOverviewStore.js`)

No issues found.

---

## src/utils/

### formatting.js (`src/utils/formatting.js`)

No issues found. All formatters use `America/New_York` timezone consistently.

---

## src/ws/

### useWebSocket.js (`src/ws/useWebSocket.js`)

- **[MEDIUM] EMPTY STATES:** On eviction (code 4001) or auth failure (code 4003), the hook logs a console warning but the UI has no visible indication that the WebSocket was forcibly disconnected. Users may not realize they've been evicted from another session.
- **[LOW] CONSISTENCY:** Exponential backoff reconnect is correct behavior. Max reconnect delay is appropriate.

---

## Cross-Cutting Issues

### 1. Pervasive Sub-Readable Text Sizes

| Size | Approx Points | Components Using It |
|------|--------------|---------------------|
| `text-[6.3px]` | 4.7pt | ChartPanel system footer |
| `text-[6.4px]` | 4.8pt | TopBar "Last tick" timestamp |
| `text-[6px]` | 4.5pt | AssetCard session badges |
| `text-[7px]` | 5.3pt | SignalCards confidence tier, AssetCard direction |
| `text-[7.2px]` | 5.4pt | ActivePosition ENTRY/CURRENT/SL/TP labels |
| `text-[7.5px]` | 5.6pt | MarketTicker change percentages |
| `text-[8px]` | 6.0pt | AimRegistryPanel tier badge, SystemLog category labels, PlaybackControls speed, BatchPnlReport toggles |
| `text-[8.2px]` | 6.2pt | ActivePosition metadata, TopBar Git Pull |
| `text-[8.6px]` | 6.5pt | TopBar dropdown, TradeLog headers, SystemLog filters |

**Recommendation:** Establish a minimum font size of `10px` for all content and `11px` for interactive elements. Text below 10px is not reliably readable on standard DPI displays.

### 2. Undersized Touch/Click Targets

| Target Size | Component | Element |
|------------|-----------|---------|
| ~14px height | AimRegistryPanel | Activate/Deactivate buttons |
| ~18px height | SignalCards | Clear button |
| 20px height | TopBar | Account dropdown, Git Pull button |
| 24px square | PlaybackControls | Play/Pause button |
| 3px height | PlaybackControls | Progress seek bar |
| 5px width/height | DashboardPage | ResizeHandle |
| 5px height | ReplayPage | Bottom panel drag handle |

**Recommendation:** All interactive elements should have a minimum touch target of 32px (desktop) or 44px (touch). For critical actions (activate/deactivate, play/pause, git pull), use 44px minimum.

### 3. Hardcoded Figma Export Artifacts

Components that appear to be direct Figma code exports with fractional pixel values, custom breakpoint classes (`mq450`, `mq750`, `mq1025`), and fixed-width containers:

- `RiskPanel.jsx` — Most severely affected. Essentially a Figma-to-code paste.
- `ActivePosition.jsx` — Hardcoded SL/TP bar padding, Figma breakpoints.
- `SignalExecutionBar.jsx` — Fixed-width inner container at `558.7px`.
- `TopBar.jsx` — Fixed `36.6px` bar height, `5.5px` status dots.
- `ChartPanel.jsx` — `6.3px` footer text, `45.8px` price display.
- `MarketTicker.jsx` — Per-ticker Figma export with fractional padding values.
- `TradeLog.jsx` — Fixed gap values, Figma-era line heights.

**Recommendation:** Replace all fractional pixel values with Tailwind spacing scale values. Replace `mq*` custom breakpoints with standard Tailwind responsive prefixes. Replace fixed-width containers with flex/grid layouts.

### 4. Missing Keyboard Accessibility

No component in the codebase implements `focus-visible` styling. Components that accept click input via `<div>` elements without keyboard support:

- MarketTicker tickers (clickable divs, no keyboard)
- PipelineStepper stages (clickable divs, no keyboard)
- AimCard (clickable div, no keyboard)
- CollapsiblePanel toggle (button, but no focus ring)
- TopBar dropdown (no arrow-key navigation)

### 5. WS-Dependent Pages Without Independent Data Fetch

`HistoryPage` and `ModelsPage` both depend on `DashboardPage` being mounted to establish the WebSocket connection. If a user navigates directly to `/history` or `/models` (e.g., via bookmark or refresh), they see "Connect to the dashboard first" with no way to proceed except navigating to `/` first. Both pages have TODO comments acknowledging this.

---

## Summary Statistics

| Severity | Count |
|----------|-------|
| CRITICAL | 11 |
| MEDIUM | 52 |
| LOW | 30 |
| **Total** | **93** |

### Top 5 Most Critical Files

1. **MarketTicker.jsx** — 9/10 tickers show hardcoded stale prices
2. **ActivePosition.jsx** — SL/TP gradient bar breaks on resize, sub-readable labels
3. **RiskPanel.jsx** — Fixed-width drawdown bars overflow, Figma export artifacts throughout
4. **TopBar.jsx** — Sub-readable health indicators and timestamps
5. **ChartPanel.jsx** — 6.3px system footer text
