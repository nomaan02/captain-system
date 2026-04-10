# Fix Plan

**Branch:** `ux-audit-overhaul`
**Date:** 2026-04-10
**Sources:** `STRUCTURAL_AUDIT.md` (93 issues) + `A11Y_AUDIT.md` (50 issues)
**After dedup:** 143 unique issues across 44 files
**Breakdown:** 31 CRITICAL, 81 MEDIUM, 31 LOW

---

## Issue Registry

Grouped by component file path, sorted by issue count descending.
Source: `STR` = structural audit, `A11Y` = accessibility audit, `BOTH` = merged duplicate.

---

### src/components/risk/RiskPanel.jsx (11 issues)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-001 | CRITICAL | Drawdown bar segments (10 x `w-[42.7px]`) overflow container below 470px, causes horizontal scroll | STR |
| FIX-002 | CRITICAL | Fractional pixel dimensions throughout (`text-[10.7px]`, `leading-[16.1px]`, `gap-[9.1px]`) -- Figma auto-export artifacts | STR |
| FIX-003 | CRITICAL | MDD drawdown bar has no `role="progressbar"`, `aria-valuenow/min/max` -- screen readers get nothing | A11Y |
| FIX-004 | CRITICAL | Daily DD drawdown bar has no ARIA -- same issue as MDD bar | A11Y |
| FIX-005 | MEDIUM | Payout Info cards fixed `w-[201px]` (6 cards = 1206px), wrap unevenly at intermediate widths | STR |
| FIX-006 | MEDIUM | Risk parameter cards `min-w-[112px] max-w-[149px]` cannot wrap cleanly at narrow panel widths | STR |
| FIX-007 | MEDIUM | Uses `font-['JetBrains_Mono']` directly instead of `font-mono` Tailwind class | STR |
| FIX-008 | MEDIUM | Footer labels clip on narrow panels despite `overflow-x-auto` | STR |
| FIX-009 | MEDIUM | Payout target bar has no `role="progressbar"` or value attributes | A11Y |
| FIX-010 | LOW | Custom breakpoint classes `mq450`, `mq750`, `mq1025` inconsistent with Tailwind `sm:`/`md:`/`lg:` | STR |
| FIX-011 | LOW | `pb-[29px]` bottom padding is Figma pixel-perfect artifact | STR |

---

### src/components/layout/TopBar.jsx (11 issues)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-012 | CRITICAL | "Last tick" timestamp uses `text-[6.4px]` (~4.8pt) -- sub-readable, operationally important | STR |
| FIX-013 | CRITICAL | Health status dots `w-[5.5px] h-[5.5px]` -- barely visible, convey critical system health | STR |
| FIX-014 | CRITICAL | Status dots (API, WS, QDB, Redis) have no accessible text -- colour-only status | A11Y |
| FIX-015 | CRITICAL | Account dropdown missing ARIA pattern: no `aria-expanded`, `aria-haspopup`, `role="listbox"`, no keyboard arrow-key nav | BOTH |
| FIX-016 | MEDIUM | Account dropdown button `h-[20px]` with `text-[8.6px]` -- below 44px touch target | STR |
| FIX-017 | MEDIUM | Git Pull button `h-[20px]` with `text-[8.2px]` -- small touch target for destructive action | STR |
| FIX-018 | MEDIUM | Nav tabs `text-[9.1px]` with `px-[7px]` -- targets ~28x20px | STR |
| FIX-019 | MEDIUM | No `focus-visible` styling on any buttons (dropdown, git pull, dropdown items) | STR |
| FIX-020 | MEDIUM | Dropdown chevron `▼` announced by screen readers -- wrap in `aria-hidden="true"` | A11Y |
| FIX-021 | MEDIUM | Git Pull button Unicode icons (`↻`, `⚙`, `✓`, `✗`, `↓`) announced by screen readers | A11Y |
| FIX-022 | LOW | Bar height `h-[36.6px]` -- fractional pixel causes subpixel rendering artifacts | STR |

---

### src/components/replay/PlaybackControls.jsx (8 issues)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-023 | CRITICAL | Play/Pause button content is Unicode `⏸`/`▶` with no `aria-label` | A11Y |
| FIX-024 | CRITICAL | Skip button content is Unicode `⏭` with no `aria-label` | A11Y |
| FIX-025 | MEDIUM | Play/Pause button `w-[24px] h-[24px]` -- below 44px touch target for primary action | STR |
| FIX-026 | MEDIUM | Speed pills at `text-[8px]` -- small text and small click targets | STR |
| FIX-027 | MEDIUM | Progress bar `h-[3px]` -- nearly invisible, very hard to click | STR |
| FIX-028 | MEDIUM | Speed selection buttons lack `aria-pressed` for active speed | A11Y |
| FIX-029 | MEDIUM | Progress bar missing `role="progressbar"`, `aria-valuenow/min/max` | A11Y |
| FIX-030 | LOW | No keyboard shortcuts for Play/Pause/Speed | STR |

---

### src/components/aim/AimRegistryPanel.jsx (8 issues)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-031 | CRITICAL | Activate/Deactivate buttons `py-0.5 text-[9px]` (~18-20px height) -- critically small for live-system actions | STR |
| FIX-032 | CRITICAL | AimCard is clickable `<div>` with no `role="button"`, `tabIndex`, `onKeyDown` | BOTH |
| FIX-033 | MEDIUM | Tier badge `text-[8px]` absolutely positioned -- sub-readable on many displays | STR |
| FIX-034 | MEDIUM | AIM card content `text-[10px]` throughout with `p-2` -- very dense | STR |
| FIX-035 | MEDIUM | Weight progress bar has no `role="progressbar"`, `aria-valuenow/min/max` | A11Y |
| FIX-036 | MEDIUM | Warmup progress bar has no ARIA -- same as weight bar | A11Y |
| FIX-037 | MEDIUM | Tier badge `absolute top-1.5 right-1.5` can overlap status badge on narrow cards | A11Y |
| FIX-038 | LOW | Grid uses `grid-cols-4 2xl:grid-cols-4 xl:grid-cols-4` -- redundant breakpoints | STR |

---

### src/components/layout/MarketTicker.jsx (8 issues)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-039 | CRITICAL | 9 of 10 tickers show hardcoded stale prices (only MES is wired to `liveMarket`) -- data integrity | STR |
| FIX-040 | CRITICAL | Change percentages use `text-[7.5px]` (~5.6pt) -- sub-readable | STR |
| FIX-041 | CRITICAL | All 10 tickers are clickable `<div>` with no `role`, `tabIndex`, `onKeyDown` -- primary asset selector | BOTH |
| FIX-042 | CRITICAL | Green status dots have no accessible text -- colour-only "live" indicator | A11Y |
| FIX-043 | MEDIUM | Ticker prices `text-[9.8px]` and names `text-[9px]` -- below comfortable reading size | STR |
| FIX-044 | MEDIUM | `overflow-x-auto` on nav has no visual scroll indicator | STR |
| FIX-045 | MEDIUM | Selected ticker state not announced -- no `aria-current` or `aria-selected` | A11Y |
| FIX-046 | LOW | Status dots `w-[4.5px] h-[4.5px]` -- imperceptibly small | STR |

---

### src/components/aim/AimDetailModal.jsx (7 issues)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-047 | CRITICAL | Modal container missing `role="dialog"` and `aria-modal="true"` | BOTH |
| FIX-048 | CRITICAL | Focus not trapped inside modal -- Tab reaches elements behind backdrop | BOTH |
| FIX-049 | CRITICAL | Focus not set on open -- stays on trigger element behind overlay | A11Y |
| FIX-050 | CRITICAL | Close button text is `✕` with no `aria-label="Close"` | A11Y |
| FIX-051 | MEDIUM | Close button `px-2` with no min-height/min-width -- touch target ~20x20px | STR |
| FIX-052 | MEDIUM | All body text `text-[10px]` -- per-asset table cells dense and hard to scan | STR |
| FIX-053 | MEDIUM | CheckIcon `✓`/`✗` has no `aria-label` or `role="img"` -- ambiguous for screen readers | A11Y |

---

### src/components/replay/ReplayConfigPanel.jsx (7 issues)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-054 | MEDIUM | Labels use `text-[8px]` -- below comfortable reading size | STR |
| FIX-055 | MEDIUM | Toggle switches `h-[16px] w-[32px]` with `12px` knobs -- too small for touch | STR |
| FIX-056 | MEDIUM | Run Replay button `py-[6px] text-[11px]` -- small for primary action | STR |
| FIX-057 | MEDIUM | `Label` component renders `<label>` without `htmlFor` -- inputs not programmatically linked | A11Y |
| FIX-058 | MEDIUM | Toggle switches have `role="switch"` + `aria-checked` but missing `aria-label` | A11Y |
| FIX-059 | MEDIUM | Preset `<select>` has no `<label>` or `aria-label` | A11Y |
| FIX-060 | MEDIUM | Preset name input uses `placeholder` only -- no `aria-label` | A11Y |

---

### src/components/system/SystemLog.jsx (7 issues)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-061 | CRITICAL | Tab buttons ("SYSTEM LOG"/"TELEGRAM") missing ARIA tablist pattern: no `role="tablist/tab/tabpanel"`, no `aria-selected`, no arrow-key nav | A11Y |
| FIX-062 | CRITICAL | Filter buttons (ALL/Errors/Signals/Orders) missing `aria-pressed` -- active state colour-only | A11Y |
| FIX-063 | MEDIUM | Filter buttons at `text-[8.6px]` -- small click targets for frequent use | STR |
| FIX-064 | MEDIUM | Category labels inline `fontSize: "8px"` -- ERR/SIG/ORD barely legible | STR |
| FIX-065 | MEDIUM | Mixes Tailwind classes with inline styles -- two styling approaches in one component | STR |
| FIX-066 | MEDIUM | Log entries `leading-[13.6px]` at `text-[9.7px]` -- dense messages blur together | STR |
| FIX-067 | LOW | Tab switching buttons have no `focus-visible` styling | STR |

---

### src/components/chart/ChartPanel.jsx (6 issues)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-068 | CRITICAL | System info footer `text-[6.3px]` (~4.7pt) -- physically unreadable on all displays | STR |
| FIX-069 | MEDIUM | Price display `text-[45.8px]` -- no responsive scaling, overflows on narrow center panels | STR |
| FIX-070 | MEDIUM | Asset name `text-[21.2px]` and OHLC `text-[15.2px]` -- fractional sizes, inconsistent subpixel rendering | STR |
| FIX-071 | MEDIUM | OHLC + Bid/Ask flex row has no `overflow-hidden` or `text-overflow` truncation | STR |
| FIX-072 | LOW | OR values show "---" with no context about OR status (not formed vs data unavailable) | STR |
| FIX-073 | LOW | Heading hierarchy jump: `<h2>`/`<h3>` with no `<h1>` in DashboardPage context | A11Y |

---

### src/components/shared/CollapsiblePanel.jsx (5 issues)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-074 | CRITICAL | Toggle button missing `aria-expanded={isOpen}` -- collapsed/expanded state not communicated | A11Y |
| FIX-075 | CRITICAL | Missing `aria-controls` -- button should point to content panel's `id` | A11Y |
| FIX-076 | MEDIUM | Toggle button has no `focus-visible` styling -- keyboard focus invisible | STR |
| FIX-077 | LOW | Arrow characters (`▼`/`▶`) vary across fonts -- inconsistent alignment | STR |
| FIX-078 | LOW | Chevron character announced by screen readers -- wrap in `aria-hidden="true"` | A11Y |

---

### src/components/trading/ActivePosition.jsx (5 issues)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-079 | CRITICAL | SL/TP gradient bar uses hardcoded `pl-[346px] pr-[265px]` -- breaks completely below ~650px | STR |
| FIX-080 | CRITICAL | ENTRY/CURRENT/SL/TP labels at `text-[7.2px]` (~5.4pt) -- sub-readable, operationally critical info | STR |
| FIX-081 | MEDIUM | P&L display `text-[18.4px]` -- fractional pixel from Figma export | STR |
| FIX-082 | MEDIUM | Direction badge, contracts, order info all `text-[8.2px]` -- borderline readable | STR |
| FIX-083 | MEDIUM | Uses `mq450`/`mq750`/`mq1025` Figma breakpoints inconsistently with rest of app | STR |

---

### src/components/replay/BatchPnlReport.jsx (5 issues)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-084 | MEDIUM | View toggle buttons ("Daily"/"Overall") at `text-[8px]` -- tiny click targets | STR |
| FIX-085 | MEDIUM | Scrollbar browser-default, invisible on macOS/trackpad until hover | STR |
| FIX-086 | MEDIUM | View toggle buttons lack `aria-pressed` for active state | A11Y |
| FIX-087 | MEDIUM | Batch progress bar missing `role="progressbar"` and value attributes | A11Y |
| FIX-088 | MEDIUM | CSV download button `aria-label` should be "Download as CSV" for clarity | A11Y |

---

### src/pages/DashboardPage.jsx (5 issues)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-089 | CRITICAL | DEV mock data injected on every mount when `import.meta.env.DEV` -- should be `.env` toggle | STR |
| FIX-090 | MEDIUM | `ResizeHandle` width/height 5px -- standard is 8-12px with visible drag indicator | STR |
| FIX-091 | MEDIUM | Panel `minSize={5}` allows shrinking to 5% height -- content becomes unreadable | STR |
| FIX-092 | LOW | No loading skeleton/spinner while initial API data loads | STR |
| FIX-093 | LOW | No `<h1>` heading for screen reader navigation landmarks | A11Y |

---

### src/components/replay/PipelineStepper.jsx (4 issues)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-094 | MEDIUM | Stage buttons are clickable divs with no `role="button"`, `tabIndex`, keyboard support | STR |
| FIX-095 | MEDIUM | Circle indicators `w-[14px] h-[14px]` -- small touch targets | STR |
| FIX-096 | MEDIUM | Stage buttons lack `aria-expanded` for toggled detail view | A11Y |
| FIX-097 | MEDIUM | Circle status indicators (green/red/blue) are visual-only -- no text fallback | A11Y |

---

### src/components/signals/SignalCards.jsx (4 issues)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-098 | MEDIUM | Direction badges `text-[8px] leading-[12px]` -- below comfortable reading size | STR |
| FIX-099 | MEDIUM | Confidence tier badge `text-[7px] leading-[10px]` -- sub-readable on most displays | STR |
| FIX-100 | MEDIUM | Clear button `text-[8px]` with `px-[6px] py-[1px]` -- touch target ~30x14px | STR |
| FIX-101 | LOW | Five different font sizes in one card row (11/10/9/8/7px) -- visual noise | STR |

---

### src/components/signals/SignalExecutionBar.jsx (4 issues)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-102 | MEDIUM | Fixed-width inner container `w-[558.7px]` prevents shrinking below that width | STR |
| FIX-103 | MEDIUM | Pipeline stage pills have no `aria-current="step"` for active stage | A11Y |
| FIX-104 | LOW | Pipeline stage pills `text-[12.1px]` -- rare fractional size | STR |
| FIX-105 | LOW | Uses `mq750`/`mq450` custom breakpoints instead of standard Tailwind | STR |

---

### src/components/trading/TradeLog.jsx (4 issues)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-106 | MEDIUM | Column headers at `text-[8.6px]` -- undersized | STR |
| FIX-107 | MEDIUM | Fixed `gap-[33px]` column spacing causes overlap on narrow right panels | STR |
| FIX-108 | MEDIUM | Uses `<div>` grid instead of `<table>` -- screen readers cannot navigate as tabular data | A11Y |
| FIX-109 | LOW | Total footer `text-[9.7px]` -- adequate but small | STR |

---

### src/pages/HistoryPage.jsx (4 issues)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-110 | MEDIUM | WS-dependent: shows "Connect to dashboard first" when visited directly via URL | STR |
| FIX-111 | MEDIUM | Tab buttons `px-3 py-1.5 text-[10px]` -- targets ~60x24px, passable but small | STR |
| FIX-112 | MEDIUM | Tab buttons missing ARIA tab pattern: no `role="tab/tablist"`, no `aria-selected` | A11Y |
| FIX-113 | LOW | "Trade Outcomes" and "System Events" tabs wired to empty data arrays | STR |

---

### src/pages/LoginPage.jsx (3 issues)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-114 | MEDIUM | Submit button `py-2 text-[10px]` (~30px height) -- below 44px touch target | STR |
| FIX-115 | MEDIUM | Error message not linked to input via `aria-describedby`; missing `role="alert"` | A11Y |
| FIX-116 | LOW | `autoFocus` can cause viewport jump on mobile | STR |

---

### src/pages/ModelsPage.jsx (3 issues)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-117 | MEDIUM | WS-dependent: requires DashboardPage mount for WebSocket -- "Connect first" on direct nav | STR |
| FIX-118 | MEDIUM | AIM registry uses `grid-cols-1` -- single column for 270+ AIM state rows | STR |
| FIX-119 | LOW | Duplicates AIM display logic already in `AimRegistryPanel` | STR |

---

### src/pages/ReplayPage.jsx (3 issues)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-120 | MEDIUM | Fixed 3-column grid `grid-cols-[280px_1fr_280px]` -- center crushed below ~700px viewport | STR |
| FIX-121 | MEDIUM | Bottom panel drag handle `h-[5px]` -- standard is 8-12px | STR |
| FIX-122 | MEDIUM | Drag handle has no `role`, `aria-label`, or keyboard resize support | A11Y |

---

### src/pages/ReportsPage.jsx (3 issues)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-123 | MEDIUM | 3-column grid `grid-cols-3` columns too narrow below ~600px | STR |
| FIX-124 | MEDIUM | Report type list `max-h-[calc(100vh-140px)]` uses magic number 140px | STR |
| FIX-125 | MEDIUM | Report type selector buttons lack `aria-current` or `aria-selected` | A11Y |

---

### src/pages/SystemOverviewPage.jsx (3 issues)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-126 | MEDIUM | Multiple sections `text-[10px]` throughout -- dense governance/data quality tables | STR |
| FIX-127 | MEDIUM | Placeholder sections display "available via RPT-XX" -- stubs with no actionable content | STR |
| FIX-128 | MEDIUM | Radar chart renders SVG only -- no text alternative for screen readers | A11Y |

---

### src/components/replay/AssetCard.jsx (2 issues)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-129 | MEDIUM | Direction badges `text-[7px]`, session badges `text-[6px]` -- session badges unreadable | STR |
| FIX-130 | LOW | Loading shimmer has no `aria-busy="true"` on card container | A11Y |

---

### src/components/shared/DataTable.jsx (2 issues)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-131 | MEDIUM | `overflow-x-auto` on table wrapper has no visual scroll indicator | STR |
| FIX-132 | MEDIUM | Search input has no accessible label -- uses `placeholder` only | A11Y |

---

### src/components/replay/BlockDetail.jsx (2 issues)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-133 | MEDIUM | Nested scroll containers (`max-h-[300px]` outer + `max-h-[200px]` inner) confusing | STR |
| FIX-134 | MEDIUM | Reason column truncated at `max-w-[150px]` with no tooltip or expand | STR |

---

### src/components/replay/ReplaySummary.jsx (2 issues)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-135 | MEDIUM | What-If and Save buttons `py-[4px] text-[9px]` -- small touch targets | STR |
| FIX-136 | MEDIUM | Trades table `max-h-[160px]` -- very limited space, scrolling with 10 assets | STR |

---

### src/components/replay/WhatIfComparison.jsx (2 issues)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-137 | MEDIUM | Per-asset contracts `max-h-[120px]` -- very tight, easy to miss scrollability | STR |
| FIX-138 | LOW | 4-column comparison grid may overflow on fixed 280px right panel | STR |

---

### src/pages/ProcessesPage.jsx (2 issues)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-139 | MEDIUM | Block trigger badges at `text-[8px]` -- small | STR |
| FIX-140 | MEDIUM | Block source file paths at `text-[9px]` -- dense | STR |

---

### src/stores/dashboardStore.js (2 issues)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-141 | MEDIUM | Direction normalization: unexpected backend values (0, null, "BUY") fall through to raw UI display | STR |
| FIX-142 | LOW | `clearSignals` archives to `localStorage` with no size limit -- accumulates over months | STR |

---

### src/App.jsx (2 issues)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-143 | CRITICAL | `RequireAuth` returns `null` during auth loading -- blank white screen, no spinner/skeleton | STR |
| FIX-144 | LOW | No `<title>` set for `/models` route -- browser tab shows stale title | STR |

---

### src/global.css (1 issue)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-145 | CRITICAL | No `focus-visible` ring anywhere -- base layer resets borders, `focus:outline-none` used without replacement. WCAG 2.4.7 failure. Affects entire app. | A11Y |

---

### src/components/shared/StatusDot.jsx (1 issue)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-146 | CRITICAL | Coloured circle with no text, `aria-label`, `role`, or sr-only text. Status via colour alone. ~20 instances across app. WCAG 1.4.1 + 4.1.2 failure. | A11Y |

---

### src/components/shared/StatusBadge.jsx (1 issue)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-147 | LOW | `text-[10px]` with `whitespace-nowrap` -- adequate but on the small side | STR |

---

### src/api/client.js (1 issue)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-148 | MEDIUM | On 401, `window.location.href = "/login"` hard-navigates -- discards all Zustand state | STR |

---

### src/auth/AuthContext.jsx (1 issue)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-149 | MEDIUM | `loading` state `true` during initial token validation but no consumer shows loading indicator | STR |

---

### src/pages/ConfigPage.jsx (1 issue)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-150 | MEDIUM | Entire page is stub with "Pending backend endpoint integration" -- no timeline or workaround | STR |

---

### src/pages/SettingsPage.jsx (1 issue)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-151 | MEDIUM | Theme toggle button has no ARIA state -- doesn't communicate current theme | A11Y |

---

### src/ws/useWebSocket.js (1 issue)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-152 | MEDIUM | On eviction (4001) or auth failure (4003), UI has no visible indication of forced disconnect | STR |

---

### src/stores/notificationStore.js (1 issue)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-153 | LOW | Notifications array grows unbounded -- no max-size cap or auto-pruning | STR |

---

### src/components/chart/CandlestickChart.jsx (1 issue)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-154 | LOW | Dead code: `USE_CUSTOM_CHART` is `false` -- 187 lines never rendered. **Delete file.** | STR |

---

### src/components/chart/ChartOverlayToggles.jsx (1 issue)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-155 | LOW | Dead code: only renders when `USE_CUSTOM_CHART` is true (hardcoded false). **Delete file.** | STR |

---

### src/components/chart/TimeframeSelector.jsx (1 issue)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-156 | LOW | Dead code: never rendered. **Delete file.** | STR |

---

### src/components/chart/TradingViewWidget.jsx (1 issue)

| ID | Sev | Description | Source |
|----|-----|-------------|--------|
| FIX-157 | LOW | `position: absolute` with `inset: 0` inside relative parent may flash on initial render when parent height is 0 | STR |

---

## Execution Batches

Batches are ordered by dependency and impact. BATCH_0 is a prerequisite for all others (shared components cascade). Subsequent batches can run independently.

---

### BATCH_0: Foundation -- Global + Shared Components

**Prerequisite for all other batches.** Changes here cascade across the entire app.

| | |
|---|---|
| **Components** | 5 |
| **Issues** | 10 |
| **CRITICAL** | 4 |
| **Token cost** | **LOW** -- small files, targeted edits (1 CSS rule, add props, add ARIA attributes) |

**Files:**

| File | Issues | IDs |
|------|--------|-----|
| `src/global.css` | 1 | FIX-145 |
| `src/components/shared/StatusDot.jsx` | 1 | FIX-146 |
| `src/components/shared/CollapsiblePanel.jsx` | 5 | FIX-074..078 |
| `src/components/shared/DataTable.jsx` | 2 | FIX-131, 132 |
| `src/components/shared/StatusBadge.jsx` | 1 | FIX-147 |

**Key changes:**
- Add global `:focus-visible` ring in CSS (fixes keyboard nav across entire app)
- StatusDot: accept `label` prop, render `aria-label` + `role="status"`
- CollapsiblePanel: add `aria-expanded`, `aria-controls`, `id` on panel, `aria-hidden` on chevron
- DataTable: add `aria-label` on search input, scroll affordance indicator
- StatusBadge: bump `text-[10px]` to `text-[11px]`

---

### BATCH_1: App Shell -- Auth + Routing + TopBar

| | |
|---|---|
| **Components** | 4 |
| **Issues** | 15 |
| **CRITICAL** | 5 |
| **Token cost** | **HIGH** -- TopBar requires sizing overhaul, ARIA dropdown pattern, keyboard navigation |

**Files:**

| File | Issues | IDs |
|------|--------|-----|
| `src/App.jsx` | 2 | FIX-143, 144 |
| `src/api/client.js` | 1 | FIX-148 |
| `src/auth/AuthContext.jsx` | 1 | FIX-149 |
| `src/components/layout/TopBar.jsx` | 11 | FIX-012..022 |

**Key changes:**
- App.jsx: add spinner/skeleton in `RequireAuth` during auth loading
- client.js: replace hard navigation with React Router `navigate()`
- AuthContext: wire loading state to App.jsx spinner
- TopBar: increase all text to min 10px, increase touch targets to min 32px, implement ARIA dropdown (aria-expanded, aria-haspopup, role="menu", arrow-key nav), add sr-only text to status dots, wrap decorative Unicode in aria-hidden

---

### BATCH_2: Market Data -- Ticker + Chart

| | |
|---|---|
| **Components** | 2 (+ 3 dead code deletions) |
| **Issues** | 14 |
| **CRITICAL** | 5 |
| **Token cost** | **HIGH** -- MarketTicker needs structural rewrite (hardcoded data, a11y), ChartPanel sizing overhaul |

**Files:**

| File | Issues | IDs |
|------|--------|-----|
| `src/components/layout/MarketTicker.jsx` | 8 | FIX-039..046 |
| `src/components/chart/ChartPanel.jsx` | 6 | FIX-068..073 |

**Also delete (dead code):**
- `src/components/chart/CandlestickChart.jsx` (FIX-154)
- `src/components/chart/ChartOverlayToggles.jsx` (FIX-155)
- `src/components/chart/TimeframeSelector.jsx` (FIX-156)

**Key changes:**
- MarketTicker: wire all 10 tickers to `liveMarket` store (or show "---" when no data), convert `<div>` to `<button>`, add `aria-current="true"` on selected, add sr-only text to status dots, increase text sizes to min 10px
- ChartPanel: increase footer to min 10px, round fractional sizes, add overflow truncation on OHLC row
- Delete 3 dead chart files and remove their imports from ChartPanel

---

### BATCH_3: Risk + Trade Log

| | |
|---|---|
| **Components** | 2 |
| **Issues** | 15 |
| **CRITICAL** | 4 |
| **Token cost** | **HIGH** -- RiskPanel is most complex: full Figma-to-Tailwind layout refactor + ARIA |

**Files:**

| File | Issues | IDs |
|------|--------|-----|
| `src/components/risk/RiskPanel.jsx` | 11 | FIX-001..011 |
| `src/components/trading/TradeLog.jsx` | 4 | FIX-106..109 |

**Key changes:**
- RiskPanel: replace fixed-width drawdown bars with flex/percentage layout, replace all fractional px with Tailwind scale, add `role="progressbar"` + `aria-valuenow/min/max` on MDD/Daily DD/Payout bars, replace `font-['JetBrains_Mono']` with `font-mono`, replace `mq*` with Tailwind breakpoints, make Payout cards responsive grid
- TradeLog: convert `<div>` grid to `<table>`, replace fixed gap with table columns, increase header text

---

### BATCH_4: Active Position + AIM Registry

| | |
|---|---|
| **Components** | 2 |
| **Issues** | 13 |
| **CRITICAL** | 4 |
| **Token cost** | **HIGH** -- ActivePosition SL/TP bar needs layout rewrite, AimCard needs button conversion |

**Files:**

| File | Issues | IDs |
|------|--------|-----|
| `src/components/trading/ActivePosition.jsx` | 5 | FIX-079..083 |
| `src/components/aim/AimRegistryPanel.jsx` | 8 | FIX-031..038 |

**Key changes:**
- ActivePosition: replace hardcoded `pl-[346px] pr-[265px]` with percentage-based positioning on SL/TP bar, increase labels to min 10px, round fractional sizes, replace `mq*` with Tailwind breakpoints
- AimRegistryPanel: increase Activate/Deactivate buttons to min 32px height, convert AimCard from `<div onClick>` to `<button>`, add `role="progressbar"` on weight/warmup bars, increase tier badge to min 10px, fix grid breakpoints

---

### BATCH_5: AIM Modal + System Log

| | |
|---|---|
| **Components** | 2 |
| **Issues** | 14 |
| **CRITICAL** | 6 |
| **Token cost** | **HIGH** -- Focus trap implementation, ARIA dialog pattern, ARIA tablist pattern |

**Files:**

| File | Issues | IDs |
|------|--------|-----|
| `src/components/aim/AimDetailModal.jsx` | 7 | FIX-047..053 |
| `src/components/system/SystemLog.jsx` | 7 | FIX-061..067 |

**Key changes:**
- AimDetailModal: add `role="dialog"`, `aria-modal="true"`, `aria-labelledby`, implement focus trap (on open: move focus to modal, on Tab: cycle within modal), add `aria-label="Close"` on close button, increase close button touch target, add `aria-label` to CheckIcon
- SystemLog: implement ARIA tablist (role="tablist/tab/tabpanel", aria-selected, arrow-key nav), add `aria-pressed` on filter buttons, convert inline `fontSize` to Tailwind, increase text sizes to min 10px

---

### BATCH_6: Signals + Dashboard Page

| | |
|---|---|
| **Components** | 3 |
| **Issues** | 13 |
| **CRITICAL** | 1 |
| **Token cost** | **MED** -- sizing fixes, env toggle for mock data, ARIA attributes |

**Files:**

| File | Issues | IDs |
|------|--------|-----|
| `src/components/signals/SignalCards.jsx` | 4 | FIX-098..101 |
| `src/components/signals/SignalExecutionBar.jsx` | 4 | FIX-102..105 |
| `src/pages/DashboardPage.jsx` | 5 | FIX-089..093 |

**Key changes:**
- SignalCards: increase all text to min 10px, increase clear button touch target, normalize font size scale
- SignalExecutionBar: replace fixed `w-[558.7px]` with flex, add `aria-current="step"`, round fractional sizes, replace `mq*` breakpoints
- DashboardPage: gate mock data behind `VITE_DEV_MOCK` env var, increase resize handle to 8-12px, raise panel `minSize` to 15%, add loading skeleton

---

### BATCH_7: Replay Controls

| | |
|---|---|
| **Components** | 2 |
| **Issues** | 15 |
| **CRITICAL** | 2 |
| **Token cost** | **MED** -- sizing fixes, ARIA label/pressed attributes, input label linking |

**Files:**

| File | Issues | IDs |
|------|--------|-----|
| `src/components/replay/PlaybackControls.jsx` | 8 | FIX-023..030 |
| `src/components/replay/ReplayConfigPanel.jsx` | 7 | FIX-054..060 |

**Key changes:**
- PlaybackControls: add `aria-label` on play/pause/skip buttons, increase buttons to 32px min, increase speed pills to 10px, increase progress bar to 6-8px, add `aria-pressed` on speed buttons, add `role="progressbar"`
- ReplayConfigPanel: increase label text to 10px, increase toggle switch to 20x40, add `htmlFor`/`id` pairs on labels, add `aria-label` on toggles/select/input

---

### BATCH_8: Replay Panels

| | |
|---|---|
| **Components** | 5 |
| **Issues** | 15 |
| **CRITICAL** | 0 |
| **Token cost** | **MED** -- many small ARIA and sizing fixes across 5 files |

**Files:**

| File | Issues | IDs |
|------|--------|-----|
| `src/components/replay/PipelineStepper.jsx` | 4 | FIX-094..097 |
| `src/components/replay/BatchPnlReport.jsx` | 5 | FIX-084..088 |
| `src/components/replay/AssetCard.jsx` | 2 | FIX-129, 130 |
| `src/components/replay/BlockDetail.jsx` | 2 | FIX-133, 134 |
| `src/components/replay/ReplaySummary.jsx` | 2 | FIX-135, 136 |

**Key changes:**
- PipelineStepper: convert stage buttons to `<button>`, add `aria-expanded`, add text to circle indicators
- BatchPnlReport: add `aria-pressed` on toggles, add `role="progressbar"`, increase toggle text, style scrollbar, add `aria-label` on CSV button
- AssetCard: increase badge text to 10px, add `aria-busy` during loading
- BlockDetail: flatten nested scroll (single scroll container), add tooltip/expand on truncated reason
- ReplaySummary: increase button touch targets, increase trades table `max-h`

---

### BATCH_9: Pages Group A

| | |
|---|---|
| **Components** | 5 |
| **Issues** | 15 |
| **CRITICAL** | 0 |
| **Token cost** | **LOW** -- small targeted edits: ARIA tabs, sizing bumps, WS-dependency notes |

**Files:**

| File | Issues | IDs |
|------|--------|-----|
| `src/pages/HistoryPage.jsx` | 4 | FIX-110..113 |
| `src/pages/LoginPage.jsx` | 3 | FIX-114..116 |
| `src/pages/ModelsPage.jsx` | 3 | FIX-117..119 |
| `src/pages/ReplayPage.jsx` | 3 | FIX-120..122 |
| `src/components/replay/WhatIfComparison.jsx` | 2 | FIX-137, 138 |

**Key changes:**
- HistoryPage: add ARIA tab pattern (role="tablist/tab/tabpanel", aria-selected), increase tab button size
- LoginPage: increase submit button to 44px, add `aria-describedby` + `role="alert"` on error
- ModelsPage: add independent data fetch (or clear TODO note), increase grid cols
- ReplayPage: add responsive grid breakpoint, increase drag handle to 8px, add ARIA to drag handle
- WhatIfComparison: increase `max-h` on contracts scroll, handle grid overflow

---

### BATCH_10: Pages Group B

| | |
|---|---|
| **Components** | 5 |
| **Issues** | 10 |
| **CRITICAL** | 0 |
| **Token cost** | **LOW** -- mostly stub pages with small ARIA/sizing fixes |

**Files:**

| File | Issues | IDs |
|------|--------|-----|
| `src/pages/ReportsPage.jsx` | 3 | FIX-123..125 |
| `src/pages/SystemOverviewPage.jsx` | 3 | FIX-126..128 |
| `src/pages/ProcessesPage.jsx` | 2 | FIX-139, 140 |
| `src/pages/ConfigPage.jsx` | 1 | FIX-150 |
| `src/pages/SettingsPage.jsx` | 1 | FIX-151 |

**Key changes:**
- ReportsPage: add responsive grid breakpoint, replace magic 140px, add `aria-current` on selected report
- SystemOverviewPage: increase text sizes, improve stub section messaging, add aria-label on radar chart container
- ProcessesPage: increase badge/path text to 10px
- ConfigPage: improve stub messaging
- SettingsPage: add ARIA state to theme toggle

---

### BATCH_11: Stores + WebSocket + Dead Code Cleanup

| | |
|---|---|
| **Components** | 4 |
| **Issues** | 5 |
| **CRITICAL** | 0 |
| **Token cost** | **LOW** -- store guard clauses, WS disconnect indicator, widget fix |

**Files:**

| File | Issues | IDs |
|------|--------|-----|
| `src/stores/dashboardStore.js` | 2 | FIX-141, 142 |
| `src/stores/notificationStore.js` | 1 | FIX-153 |
| `src/ws/useWebSocket.js` | 1 | FIX-152 |
| `src/components/chart/TradingViewWidget.jsx` | 1 | FIX-157 |

**Key changes:**
- dashboardStore: add explicit fallback for unknown direction values, cap localStorage archive size
- notificationStore: add max-size cap (e.g., 500) with FIFO pruning
- useWebSocket: surface eviction/auth-failure as visible UI notification (use notificationStore)
- TradingViewWidget: guard against zero-height parent with min-height or layout check

---

## Batch Summary

| Batch | Name | Components | Issues | CRITICAL | Cost | Dependency |
|-------|------|-----------|--------|----------|------|------------|
| BATCH_0 | Foundation | 5 | 10 | 4 | LOW | None (do first) |
| BATCH_1 | App Shell | 4 | 15 | 5 | HIGH | BATCH_0 |
| BATCH_2 | Market + Chart | 2+3 del | 14+3 | 5 | HIGH | BATCH_0 |
| BATCH_3 | Risk + Trade | 2 | 15 | 4 | HIGH | BATCH_0 |
| BATCH_4 | Position + AIM | 2 | 13 | 4 | HIGH | BATCH_0 |
| BATCH_5 | Modal + SysLog | 2 | 14 | 6 | HIGH | BATCH_0 |
| BATCH_6 | Signals + Dash | 3 | 13 | 1 | MED | BATCH_0 |
| BATCH_7 | Replay Controls | 2 | 15 | 2 | MED | BATCH_0 |
| BATCH_8 | Replay Panels | 5 | 15 | 0 | MED | BATCH_0 |
| BATCH_9 | Pages A | 5 | 15 | 0 | LOW | BATCH_0 |
| BATCH_10 | Pages B | 5 | 10 | 0 | LOW | BATCH_0 |
| BATCH_11 | Cleanup | 4 | 5 | 0 | LOW | None |
| **Total** | | **44** | **157** | **31** | | |

---

## Recommended Execution Order

```
BATCH_0  (foundation -- prerequisite)
   |
   +---> BATCH_1 through BATCH_10 (can run in any order after BATCH_0)
   |
BATCH_11 (cleanup -- no dependencies, run anytime)
```

**Priority sequence for maximum impact:**
1. BATCH_0 (unblocks everything, 4 CRITICALs for zero-effort cascading fix)
2. BATCH_5 (6 CRITICALs -- highest CRITICAL density)
3. BATCH_1 (5 CRITICALs -- user sees TopBar on every page)
4. BATCH_2 (5 CRITICALs -- hardcoded data is a data integrity issue)
5. BATCH_3 (4 CRITICALs -- RiskPanel Figma layout overhaul)
6. BATCH_4 (4 CRITICALs -- ActivePosition breaks on resize)
7. BATCH_6 through BATCH_11 (MEDIUM/LOW -- polish)
