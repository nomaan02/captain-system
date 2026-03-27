# Captain GUI — Redesign Issues

**Audited:** 2026-03-23
**Stack:** React 18 + Vite + Tailwind + Zustand + Recharts + Lucide icons
**Files:** 66 source files (20 main panels, 19 admin panels, 5 pages, 6 components, 4 stores, etc.)
**Status:** Functional but needs UX overhaul before production use

---

## Architecture (working correctly)

- Sidebar navigation with 5 routes (Dashboard, System Overview, History, Reports, Settings)
- WebSocket connection with REST polling fallback (10s)
- Dark/light theme toggle
- Role-based routing (ADMIN-only System Overview)
- Zustand stores for dashboard, notifications, system overview, theme
- API client with typed endpoints

---

## Layout Issues (user-reported + audit-confirmed)

### 1. Ever-Expanding Panels (no scroll containment)

Most panels use `space-y-`* stacking with no `max-h` or `overflow-y-auto`. When data grows, panels expand indefinitely, pushing everything below off-screen.

**Affected panels:**

- `NotificationCenter.tsx` — notification list grows unbounded
- `PositionMonitor.tsx` — position cards stack without limit
- `TsmStatusBar.tsx` — account list (space-y-4) expands per account
- `StrategyComparison.tsx` — params grid expands with strategies
- `AimPanel.tsx` — AIM cards in 2-col grid expand if many AIMs active
- `LiveMarketPanel.tsx` — quote rows expand per asset

**Fix pattern:** Add `max-h-[value] overflow-y-auto` to scrollable list containers. Only `SignalCards.tsx` currently does this correctly (`max-h-80 overflow-y-auto`).

### 2. Panels Too Large for Single View

The DashboardPage stacks ~14 panels vertically. On a standard 1080p monitor, you can only see the top 2-3 panels without scrolling. Critical info (positions, drawdown) may be off-screen.

**Fix:** Collapsible panel sections with expand/collapse toggles. Group related panels (e.g., "Signals & Trades", "Account Status", "AIM & Regime", "Notifications").

### 3. SystemOverviewPage — 8 Rows of Admin Panels

19 admin panels arranged in 8 rows. Extremely long page — no way to see everything. Each row uses `grid-cols-3` which compresses panel content on smaller screens.

**Fix:** Collapsible sections or tabbed layout for admin groups.

### 4. No Responsive Breakpoints Below XL

Grid layouts use `xl:grid-cols-2` and `xl:grid-cols-3` but fall back to single column below `xl` (1280px). On common 1440px or 1920px monitors this works, but laptop screens (1366px) get awkward layouts.

---

## Missing UX Features

### 5. No Descriptive Labels / Section Headers

Panels jump straight into data with no context. New users won't understand what each panel shows or why it matters.

**Fix:** Add small `text-xs text-gray-400` descriptions below each panel title explaining what the panel shows and when to pay attention to it.

### 6. No Collapsible Panels

Every panel is always fully expanded. Users can't hide panels they don't need right now.

**Fix:** Add a chevron toggle to each panel card header. Persist collapsed state in localStorage.

### 7. No Panel Priority / Alert Highlighting

All panels have equal visual weight. A circuit breaker halt and a warmup gauge look the same.

**Fix:** Border-left color coding (red = action required, yellow = warning, green = normal, gray = info-only). The `CircuitBreakerBanner` and `DecayAlertBanner` already do this well — extend the pattern.

### 8. Notification Center Has No Filtering

All notifications in one list. No way to filter by priority, asset, or read/unread.

---

## Minor Issues

- **No loading skeletons** — pages show `<LoadingSpinner />` (full-page spinner) while data loads instead of skeleton placeholders per panel
- **TpSlProximityBar** uses hardcoded `h-3` which is too small to read on some displays
- **No keyboard shortcuts** for TAKEN/SKIPPED actions
- **WebSocket reconnect** banner is red and alarming — could be softer for brief disconnects

---

## Recommended Redesign Priority

1. **Collapsible panels** — biggest bang for usability
2. **Overflow scrolling** on all list panels — prevents layout breakage
3. **Section headers with descriptions** — onboarding aid
4. **Priority color coding** — visual hierarchy
5. **Notification filtering** — usability at scale
6. **Admin page tabs** — SystemOverview is too long to scroll

