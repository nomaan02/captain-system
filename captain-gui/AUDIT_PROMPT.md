# Claude Code Prompt — Full GUI Element Audit & Data Flow Validation

Paste everything below the line into Claude Code from the `captain-gui/` directory.

---

## TASK: Comprehensive GUI element audit — test every element, verify data flow, iterate until all responsive

You are working on the Captain GUI (`~/captain-system/captain-gui/`), a React 18 + Vite + Zustand + Tailwind trading dashboard. A Playwright E2E harness already exists (`e2e/data-flow.spec.ts`, `playwright.config.ts`). Your job is to **extend it into a full audit** of every visible GUI element, verifying that each one receives correct data and responds dynamically to state changes.

### WHAT ALREADY EXISTS

**Playwright harness (confirmed working, 9/9 pass):**
- `playwright.config.ts` — Chromium-only, baseURL `http://localhost:5174`, headless
- `e2e/data-flow.spec.ts` — 9 basic visibility/connection tests
- `npm run test:e2e` — runs the suite

**Instrumented `data-testid` attributes (10 total):**
- `app-shell` — DashboardPage outer div
- `health-bar` — TopBar status dots container
- `api-status` + `data-status` — TopBar API dot
- `ws-status` + `data-status` — TopBar WS dot
- `last-tick-timestamp` — TopBar last tick span
- `market-status-panel` — MarketTicker nav
- `current-price` — ChartPanel h2 price
- `risk-panel` — RiskPanel outer div
- `signal-panel` — SignalCards outer div
- `session-phase` — SignalExecutionBar stage pills container

**Component tree (all in `src/`):**
```
pages/DashboardPage.jsx          — main layout (react-resizable-panels)
  components/layout/TopBar.jsx   — clock, nav, account selector, status dots, last tick
  components/layout/MarketTicker.jsx — horizontal asset tabs (MES live, rest hardcoded)
  components/risk/RiskPanel.jsx  — capital, drawdown bars, payout target, day stats, accounts, risk params
  components/chart/ChartPanel.jsx — asset header, large price, TradingView chart, OR values
  components/trading/ActivePosition.jsx — open position details (or "No active position")
  components/signals/SignalExecutionBar.jsx — pipeline stage pills + Auto Trade toggle
  components/signals/SignalCards.jsx — pending signal cards + session summary footer
  components/trading/TradeLog.jsx — today's trade rows
  components/system/SystemLog.jsx — notification log with All/Errors/Signals/Orders filter
```

**Zustand stores (3):**
- `stores/dashboardStore.js` — connected, timestamp, pipelineStage, autoExecute, orStatus, capitalSilo, dailyTradeStats, openPositions, pendingSignals, liveMarket, apiStatus, tsmStatus, decayAlerts, warmupGauges, regimePanel, payoutPanel, scalingDisplay, lastAck, selectedAccount, accounts
- `stores/notificationStore.js` — notifications[], unreadCount, filter
- `stores/chartStore.js` — bars[], timeframe, selectedAsset, overlays{}

**Data sources:**
- WebSocket: `ws/useWebSocket.js` connects to `/ws/{userId}`. Message types: `connected`, `dashboard`, `live_market`, `signal`, `command_ack`, `notification`, `error`, `below_threshold`, `or_status`, `pipeline_status`, `bar_update`
- REST API: `api/client.js` — `/api/health`, `/api/status`, `/api/dashboard/{userId}`, `/api/bars/{asset}`, `/api/orders/{userId}`, `/api/performance/{userId}`, etc.
- Mock mode: `DEV_MOCK_ENABLED = true` in DashboardPage injects static mock data on mount

**Backend:** captain-command (FastAPI on `:8000`), served via Docker. WebSocket and API proxy through Vite dev server config (`/api` → `:8000`, `/ws` → `ws://:8000`).

---

### PHASE 1 — ENVIRONMENT SETUP & PREREQUISITE CHECK

Before writing any tests, verify the runtime environment:

1. **Check Vite dev server** — `curl -s -o /dev/null -w "%{http_code}" http://localhost:5173` and `:5174`. Whichever returns 200 is the active port. Update `playwright.config.ts` baseURL if needed.

2. **Check Docker backend** — Run `docker compose -f ~/captain-system/docker-compose.yml -f ~/captain-system/docker-compose.local.yml ps` to see if captain-command is running. If it IS running, the WebSocket and API will be live. If it's NOT running, tests must work against mock mode (`DEV_MOCK_ENABLED = true`).

3. **Determine test mode:**
   - If backend is UP: Set `DEV_MOCK_ENABLED = false` in `src/pages/DashboardPage.jsx` so we test REAL data flow. This is the preferred mode.
   - If backend is DOWN: Leave `DEV_MOCK_ENABLED = true`. Tests will validate mock data rendering. Note this in test output.

4. **Check the existing harness still passes:** Run `npm run test:e2e`. If any of the 9 existing tests fail, fix them first before proceeding.

5. **If backend is UP but WebSocket isn't connecting:** Check `docker compose logs captain-command --tail=20` for errors. The WS endpoint is `/ws/{user_id}` where `user_id` is `primary_user`. If the backend WebSocket server isn't implemented yet or is broken, note this and fall back to mock mode.

---

### PHASE 2 — INSTRUMENT ALL REMAINING ELEMENTS

Read every component file in `src/components/` and `src/pages/`. For EVERY piece of dynamic content (anything driven by Zustand state, props, or API data), add a `data-testid` attribute. The principle: **every testable data point gets a unique testid**.

**Naming convention:** `{component}-{element}` in kebab-case. Examples:
- `topbar-clock` for the ET clock display
- `topbar-account-selector` for the account dropdown button
- `topbar-trading-badge` for the TRADING status badge
- `risk-capital-value` for the CAPITAL dollar amount
- `risk-equity-value` for the EQUITY dollar amount
- `risk-cumulative-pnl` for the Cumulative P&L value
- `risk-mdd-bar` for the MAX DD progress bar
- `risk-mdd-percent` for the MAX DD percentage text
- `risk-daily-dd-bar` for the DAILY DD progress bar
- `risk-daily-dd-percent` for the DAILY DD percentage text
- `risk-payout-target-bar` for the payout progress bar
- `risk-payout-remaining` for the remaining dollar amount
- `risk-day-pnl` for the Day P&L value
- `risk-profit-factor` for the Profit Factor value
- `risk-wins` / `risk-losses` / `risk-trades` / `risk-win-pct` for day stats
- `chart-asset-name` for the selected asset symbol in chart header
- `chart-last-price` (already `current-price`, keep it)
- `chart-change` for the price change display
- `chart-volume` for volume
- `chart-bid-ask` for bid/ask spread
- `chart-or-upper` / `chart-or-lower` for OR range values
- `chart-or-state` for the OR state badge (INSIDE OR / BREAKOUT SHORT etc.)
- `position-direction` for LONG/SHORT badge
- `position-asset` for position asset name
- `position-pnl` for position P&L
- `position-entry` for entry price
- `position-current` for current price
- `execution-pipeline-stage` (already `session-phase`, keep it)
- `execution-auto-trade-toggle` for the Auto Trade switch
- `signal-card` for each signal row (use `data-testid="signal-card"` on each, differentiate by content)
- `tradelog-row` for each trade row
- `tradelog-total` for the total P&L footer
- `syslog-entry` for each system log line
- `syslog-filter-all` / `syslog-filter-errors` / `syslog-filter-signals` / `syslog-filter-orders` for filter buttons
- `ticker-{asset}` for each asset in MarketTicker (e.g., `ticker-MES`, `ticker-ES`)
- `ticker-{asset}-price` for the price within each ticker

Add `data-status` attributes where state is binary/enum:
- Account selector: `data-status="open"` / `"closed"`
- Auto Trade toggle: `data-status="on"` / `"off"` based on `autoExecute`
- Pipeline stage pills: `data-active="true"` on the active stage
- Connection dots (QDB, Redis): `data-status="connected"` / `"disconnected"`

**Rules:**
- ONLY add attributes — never change functionality, styling, or layout
- If an element is hardcoded (not driven by state), still add a testid but note it in a comment: `{/* NOTE: hardcoded, not from store */}`
- Keep all existing `data-testid` values unchanged

After instrumenting, run `grep -r 'data-testid' src/ --include='*.jsx' | wc -l` to report the total count.

---

### PHASE 3 — WRITE COMPREHENSIVE AUDIT TESTS

Create `e2e/full-audit.spec.ts` (separate from the existing `data-flow.spec.ts`). This test file should:

#### 3A. Console & Error Monitoring (setup in beforeEach)

```ts
test.beforeEach(async ({ page }) => {
  const logs: string[] = [];
  const errors: string[] = [];

  page.on("console", (msg) => {
    logs.push(`[${msg.type()}] ${msg.text()}`);
    if (msg.type() === "error") errors.push(msg.text());
  });

  page.on("pageerror", (err) => {
    errors.push(`UNCAUGHT: ${err.message}`);
  });

  // Attach to test info for later assertions
  (page as any).__logs = logs;
  (page as any).__errors = errors;

  await page.goto("/");
  // Wait for app shell to confirm page loaded
  await page.locator("[data-testid='app-shell']").waitFor({ timeout: 10_000 });
});
```

#### 3B. Test Categories

Write tests for ALL of these categories. For each test, use a descriptive name.

**Category 1: TopBar elements**
- Clock displays a time string (matches HH:MM pattern or similar)
- Account selector is visible and shows an account ID
- Account selector opens dropdown on click, lists accounts
- TRADING badge is visible
- All 4 status dots (API, WS, QDB, Redis) are visible within health-bar
- Last tick timestamp has text content

**Category 2: MarketTicker elements**
- All 10 asset tabs are visible (MES, MNQ, ES, NQ, MYM, MGC, NKD, ZN, MCL, 6E)
- Each asset tab displays a price (contains digits)
- Each asset tab displays a change percentage
- Clicking an asset tab updates the chart header asset name
- MES tab price matches liveMarket data (if live mode)

**Category 3: RiskPanel data integrity**
- CAPITAL value is a formatted dollar amount
- EQUITY value is a formatted dollar amount
- Cumulative P&L displays with sign (+/-)
- MAX DD bar renders 10 segments
- MAX DD percentage is displayed
- DAILY DD bar renders 10 segments
- DAILY DD percentage is displayed
- Payout target progress bar is visible
- Remaining amount is displayed
- Day Stats: P&L, Profit Factor, Avg Win, Avg Loss, Wins, Losses, Trades, Win% all have values (not all "—" dashes)
- Risk Parameters: Max DD, Daily DD, Max Lots values are displayed
- Accounts section shows at least one account with ACTIVE/INACTIVE badge

**Category 4: ChartPanel data**
- Selected asset symbol is displayed in chart header
- Last price is displayed (not "—")
- Price change arrow and percentage are displayed
- Volume is displayed
- Bid/Ask spread is displayed
- OR Upper and OR Lower values are displayed (or "—" if no OR data)
- OR state badge shows a valid state string
- TradingView widget or custom chart container is visible

**Category 5: ActivePosition**
- Component renders (either position details or "No active position")
- If position exists: direction badge, asset, contracts, entry price, current price, P&L, SL/TP levels all visible

**Category 6: Signal & Execution**
- Pipeline stage pills are visible (WAITING, OR FORMING, SIGNAL GEN, EXECUTED)
- Exactly one pill is highlighted/active
- Auto Trade toggle is visible and clickable
- Clicking Auto Trade toggle changes its state

**Category 7: SignalCards**
- If signals exist: at least one signal card is visible with direction, asset, entry/SL/TP prices, P&L, confidence tier
- Session summary footer shows P&L, Win%, Signals count, Trades count
- If no signals: "No pending signals" message is shown

**Category 8: TradeLog**
- TRADE LOG header is visible
- Column headers (TIME, TICK, D, P&L, DUR) are visible
- Total footer shows trade count
- If trades exist: at least one row with time, asset, direction, P&L

**Category 9: SystemLog**
- SYSTEM LOG header is visible
- Filter buttons (All, Errors, Signals, Orders) are visible
- Clicking each filter button changes the displayed entries
- If notifications exist: entries display timestamp and message text
- Error entries are colored red
- Category labels (ERR, SIG, ORD) appear on categorized entries

**Category 10: Cross-component data consistency**
- The price shown in MarketTicker MES tab matches ChartPanel last price (when MES is selected)
- The Day P&L in RiskPanel matches the P&L in SignalCards session footer
- The trade count in RiskPanel Day Stats matches TradeLog footer count
- Pipeline stage in SignalExecutionBar matches what was set in store

**Category 11: Console health**
- No uncaught JavaScript errors in console
- No failed network requests (4xx/5xx) to `/api/*` endpoints (skip if backend is down)
- No WebSocket connection errors (skip if backend is down)
- No React key warnings or prop type warnings

**Category 12: Dynamic state changes (interaction tests)**
- Click a different asset in MarketTicker → chart header updates to show new asset
- Click Auto Trade toggle → toggle state visually changes
- Click SystemLog filter buttons → log entries filter correctly
- Click account selector → dropdown opens → click different account → selector updates

#### 3C. Zustand Store Direct Inspection

For critical data integrity checks, use `page.evaluate()` to read Zustand store state directly and compare it against what's rendered:

```ts
const storeState = await page.evaluate(() => {
  // Access Zustand stores via their internal APIs
  // The stores are module-scoped, so we need to access them through the window or React devtools
  // Alternative: inject a global accessor in the app for test mode
});
```

If direct store access isn't feasible, compare rendered values against each other (cross-component consistency tests above).

---

### PHASE 4 — EXECUTION LOOP

This is the critical phase. Follow this loop strictly:

```
WHILE (failing tests exist that are NOT category-e):
  1. Run: npm run test:e2e
  2. Read FULL output including any error messages and stack traces
  3. For EACH failure, classify it:

     (a) MISSING TESTID — you forgot to instrument an element
         → Add the data-testid to the component
         → Re-run

     (b) WRONG SELECTOR — test targets wrong element or wrong attribute
         → Read the component source to find the correct selector
         → Fix the test
         → Re-run

     (c) TIMING — element exists but takes longer to appear
         → Increase timeout for that specific assertion
         → Or add a waitFor before the assertion
         → Re-run

     (d) COMPONENT NOT BUILT — the element genuinely doesn't exist in the codebase
         → Comment out the test with: // TODO: enable when {component} is built
         → Re-run

     (e) DATA FLOW BUG — the element exists, is instrumented, but shows wrong/stale/missing data
         → DO NOT fix application logic
         → Record the finding: which element, what was expected, what was actual
         → Mark the test with: test.fixme() or test.skip() with a comment explaining the bug
         → Continue to next failure

     (f) HARDCODED VALUE — element shows a static value instead of dynamic store data
         → Record which element is hardcoded and what store field it SHOULD be reading
         → This is a data flow finding, not a test issue
         → Mark with test.fixme() and document

     (g) MISSING BACKEND DATA — the backend isn't sending a field that the UI expects
         → Record: which WS message type or API endpoint, which field is missing
         → Mark with test.skip() and document
         → Continue

  4. After fixing all (a), (b), (c), (d) type issues, re-run
  5. Repeat until stable — either all pass or remaining failures are (e), (f), (g)
END WHILE
```

**Hard limit: 10 iterations max.** If after 10 iterations you still have non-trivial failures, stop and report what's left.

**After each iteration, report:**
- Iteration number
- Tests passed / total
- What was fixed
- What remains

---

### PHASE 5 — SOURCE & APPLY MISSING FUNCTIONALITY

For any category (f) findings (hardcoded values that should be dynamic), you ARE authorized to fix the data binding in the component — but ONLY the data binding, nothing else:

- If MarketTicker shows hardcoded prices for assets other than MES, wire them to the store (this will require the backend to send multi-asset live_market data, or the store to track per-asset prices)
- If TopBar "Last tick: 0.3s ago" is hardcoded, wire it to `dashboardStore.timestamp` or `liveMarket.timestamp` and compute the elapsed time dynamically
- If any value shows "—" when the store actually has data, fix the binding

**For each fix:**
1. Read the component to understand what it currently renders
2. Read the store to understand what data is available
3. Make the minimal change to wire the component to the correct store field
4. Do NOT change styling, layout, or add new features
5. Re-run tests to confirm the fix works

For category (g) findings (missing backend data), DO NOT modify backend code. Just document what the backend needs to provide.

---

### PHASE 6 — FINAL REPORT

When the loop terminates, produce a structured report:

```
## GUI Audit Report — {date}

### Test Mode: {MOCK / LIVE}
### Backend Status: {UP / DOWN}

### Results: {passed}/{total} tests

### Passing Tests
[List each passing test name]

### Data Flow Bugs Found (category e)
[For each bug:]
- Component: {name}
- Element: {data-testid}
- Expected: {what should appear}
- Actual: {what appears instead}
- Root cause: {store field missing / WS message not sent / API not returning field}

### Hardcoded Values Fixed (category f)
[For each fix:]
- Component: {name}
- What was hardcoded: {description}
- What it's now wired to: {store field}
- Status: {FIXED / PARTIALLY FIXED}

### Missing Backend Data (category g)
[For each missing field:]
- Component expecting: {what}
- Store field: {which}
- Backend source needed: {WS message type or API endpoint}
- What backend needs to send: {field name and expected format}

### Components Not Yet Built (category d)
[List any commented-out tests and what they're waiting for]

### Console Health
- Uncaught errors: {count and details}
- Failed API requests: {count and details}
- React warnings: {count and details}

### Instrumentation Summary
- Total data-testid attributes: {count}
- Files modified: {list}

### Command to re-run:
npm run test:e2e
```

---

### CONSTRAINTS

- **DO NOT** modify Zustand store logic, WebSocket handling, or API client code
- **DO NOT** change component styling or layout
- **DO NOT** weaken assertions to force passes
- **DO NOT** mock WebSocket or API responses in tests — this validates REAL data flow
- **DO NOT** create new components or pages
- **DO** add `data-testid` and `data-status` attributes freely
- **DO** fix hardcoded values by wiring them to existing store data
- **DO** adjust test timeouts when the real operation is just slow
- **DO** document everything you find — the audit report is the primary deliverable
