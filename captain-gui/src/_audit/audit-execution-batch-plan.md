BATCH 0 — Foundation
Read src/_audit/FIX_PLAN.md, specifically BATCH_0. You are executing BATCH_0: Foundation.

Files: src/global.css, src/components/shared/StatusDot.jsx, src/components/shared/CollapsiblePanel.jsx, src/components/shared/DataTable.jsx, src/components/shared/StatusBadge.jsx
Issues: FIX-145, FIX-146, FIX-074..078, FIX-131..132, FIX-147

Rules:

- PRESERVE Bloomberg Terminal aesthetic: monospace fonts, near-black backgrounds (#0a0e17, #111827), 1px solid borders (#1e293b), Lucide icons
- DO NOT change layout structure, component hierarchy, or routing
- DO NOT add new dependencies
- Read each file before editing. Minimal changes only.

Specific fixes:

1. global.css (FIX-145): Add a global `*:focus-visible` ring style — something like `outline: 2px solid #3b82f6; outline-offset: 2px`. This cascades app-wide.
2. StatusDot.jsx (FIX-146): Accept a `label` prop, render `role="status"` and `aria-label={label}`. Add sr-only text span.
3. CollapsiblePanel.jsx (FIX-074..078): Add `aria-expanded={isOpen}` on toggle button, `aria-controls` pointing to panel id, generate unique `id` on content panel, wrap chevron chars in `aria-hidden="true"`, add `focus-visible` ring on toggle.
4. DataTable.jsx (FIX-131..132): Add `aria-label` on search input. Add a subtle gradient fade or shadow on the scroll edge as scroll affordance.
5. StatusBadge.jsx (FIX-147): Bump `text-[10px]` to `text-[11px]`.

After all fixes: list what you changed (one line per fix). Flag anything you couldn't fix and why.

BATCH 1 — App Shell
Read src/_audit/FIX_PLAN.md, specifically BATCH_1. You are executing BATCH_1: App Shell.

Files: src/App.jsx, src/api/client.js, src/auth/AuthContext.jsx, src/components/layout/TopBar.jsx
Issues: FIX-143..144, FIX-148..149, FIX-012..022

Rules:

- PRESERVE Bloomberg Terminal aesthetic exactly
- DO NOT change layout structure, routing, or add new dependencies
- Read each file before editing. Minimal changes only.

Specific fixes:

1. App.jsx (FIX-143): In RequireAuth, replace `return null` during loading with a centered spinner or skeleton matching the dark theme. (FIX-144): Set document.title per route.
2. client.js (FIX-148): Replace `window.location.href = "/login"` with a soft redirect approach — store a flag or use an event the AuthContext can listen to, avoiding hard nav that kills Zustand state.
3. AuthContext.jsx (FIX-149): Ensure the loading state is consumed by App.jsx's RequireAuth spinner.
4. TopBar.jsx (FIX-012..022): This is the big one:
  - Increase "Last tick" timestamp from text-[6.4px] to min text-[10px]
  - Increase health dots from 5.5px to min 8px
  - Add sr-only text to each status dot (e.g., "API: connected")
  - Implement ARIA dropdown on account selector: aria-expanded, aria-haspopup="listbox", role="listbox" on menu, arrow-key navigation, Escape to close
  - Increase account dropdown and Git Pull buttons to min h-[32px]
  - Increase nav tab text to min text-[10px] with min px-[10px] py-[6px]
  - Add focus-visible styling on all interactive elements
  - Wrap decorative Unicode (▼, ↻, ⚙, ✓, ✗, ↓) in aria-hidden="true"
  - Round h-[36.6px] to h-[36px] or h-9

After all fixes: list what you changed (one line per fix). Flag anything you couldn't fix and why.

BATCH 2 — Market + Chart
Read src/_audit/FIX_PLAN.md, specifically BATCH_2. You are executing BATCH_2: Market Data.

Files to edit: src/components/layout/MarketTicker.jsx, src/components/chart/ChartPanel.jsx
Files to DELETE: src/components/chart/CandlestickChart.jsx, src/components/chart/ChartOverlayToggles.jsx, src/components/chart/TimeframeSelector.jsx
Issues: FIX-039..046, FIX-068..073, FIX-154..156

Rules:

- PRESERVE Bloomberg Terminal aesthetic exactly
- DO NOT change layout structure, routing, or add new dependencies
- Read each file before editing. Minimal changes only.

Specific fixes:

1. MarketTicker.jsx (FIX-039..046):
  - FIX-039 CRITICAL: The 9 hardcoded tickers must show real data or "---" when no data. Check the liveMarket store — wire all tickers to it the same way MES is wired. If the store only supports one asset currently, show "---" for unconnected tickers and add a TODO comment.
  - FIX-040: Increase change % text from text-[7.5px] to min text-[10px]
  - FIX-041 CRITICAL: Convert ticker divs from `<div onClick>` to `<button>`. Add tabIndex, onKeyDown (Enter/Space).
  - FIX-042: Add sr-only text to green status dots
  - FIX-043: Increase ticker prices to min text-[10px], names to min text-[10px]
  - FIX-044: Add scroll shadow/fade indicator on overflow-x-auto
  - FIX-045: Add aria-current="true" on selected ticker
  - FIX-046: Increase status dots from 4.5px to min 6px
2. ChartPanel.jsx (FIX-068..073):
  - FIX-068 CRITICAL: Increase system info footer from text-[6.3px] to min text-[10px]
  - FIX-069: Make price display responsive — use clamp() or responsive text classes instead of fixed text-[45.8px]
  - FIX-070: Round fractional sizes (21.2 → 21 or text-xl, 15.2 → 15 or text-sm)
  - FIX-071: Add overflow-hidden and text-ellipsis on OHLC + Bid/Ask row
  - FIX-072: Differentiate "---" states (OR not formed vs no data)
  - FIX-073: Add visually-hidden h1 for page context
3. Delete the 3 dead chart files (FIX-154..156). Remove any imports referencing them in ChartPanel.

After all fixes: list what you changed (one line per fix). Flag anything you couldn't fix and why.

BATCH 3 — Risk + Trade
Read src/_audit/FIX_PLAN.md, specifically BATCH_3. You are executing BATCH_3: Risk + Trade Log.

Files: src/components/risk/RiskPanel.jsx, src/components/trading/TradeLog.jsx
Issues: FIX-001..011, FIX-106..109

Rules:

- PRESERVE Bloomberg Terminal aesthetic exactly
- DO NOT change layout structure, routing, or add new dependencies
- Read each file before editing. Minimal changes only.

Specific fixes:

1. RiskPanel.jsx (FIX-001..011): This is the most complex component.
  - FIX-001 CRITICAL: Replace fixed `w-[42.7px]` drawdown bar segments with flex percentages so they don't overflow
  - FIX-002 CRITICAL: Replace ALL fractional pixel values (text-[10.7px], leading-[16.1px], gap-[9.1px] etc.) with nearest Tailwind scale values. These are Figma auto-export artifacts.
  - FIX-003..004 CRITICAL: Add `role="progressbar"`, `aria-valuenow`, `aria-valuemin="0"`, `aria-valuemax="100"` on MDD and Daily DD drawdown bars
  - FIX-005: Replace Payout cards fixed `w-[201px]` with responsive grid (e.g., grid-cols-2 md:grid-cols-3)
  - FIX-006: Replace `min-w-[112px] max-w-[149px]` on risk param cards with flex-wrap-friendly sizing
  - FIX-007: Replace `font-['JetBrains_Mono']` with `font-mono`
  - FIX-008: Fix footer label clipping
  - FIX-009: Add `role="progressbar"` on payout target bar
  - FIX-010: Replace `mq450`/`mq750`/`mq1025` with Tailwind sm:/md:/lg:
  - FIX-011: Replace `pb-[29px]` with nearest Tailwind spacing (pb-7 = 28px)
2. TradeLog.jsx (FIX-106..109):
  - FIX-106: Increase column headers from text-[8.6px] to min text-[10px]
  - FIX-107: Replace fixed `gap-[33px]` with a proper table layout or auto grid
  - FIX-108: Convert div grid to semantic `<table>` with `<thead>`/`<tbody>`/`<th>`/`<td>` so screen readers can navigate it as tabular data
  - FIX-109: Increase total footer text slightly

After all fixes: list what you changed (one line per fix). Flag anything you couldn't fix and why.

BATCH 4 — Position + AIM
Read src/_audit/FIX_PLAN.md, specifically BATCH_4. You are executing BATCH_4: Active Position + AIM Registry.

Files: src/components/trading/ActivePosition.jsx, src/components/aim/AimRegistryPanel.jsx
Issues: FIX-079..083, FIX-031..038

Rules:

- PRESERVE Bloomberg Terminal aesthetic exactly
- DO NOT change layout structure, routing, or add new dependencies
- Read each file before editing. Minimal changes only.

Specific fixes:

1. ActivePosition.jsx (FIX-079..083):
  - FIX-079 CRITICAL: Replace hardcoded `pl-[346px] pr-[265px]` on SL/TP bar with percentage-based or flex positioning that adapts to container width
  - FIX-080 CRITICAL: Increase ENTRY/CURRENT/SL/TP labels from text-[7.2px] to min text-[10px]
  - FIX-081: Round text-[18.4px] to text-lg or text-[18px]
  - FIX-082: Increase direction badge/contracts/order info from text-[8.2px] to min text-[10px]
  - FIX-083: Replace mq450/mq750/mq1025 with Tailwind sm:/md:/lg:
2. AimRegistryPanel.jsx (FIX-031..038):
  - FIX-031 CRITICAL: Increase Activate/Deactivate buttons from py-0.5 text-[9px] to min h-[32px] text-[11px]
  - FIX-032 CRITICAL: Convert AimCard from `<div onClick>` to proper `<button>` or add `role="button"`, `tabIndex={0}`, `onKeyDown` (Enter/Space)
  - FIX-033: Increase tier badge from text-[8px] to min text-[10px]
  - FIX-034: Increase AIM card content from text-[10px] to text-[11px], increase padding from p-2 to p-3
  - FIX-035..036: Add `role="progressbar"`, `aria-valuenow`, `aria-valuemin`, `aria-valuemax` on weight and warmup bars
  - FIX-037: Fix tier badge overlap with status badge — adjust positioning
  - FIX-038: Clean up redundant grid breakpoints (grid-cols-4 2xl:grid-cols-4 xl:grid-cols-4 → just grid-cols-4)

After all fixes: list what you changed (one line per fix). Flag anything you couldn't fix and why.

BATCH 5 — Modal + SysLog
Read src/_audit/FIX_PLAN.md, specifically BATCH_5. You are executing BATCH_5: AIM Modal + System Log.

Files: src/components/aim/AimDetailModal.jsx, src/components/system/SystemLog.jsx
Issues: FIX-047..053, FIX-061..067

Rules:

- PRESERVE Bloomberg Terminal aesthetic exactly
- DO NOT change layout structure, routing, or add new dependencies
- Read each file before editing. Minimal changes only.

Specific fixes:

1. AimDetailModal.jsx (FIX-047..053):
  - FIX-047 CRITICAL: Add `role="dialog"`, `aria-modal="true"`, `aria-labelledby` pointing to the modal title
  - FIX-048 CRITICAL: Implement focus trap. On open, cycle Tab within modal. On close, return focus to trigger. Use a useEffect with keydown listener — no new deps needed.
  - FIX-049 CRITICAL: On mount, auto-focus the close button or first focusable element inside modal
  - FIX-050 CRITICAL: Add `aria-label="Close"` on close button
  - FIX-051: Increase close button to min w-[32px] h-[32px]
  - FIX-052: Increase body text from text-[10px] to text-[11px]
  - FIX-053: Add `aria-label` or `role="img"` with alt text to CheckIcon ✓/✗
2. SystemLog.jsx (FIX-061..067):
  - FIX-061 CRITICAL: Implement proper ARIA tablist: role="tablist" on tab container, role="tab" on each tab button, role="tabpanel" on content, aria-selected on active tab, arrow-key navigation between tabs
  - FIX-062 CRITICAL: Add `aria-pressed={isActive}` on filter buttons (ALL/Errors/Signals/Orders)
  - FIX-063: Increase filter button text from text-[8.6px] to min text-[10px]
  - FIX-064: Increase category labels from fontSize: "8px" to min 10px, convert from inline style to Tailwind
  - FIX-065: Convert all remaining inline styles to Tailwind classes
  - FIX-066: Increase log entry text from text-[9.7px] to text-[11px], increase leading from leading-[13.6px] to leading-relaxed
  - FIX-067: Add focus-visible styling on tab switching buttons

After all fixes: list what you changed (one line per fix). Flag anything you couldn't fix and why.

BATCH 6 — Signals + Dashboard
Read src/_audit/FIX_PLAN.md, specifically BATCH_6. You are executing BATCH_6: Signals + Dashboard Page.

Files: src/components/signals/SignalCards.jsx, src/components/signals/SignalExecutionBar.jsx, src/pages/DashboardPage.jsx
Issues: FIX-098..105, FIX-089..093

Rules:

- PRESERVE Bloomberg Terminal aesthetic exactly
- DO NOT change layout structure, routing, or add new dependencies
- Read each file before editing. Minimal changes only.

Specific fixes:

1. SignalCards.jsx (FIX-098..101):
  - Increase direction badges from text-[8px] to min text-[10px]
  - Increase confidence tier badge from text-[7px] to min text-[10px]
  - Increase clear button from text-[8px] px-[6px] py-[1px] to min h-[28px] px-[8px] text-[10px]
  - Normalize font sizes: collapse the 5-size range (11/10/9/8/7px) to 2-3 sizes max (11/10px)
2. SignalExecutionBar.jsx (FIX-102..105):
  - Replace fixed `w-[558.7px]` with `w-full` or `max-w-xl` flex layout
  - Add `aria-current="step"` on active pipeline stage pill
  - Round text-[12.1px] to text-xs (12px)
  - Replace mq750/mq450 with Tailwind sm:/md:
3. DashboardPage.jsx (FIX-089..093):
  - FIX-089 CRITICAL: Gate mock data injection behind `import.meta.env.VITE_DEV_MOCK === 'true'` instead of blanket `import.meta.env.DEV`
  - Increase ResizeHandle from 5px to 8px with visible drag indicator (3 dots or line)
  - Raise panel minSize from 5 to 15
  - Add a loading skeleton or spinner for initial API data fetch
  - Add visually-hidden h1 for screen reader landmarks

After all fixes: list what you changed (one line per fix). Flag anything you couldn't fix and why.

BATCH 7 — Replay Controls
Read src/_audit/FIX_PLAN.md, specifically BATCH_7. You are executing BATCH_7: Replay Controls.

Files: src/components/replay/PlaybackControls.jsx, src/components/replay/ReplayConfigPanel.jsx
Issues: FIX-023..030, FIX-054..060

Rules:

- PRESERVE Bloomberg Terminal aesthetic exactly
- DO NOT change layout structure, routing, or add new dependencies
- Read each file before editing. Minimal changes only.

Specific fixes:

1. PlaybackControls.jsx (FIX-023..030):
  - FIX-023..024 CRITICAL: Add aria-label="Play"/"Pause"/"Skip" on Unicode button elements
  - Increase Play/Pause from 24px to min 32px
  - Increase speed pills from text-[8px] to min text-[10px] with min h-[28px]
  - Increase progress bar from h-[3px] to h-[6px]
  - Add aria-pressed on active speed button
  - Add role="progressbar", aria-valuenow/min/max on progress bar
  - FIX-030 LOW: Add Space for play/pause keyboard shortcut if feasible
2. ReplayConfigPanel.jsx (FIX-054..060):
  - Increase labels from text-[8px] to min text-[10px]
  - Increase toggle switches from h-[16px] w-[32px] to h-[20px] w-[40px]
  - Increase Run Replay button to min h-[36px] text-[12px]
  - Fix Label components: add htmlFor + matching id on inputs
  - Add aria-label on toggle switches
  - Add aria-label on preset select
  - Add aria-label on preset name input

After all fixes: list what you changed (one line per fix). Flag anything you couldn't fix and why.

BATCH 8 — Replay Panels
Read src/_audit/FIX_PLAN.md, specifically BATCH_8. You are executing BATCH_8: Replay Panels.

Files: src/components/replay/PipelineStepper.jsx, src/components/replay/BatchPnlReport.jsx, src/components/replay/AssetCard.jsx, src/components/replay/BlockDetail.jsx, src/components/replay/ReplaySummary.jsx
Issues: FIX-094..097, FIX-084..088, FIX-129..130, FIX-133..134, FIX-135..136

Rules:

- PRESERVE Bloomberg Terminal aesthetic exactly
- DO NOT change layout structure, routing, or add new dependencies
- Read each file before editing. Minimal changes only.

Specific fixes:

1. PipelineStepper.jsx (FIX-094..097): Convert stage divs to `<button>`, add aria-expanded, add sr-only text to circle indicators, increase circle size to min 20px
2. BatchPnlReport.jsx (FIX-084..088): Add aria-pressed on Daily/Overall toggle, add role="progressbar" on batch progress, increase toggle text to min 10px, style scrollbar for visibility, add descriptive aria-label on CSV button
3. AssetCard.jsx (FIX-129..130): Increase direction badge to min text-[10px], session badge to min text-[8px], add aria-busy="true" during loading shimmer
4. BlockDetail.jsx (FIX-133..134): Flatten nested scroll to single scroll container, add title attribute or tooltip on truncated reason column
5. ReplaySummary.jsx (FIX-135..136): Increase button touch targets to min h-[32px], increase trades table max-h from 160px to 240px

After all fixes: list what you changed (one line per fix). Flag anything you couldn't fix and why.

BATCH 9 — Pages Group A
Read src/_audit/FIX_PLAN.md, specifically BATCH_9. You are executing BATCH_9: Pages A.

Files: src/pages/HistoryPage.jsx, src/pages/LoginPage.jsx, src/pages/ModelsPage.jsx, src/pages/ReplayPage.jsx, src/components/replay/WhatIfComparison.jsx
Issues: FIX-110..122, FIX-137..138

Rules:

- PRESERVE Bloomberg Terminal aesthetic exactly
- DO NOT change layout structure, routing, or add new dependencies
- Read each file before editing. Minimal changes only.

Specific fixes:

1. HistoryPage.jsx (FIX-110..113): Add role="tablist" on tab container, role="tab" + aria-selected on buttons, role="tabpanel" on content, increase tab button padding to min py-2 px-4
2. LoginPage.jsx (FIX-114..116): Increase submit button to min h-[44px], add aria-describedby linking error message to input, add role="alert" on error div, remove autoFocus (or gate behind desktop check)
3. ModelsPage.jsx (FIX-117..119): Add TODO comment about independent data fetch for direct nav, increase grid to grid-cols-2 md:grid-cols-3
4. ReplayPage.jsx (FIX-120..122): Add responsive breakpoint on 3-col grid (stack on narrow), increase drag handle to h-[8px], add role="separator" + aria-label on drag handle
5. WhatIfComparison.jsx (FIX-137..138): Increase max-h from 120px to 200px on contracts scroll, add responsive handling for 4-col grid overflow

After all fixes: list what you changed (one line per fix). Flag anything you couldn't fix and why.

BATCH 10 — Pages Group B
Read src/_audit/FIX_PLAN.md, specifically BATCH_10. You are executing BATCH_10: Pages B.

Files: src/pages/ReportsPage.jsx, src/pages/SystemOverviewPage.jsx, src/pages/ProcessesPage.jsx, src/pages/ConfigPage.jsx, src/pages/SettingsPage.jsx
Issues: FIX-123..128, FIX-139..140, FIX-150..151

Rules:

- PRESERVE Bloomberg Terminal aesthetic exactly
- DO NOT change layout structure, routing, or add new dependencies
- Read each file before editing. Minimal changes only.

Specific fixes:

1. ReportsPage.jsx (FIX-123..125): Add responsive breakpoint (grid-cols-1 md:grid-cols-3), replace magic 140px in max-h calc with a CSS variable or comment explaining the value, add aria-current="true" on selected report type
2. SystemOverviewPage.jsx (FIX-126..128): Increase text sizes from text-[10px] to text-[11px], improve stub section messages (replace "available via RPT-XX" with clearer "Coming soon — data source not yet connected"), add aria-label on radar chart SVG container
3. ProcessesPage.jsx (FIX-139..140): Increase badge text to min text-[10px], increase file path text to min text-[10px]
4. ConfigPage.jsx (FIX-150): Improve stub messaging — add a meaningful placeholder explaining what will go here
5. SettingsPage.jsx (FIX-151): Add aria-pressed or aria-checked on theme toggle button

After all fixes: list what you changed (one line per fix). Flag anything you couldn't fix and why.

BATCH 11 — Cleanup
Read src/_audit/FIX_PLAN.md, specifically BATCH_11. You are executing BATCH_11: Stores + WS + Cleanup.

Files: src/stores/dashboardStore.js, src/stores/notificationStore.js, src/ws/useWebSocket.js, src/components/chart/TradingViewWidget.jsx
Issues: FIX-141..142, FIX-153, FIX-152, FIX-157

Rules:

- DO NOT change layout structure, routing, or add new dependencies
- Read each file before editing. Minimal changes only.

Specific fixes:

1. dashboardStore.js (FIX-141..142): Add explicit fallback for unknown direction values (0, null, "BUY" → map to normalized "LONG"/"SHORT"/"UNKNOWN"). Cap localStorage signal archive at 500 entries with FIFO pruning.
2. notificationStore.js (FIX-153): Add max-size cap of 500 notifications. When adding beyond cap, shift oldest off the array.
3. useWebSocket.js (FIX-152): On eviction (4001) or auth failure (4003) close codes, push a visible notification via notificationStore (e.g., "WebSocket disconnected: session evicted" or "WebSocket disconnected: authentication failed").
4. TradingViewWidget.jsx (FIX-157): Add min-height (e.g., min-h-[200px]) or a guard that checks parent height > 0 before rendering the widget to prevent zero-height flash.

After all fixes: list what you changed (one line per fix). Flag anything you couldn't fix and why.

Each prompt is self-contained — paste into a fresh Claude Code session, let it run, then git add -A && git commit -m "ux-audit: batch N — [name]" 

18:21Deciphered batch-to-skill mapping requirements for command invocationDeciphered batch-to-skill mapping requirements for command invocationBatchSkill CommandWhyBATCH 0/baseline-ui review src/components/shared/Foundation components — enforces Tailwind consistency, spacing scale, a11y primitivesBATCH 1/fixing-accessibility src/components/layout/TopBar.jsxHeavy ARIA work (dropdown pattern, keyboard nav, sr-only text)BATCH 2/baseline-ui review src/components/layout/MarketTicker.jsx src/components/chart/ChartPanel.jsxSizing cleanup, Figma artifact removal, semantic element conversionBATCH 3/baseline-ui review src/components/risk/RiskPanel.jsx src/components/trading/TradeLog.jsxBiggest Figma-to-Tailwind refactor — fractional px, fixed widths, layout anti-patternsBATCH 4/baseline-ui review src/components/trading/ActivePosition.jsx src/components/aim/AimRegistryPanel.jsxLayout rewrite (hardcoded px → flex), button conversion, progressbar ARIABATCH 5/fixing-accessibility src/components/aim/AimDetailModal.jsx src/components/system/SystemLog.jsxFocus trap, ARIA dialog, ARIA tablist — pure accessibility patternsBATCH 6/baseline-ui review src/components/signals/ src/pages/DashboardPage.jsxSizing normalisation, fixed-width removal, breakpoint cleanupBATCH 7/fixing-accessibility src/components/replay/PlaybackControls.jsx src/components/replay/ReplayConfigPanel.jsxaria-label, aria-pressed, htmlFor linking, input labellingBATCH 8/baseline-ui review src/components/replay/5 files, all sizing bumps + ARIA sprinkle — baseline sweep is fastestBATCH 9/fixing-accessibility src/pages/HistoryPage.jsx src/pages/LoginPage.jsx src/pages/ReplayPage.jsxARIA tab patterns, form a11y, role="separator"BATCH 10/baseline-ui review src/pages/ReportsPage.jsx src/pages/SystemOverviewPage.jsx src/pages/ProcessesPage.jsxMinor sizing/stub fixes — light baseline passBATCH 11None — no skill neededStore logic + JS only, no UI components