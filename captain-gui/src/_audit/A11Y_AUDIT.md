# Accessibility Audit

**Branch:** `ux-audit-overhaul`
**Date:** 2026-04-10
**Auditor:** Claude Code (automated)
**Stack:** React 18 + Vite + Tailwind + Zustand
**Scope:** All 43 component/page files under `src/`
**Theme context:** Dark theme -- `#0a0e17` background, `#111827` surface, `#1e293b` borders

---

## Severity Key

| Tag | Meaning |
|-----|---------|
| **CRITICAL** | Users cannot access, operate, or understand the control. WCAG A/AA failure. |
| **MEDIUM** | Degraded assistive technology experience. State not announced, semantics wrong. |
| **LOW** | Minor polish -- decorative aria, redundant announcements, dead-code-only issues. |

---

## Systemic Issues

These affect the entire application and should be addressed first.

### S-01 [CRITICAL] No focus-visible ring anywhere in the application

**File:** `src/global.css` (line 14-18)
**Snippet:** `*, *::before, *::after { border-width: 0; }`
**Why:** The base layer resets all border-width to 0, and dozens of components apply `focus:outline-none` without a replacement `focus-visible` ring. Keyboard users have **zero visual focus indicator** across the entire application. This is a WCAG 2.4.7 (Focus Visible) Level AA failure.
**Fix:** Add a global focus-visible ring in `global.css`:
```css
:focus-visible {
  outline: 2px solid #06b6d4;
  outline-offset: 2px;
}
```

### S-02 [CRITICAL] Clickable `<div>` pattern used instead of `<button>` throughout

**Files:** `MarketTicker.jsx`, `AimRegistryPanel.jsx` (AimCard)
**Why:** Multiple interactive elements use `<div onClick={...}>` with no `role="button"`, no `tabIndex={0}`, and no `onKeyDown` handler. Keyboard and screen reader users cannot activate these controls. WCAG 2.1.1 (Keyboard), 4.1.2 (Name, Role, Value).
**Scope:** ~12 clickable divs across the codebase.

### S-03 [CRITICAL] StatusDot conveys status via colour alone

**File:** `src/components/shared/StatusDot.jsx` (line 13-17)
**Snippet:** `<div className={...} style={{ width: size, height: size }} />`
**Why:** Renders a coloured circle with no text, no `aria-label`, no `role`, and no screen-reader-only text. Status is communicated solely by colour (green/red/amber/grey), violating WCAG 1.4.1 (Use of Color) and 4.1.2 (Name, Role, Value). Used in TopBar, ProcessesPage, SystemOverviewPage (~20 instances).

---

## Per-File Findings

### src/global.css

- **[CRITICAL] S-01 above.** No `focus-visible` rule defined. Every `focus:outline-none` in the codebase removes the default focus indicator with no replacement.

### src/components/shared/StatusDot.jsx

- **[CRITICAL] S-03 above.** The component is a bare `<div>` with colour only. Missing: `role="status"`, `aria-label={status}`, or adjacent sr-only text.

### src/components/shared/CollapsiblePanel.jsx

- **[CRITICAL] Missing `aria-expanded` on toggle button (line 28).** The `<button onClick={() => setIsOpen(!isOpen)}>` doesn't communicate expanded/collapsed state. Screen readers announce "button" with no state. Add `aria-expanded={isOpen}`.
- **[CRITICAL] Missing `aria-controls` (line 28).** Button should point to the content panel's id via `aria-controls`. Collapsible content (line 42) needs an `id` attribute.
- **[LOW] Chevron character announced by screen readers (line 37).** The `▼`/`▶` character should be wrapped in `<span aria-hidden="true">`.

### src/components/shared/DataTable.jsx

- **[MEDIUM] Search input has no accessible label (line 23).** Uses `placeholder` only. Placeholder text disappears on focus and is not a substitute for a label. Add `aria-label={searchPlaceholder}`.

### src/components/aim/AimDetailModal.jsx

- **[CRITICAL] Modal missing `role="dialog"` and `aria-modal="true"` (line 70-73).** The overlay `<div>` has no ARIA role. Screen readers don't recognise it as a modal dialog. The inner `<div ref={modalRef}>` should have `role="dialog"`, `aria-modal="true"`, and `aria-labelledby` pointing to the title.
- **[CRITICAL] Focus not trapped inside modal.** Keyboard users can Tab past the modal into the background page. Escape-to-close is implemented (good), but focus trap is missing.
- **[CRITICAL] Focus not set on open.** When the modal opens, focus stays on the trigger element behind the overlay. Focus should move to the modal (or its first focusable element).
- **[CRITICAL] Close button missing `aria-label` (line 85-89).** The button text is `✕` (multiplication sign). Screen readers announce "times button" or similar. Add `aria-label="Close"`.
- **[MEDIUM] CheckIcon (line 27-31) has no accessible alt.** The `✓`/`✗` span conveys pass/fail status but has no `aria-label` or `role="img"`. Screen readers announce the character which is ambiguous.

### src/components/aim/AimRegistryPanel.jsx

- **[CRITICAL] AimCard is a clickable `<div>` without keyboard support (line 113-116).** `<div onClick={onClick} className="... cursor-pointer">` -- no `role="button"`, no `tabIndex={0}`, no `onKeyDown`. Keyboard users cannot open AIM detail modals.
- **[MEDIUM] Weight progress bar (line 143-149) has no ARIA.** Visual-only percentage bar with no `role="progressbar"`, `aria-valuenow`, `aria-valuemin`, `aria-valuemax`, or accessible label.
- **[MEDIUM] Warmup progress bar (line 153-159) has no ARIA.** Same issue as weight bar.
- **[MEDIUM] Tier badge (line 183-186) is positionally overlapping.** `absolute top-1.5 right-1.5` -- doesn't affect a11y directly but could overlap with the status badge on narrow cards, making both unreadable.

### src/components/chart/ChartPanel.jsx

- **[LOW] Heading hierarchy jump.** Uses `<h2>` (line 71) and `<h3>` (line 49) inside what's a sub-panel. No `<h1>` in the immediate page context (DashboardPage has no heading). Not a blocking issue since it's a dashboard panel.

### src/components/layout/MarketTicker.jsx

- **[CRITICAL] All 10 ticker items are clickable divs without keyboard support (lines 18-238).** Each asset ticker uses `<div onClick={() => setSelectedAsset("...")}>` with no `role="button"`, `tabIndex={0}`, or `onKeyDown`. Keyboard users cannot select an asset to chart. This is the primary asset selection mechanism.
- **[CRITICAL] Green status dots have no accessible text (lines 27, 61, 124).** Several tickers show a green `<div className="... rounded-full bg-[#0faf7a]" />` dot to indicate "live" status. No label, no role, no sr-only text.
- **[MEDIUM] Selected ticker state not announced.** The selected asset gets a background highlight (`bg-[#0d1f1a]`) but no `aria-current` or `aria-selected` to convey state to screen readers.

### src/components/layout/TopBar.jsx

- **[CRITICAL] Status dots (API, WS, QDB, Redis) have no accessible text (lines 190-201).** Four coloured dots indicate service health. Each is a bare `<div>` with colour only. The adjacent text labels ("API", "WS", etc.) are not programmatically linked.
- **[CRITICAL] Account dropdown missing ARIA pattern (lines 102-142).** The dropdown uses a `<button>` toggle (good) but:
  - Missing `aria-expanded={dropdownOpen}` on the trigger button.
  - Missing `aria-haspopup="listbox"` on the trigger.
  - Dropdown menu has no `role="listbox"` or `role="menu"`.
  - Dropdown items have no `role="option"`.
  - No keyboard navigation (arrow keys) within the dropdown.
  - No `aria-activedescendant` for selected item.
- **[MEDIUM] Dropdown chevron `▼` (line 112-113) announced by screen readers.** Wrap in `<span aria-hidden="true">`.
- **[MEDIUM] Git Pull button icon states (lines 174-178) announced by screen readers.** The Unicode characters (`↻`, `⚙`, `✓`, `✗`, `↓`) should have `aria-hidden="true"` with an sr-only text alternative, or the button's `aria-label` should be dynamic.

### src/components/risk/RiskPanel.jsx

- **[CRITICAL] MDD drawdown bar has no ARIA (lines 108-119).** 10-segment visual bar showing MDD usage. No `role="progressbar"`, no `aria-valuenow`, no `aria-valuemin/max`. Screen readers get nothing. Colour-only communication (orange fill = used).
- **[CRITICAL] Daily DD drawdown bar has no ARIA (lines 142-150).** Same issue as MDD bar.
- **[MEDIUM] Payout target bar has no ARIA (line 190-192).** Visual-only gradient progress bar. Missing `role="progressbar"` and value attributes.
- **[MEDIUM] LIVE/OFFLINE badge (line 53-57) uses colour alone.** The green/red background conveys status but the text inside does say "LIVE"/"OFFLINE" which is accessible. Colour is supplementary. OK with text.

### src/components/signals/SignalCards.jsx

- **[LOW] Clear button has adequate text.** "Clear" is contextual but sufficient.

### src/components/signals/SignalExecutionBar.jsx

- **[MEDIUM] Pipeline stage pills have no ARIA selection state (lines 28-39).** The `data-active` attribute indicates the current stage visually, but no `aria-current="step"` or similar ARIA attribute. Screen readers cannot determine which stage is active.

### src/components/system/SystemLog.jsx

- **[CRITICAL] Tab buttons missing ARIA tablist pattern (lines 172-201).** "SYSTEM LOG" and "TELEGRAM" are tabs but:
  - No `role="tablist"` on the container.
  - No `role="tab"` on the buttons.
  - No `aria-selected` on the active tab.
  - No `role="tabpanel"` on the content area.
  - No arrow-key keyboard navigation between tabs.
- **[CRITICAL] Filter buttons (ALL/Errors/Signals/Orders) missing `aria-pressed` (lines 204-213).** These are toggle-filter buttons. The active state is communicated via background colour only. Add `aria-pressed={activeFilter === key}` to each.

### src/components/trading/ActivePosition.jsx

- **[LOW] Uses `<section>` with heading text inside.** Good semantic structure.

### src/components/trading/TradeLog.jsx

- **[MEDIUM] Trade log uses `<div>` grid instead of `<table>` (lines 28-66).** The header row (TIME, ASSET, D, P&L, DUR) and data rows are `<div>` elements styled as a table. Screen readers cannot navigate this as tabular data. Should use `<table>`, `<thead>`, `<tbody>`, `<th>`, `<td>`.

### src/components/replay/PlaybackControls.jsx

- **[CRITICAL] Play/Pause button missing `aria-label` (lines 51-62).** Button content is the Unicode character `⏸` or `▶`. Screen readers may announce "pause button" or "play button" depending on the character, but this is unreliable. Add `aria-label={isRunning ? "Pause" : "Play"}`.
- **[CRITICAL] Skip button missing `aria-label` (lines 65-76).** Same issue with `⏭`. Add `aria-label="Skip to next"`.
- **[MEDIUM] Speed selection buttons lack `aria-pressed` (lines 80-93).** Currently selected speed is shown visually but not communicated via ARIA. Add `aria-pressed={speed === s}`.
- **[MEDIUM] Progress bar missing `role="progressbar"` (lines 98-108).** The playback progress has no ARIA attributes. Add `role="progressbar"`, `aria-valuenow`, `aria-valuemin="0"`, `aria-valuemax="100"`.

### src/components/replay/PipelineStepper.jsx

- **[MEDIUM] Pipeline stage buttons lack `aria-expanded` (line 79-86).** Each stage button toggles an expanded detail view but doesn't communicate `aria-expanded={isExpanded}`.
- **[MEDIUM] Circle status indicators are visual-only (line 88-91).** The green/red/blue circles inside buttons have no text alternative. The check mark (✓) on complete stages is text, so partially accessible, but pending/running/error states have no text fallback.

### src/components/replay/ReplayConfigPanel.jsx

- **[MEDIUM] `Label` component not linked to inputs via `htmlFor` (line 9-11).** Renders `<label>` but without `htmlFor` attribute. All `NumberInput`, `date`, and `select` fields lack programmatic label association. This means clicking the label won't focus the input, and screen readers may not announce the label.
- **[MEDIUM] Toggle switches missing `aria-label` (lines 294-305, 309-323).** The CB L1 and AIM toggle buttons correctly use `role="switch"` and `aria-checked` (good!) but lack `aria-label`. Screen readers announce "switch, checked" with no name. Add `aria-label="Circuit Breaker Layer 1"` and `aria-label="AIM Scoring"`.
- **[MEDIUM] Preset select has no accessible label (line 352-361).** The `<select>` for loading presets has a default `<option>` as placeholder but no `<label>` or `aria-label`.
- **[MEDIUM] Preset name input has no accessible label (line 365-371).** Uses `placeholder` only. Add `aria-label="Preset name"`.

### src/components/replay/BatchPnlReport.jsx

- **[MEDIUM] View toggle buttons lack `aria-pressed` (lines 78-89).** The "Day-by-Day"/"Overall" toggles don't communicate selected state.
- **[MEDIUM] Progress bar missing ARIA (lines 33-42).** The batch progress indicator has no `role="progressbar"` or value attributes.
- **[MEDIUM] CSV download button performs download without accessible name context.** "CSV" is terse. Consider `aria-label="Download as CSV"`.

### src/components/replay/SimulatedPosition.jsx

- No significant a11y issues. Uses `<section>` correctly.

### src/components/replay/WhatIfComparison.jsx

- No interactive elements. OK.

### src/components/replay/ReplayHistory.jsx

- No interactive elements. OK.

### src/components/replay/BlockDetail.jsx

- No interactive elements beyond store subscriptions. OK.

### src/components/replay/AssetCard.jsx

- **[LOW] Loading shimmer has no `aria-busy` (lines 137-141).** Pulsing placeholder has no `aria-busy="true"` on the card container during loading state.

### src/pages/LoginPage.jsx

- **[MEDIUM] Error message not linked to input via `aria-describedby` (line 49-51).** The error div appears dynamically but screen readers may not announce it. Add `aria-describedby` on the input pointing to the error, and `role="alert"` on the error container.
- **[LOW] Good form structure.** Uses `<form>`, `<label>`, `<input type="password">`, and `<button type="submit">`.

### src/pages/DashboardPage.jsx

- **[LOW] No `<h1>` heading.** The page has no heading level 1 for screen reader navigation landmarks. The ResizablePanel layout doesn't include any landmark headings.

### src/pages/HistoryPage.jsx

- **[MEDIUM] Tab buttons missing ARIA tab pattern (lines 91-102).** Same pattern as SystemLog -- buttons toggle views but lack `role="tab"`, `role="tablist"`, `aria-selected`.

### src/pages/ReportsPage.jsx

- **[MEDIUM] Report type selector buttons lack `aria-current` or `aria-selected` (lines 72-97).** Selected report type has visual highlight but no ARIA attribute communicating selection state.

### src/pages/ReplayPage.jsx

- **[MEDIUM] Drag handle has no ARIA (line 88-91).** The resize handle `<div onMouseDown={onMouseDown}>` has no `role`, `aria-label`, or `aria-valuenow`. It also doesn't support keyboard resizing (arrow keys).
- **[LOW] ErrorBoundary fallback is accessible.** Renders visible error text.

### src/pages/SystemOverviewPage.jsx

- **[MEDIUM] Radar chart has no text alternative (lines 190-196).** The Recharts `<RadarChart>` renders SVG only. Screen readers get no information about the health scores. Add an `aria-label` on the container summarizing the data, or provide a visually hidden table.
- **[MEDIUM] Refresh button (line 333-336) has adequate text.** "Refresh" is clear.

### src/pages/ProcessesPage.jsx

- No significant a11y issues beyond inherited StatusDot/CollapsiblePanel problems.

### src/pages/ModelsPage.jsx

- No significant a11y issues. Display-only page.

### src/pages/ConfigPage.jsx

- No interactive elements. OK.

### src/pages/SettingsPage.jsx

- **[MEDIUM] Theme toggle button has no ARIA state.** The button text describes the action but doesn't communicate current state. Consider `aria-label={`Current theme: ${theme}. Switch to ${theme === "dark" ? "light" : "dark"}`}`.

---

## Colour Contrast Spot Checks

Evaluated against the dark theme backgrounds:

| Foreground | Background | Use | Ratio | Verdict |
|-----------|-----------|-----|-------|---------|
| `#64748b` | `#0a0e17` | Body text (secondary) | ~4.6:1 | **PASS** (AA normal text) |
| `#64748b` | `#111827` | Surface secondary text | ~3.5:1 | **FAIL** AA normal, PASS AA large |
| `#94a3b8` | `#0a0e17` | Body text (tertiary) | ~6.4:1 | **PASS** |
| `#94a3b8` | `#111827` | Surface tertiary text | ~4.9:1 | **PASS** |
| `#10b981` | `#0a0e17` | Green (success/active) | ~6.5:1 | **PASS** |
| `#ef4444` | `#0a0e17` | Red (error/loss) | ~4.4:1 | **PASS** AA normal |
| `#06b6d4` | `#0a0e17` | Cyan (info/accent) | ~6.3:1 | **PASS** |
| `#f59e0b` | `#0a0e17` | Amber (warning) | ~6.8:1 | **PASS** |
| `#e2e8f0` | `#0a0e17` | Primary text | ~13.5:1 | **PASS** |
| `rgba(226,232,240,0.5)` | `#111827` | Table headers | ~5.4:1 | **PASS** |
| `rgba(226,232,240,0.25)` | `#0a0e17` | Footer text (faintest) | ~2.4:1 | **FAIL** AA |
| `rgba(226,232,240,0.35)` | `#111827` | Risk panel sub-labels | ~2.5:1 | **FAIL** AA |
| `rgba(15,175,122,0.7)` | `#080e0d` | Risk panel section headers | ~3.2:1 | **FAIL** AA normal, PASS large |
| `#475569` | `#111827` | Deferred AIM name text | ~2.3:1 | **FAIL** AA |
| `rgba(226,232,240,0.4)` | `#080e0d` | TopBar timestamp | ~3.3:1 | **FAIL** AA normal |

**Summary:** 5 colour pairs fail WCAG AA normal-text contrast (4.5:1). Most are low-opacity text on dark surfaces. The `rgba(226,232,240,0.25)` (footer text) and `#475569` (deferred AIM) pairs are the worst offenders at ~2.3-2.5:1.

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 19 |
| MEDIUM | 24 |
| LOW | 7 |
| **Total** | **50** |

### Top 5 Priorities (highest impact fixes)

1. **S-01: Add global `focus-visible` ring** -- Single CSS rule fixes keyboard navigation visibility across entire app.
2. **S-02: Convert clickable divs to `<button>`** -- MarketTicker (10 items) + AimCard (16 items) = 26 inaccessible interactive elements.
3. **S-03: Add accessible text to StatusDot** -- Accept `label` prop, render sr-only text. Fixes ~20 instances.
4. **AimDetailModal: Add dialog ARIA + focus trap** -- Modal is completely invisible to screen readers.
5. **CollapsiblePanel: Add `aria-expanded`** -- Used in 5+ locations, single fix cascades.

### Patterns That Recur

| Pattern | Count | Fix |
|---------|-------|-----|
| Clickable `<div>` without keyboard | 26 | Replace with `<button>` or add `role`, `tabIndex`, `onKeyDown` |
| Progress bar without `role="progressbar"` | 6 | Add `role`, `aria-valuenow/min/max` |
| Toggle button without `aria-pressed` | 12 | Add `aria-pressed={isActive}` |
| Tab pattern without ARIA tablist | 3 | Add `role="tablist/tab/tabpanel"`, `aria-selected`, keyboard nav |
| Colour-only status indicator | ~20 | Add sr-only text or `aria-label` |
| Label not linked to input | ~15 | Add `htmlFor`/`id` pairs or `aria-label` |
