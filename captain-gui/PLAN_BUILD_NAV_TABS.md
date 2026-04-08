# Implementation Plan: Build All 5 Nav Tab Pages for Captain GUI

**Created:** 2026-03-31
**Spec Source:** `OLD_GUI_TAB_SPECIFICATIONS.md` (in captain-gui root)
**Status:** Ready for execution

---

## Phase 0: Documentation Discovery (COMPLETE)

### Findings Summary

#### Project Stack
- **Framework:** React 18.2.0 with Vite 6.3.2
- **Language:** JavaScript (`.jsx` files, NOT TypeScript)
- **CSS:** Tailwind CSS 4.1.3 via PostCSS
- **State:** Zustand 5.0.12
- **Routing:** react-router-dom 7.5.0 (BrowserRouter)
- **Layout:** react-resizable-panels 4.8.0
- **Charting:** lightweight-charts 5.1.0 (NOT recharts)

#### Missing Dependencies (MUST install)
- `recharts` -- needed for System Overview radar chart (4.1) and bar chart (4.12)
- `@tanstack/react-table` -- needed for searchable data tables in History, System Overview, Processes

#### Existing Infrastructure (DO NOT recreate)

| Asset | Path | Status |
|-------|------|--------|
| API client | `src/api/client.js` | Complete -- has all endpoints needed (health, status, dashboard, systemOverview, processesStatus, reportTypes, generateReport) |
| Formatters | `src/utils/formatting.js` | Partial -- has formatCurrency, formatPercent, formatPrice, formatTime, formatTimeSince |
| Dashboard store | `src/stores/dashboardStore.js` | Complete -- has aimStates, decayAlerts, pendingSignals, etc. |
| Chart store | `src/stores/chartStore.js` | Complete |
| Notification store | `src/stores/notificationStore.js` | Complete |
| WebSocket hook | `src/ws/useWebSocket.js` | Complete -- handles system_overview messages already |
| Asset names | `src/constants/assetNames.js` | Complete |
| Point values | `src/constants/pointValues.js` | Complete |

#### What Does NOT Exist (MUST create)
- No auth context / user role system (user_id hardcoded as "primary_user")
- No shared reusable UI components (all inline Tailwind in each component)
- No stores for: processes, reports, system overview, history
- No formatTimestamp or formatTimeAgo functions
- Routes only defined for `/`, `/models`, `/config` -- 5 routes missing

#### Design System Reference (extracted from Dashboard)

**Page Shell Pattern** (from ModelsPage.jsx / ConfigPage.jsx):
```jsx
<div className="h-screen bg-surface p-4 overflow-y-auto">
  <h1 className="text-lg font-mono text-white tracking-[2px] uppercase mb-6">
    Page Title
  </h1>
  {/* content */}
</div>
```

**Card/Panel Pattern** (from ModelsPage.jsx):
```jsx
<div className="bg-surface-card border border-border-subtle p-3 font-mono text-xs">
  {/* card content */}
</div>
```

**Section Header Pattern** (from ModelsPage.jsx):
```jsx
<h2 className="text-sm font-mono text-captain-green tracking-[1.5px] uppercase mb-3">
  Section Title
</h2>
```

**Status Badge Pattern** (from ModelsPage.jsx, SignalCards.jsx):
```jsx
<span className={`px-2 py-0.5 text-[10px] border border-solid ${
  isActive
    ? "bg-[rgba(16,185,129,0.15)] border-[rgba(16,185,129,0.3)] text-[#10b981]"
    : "bg-[rgba(100,116,139,0.1)] border-[#374151] text-[#64748b]"
}`}>
  {label}
</span>
```

**Empty State Pattern** (from ModelsPage.jsx):
```jsx
<div className="text-[#64748b] text-xs font-mono py-4">
  No data available
</div>
```

**Placeholder Panel Pattern** (from ConfigPage.jsx):
```jsx
<div className="bg-surface-card border border-border-subtle p-6 font-mono text-xs text-[#64748b]">
  <p>Placeholder message text.</p>
</div>
```

**Color Palette (Tailwind config tokens):**
- Backgrounds: `bg-surface` (#0a0f0d), `bg-surface-dark` (#080e0d), `bg-surface-card` (#08100f), `bg-surface-elevated` (#0a1614)
- Borders: `border-border` (#1e293b), `border-border-subtle` (#1a3038), `border-border-accent` (#2e4e5a)
- Brand: `text-captain-green` (#0faf7a), `text-captain-red` (#ef4444), `text-captain-cyan` (#06b6d4), `text-captain-amber` (#f59e0b), `text-captain-blue` (#3b82f6), `text-captain-orange` (#ff8800), `text-captain-pink` (#ff0040)
- Status green: #10b981 (with rgba backgrounds)
- Status red: #ef4444 (with rgba backgrounds)
- Status amber: #f59e0b (with rgba backgrounds)
- Muted text: #64748b, #94a3b8
- Primary text: #fff, #e2e8f0
- Fonts: `font-mono` (JetBrains Mono), `font-sans` (Inter)

**Status Dot Pattern** (from TopBar.jsx):
```jsx
<div className={`w-[5.5px] h-[5.5px] rounded-full ${connected ? "bg-[#00ad74]" : "bg-[#ef4444]"}`} />
```

**Nav Route Paths** (from TopBar.jsx lines 54-59):
- `/` -- Dashboard (implemented)
- `/system` -- System Overview (NOT implemented)
- `/processes` -- Processes (NOT implemented)
- `/history` -- History (NOT implemented)
- `/reports` -- Reports (NOT implemented)
- `/settings` -- Settings (NOT implemented)

#### Anti-Pattern Guards
- DO NOT use TypeScript -- project is pure JavaScript (.jsx)
- DO NOT use `className="..."` Tailwind tokens that don't exist in the config (e.g., don't invent `bg-panel` or `text-muted`)
- DO NOT create a separate auth provider/context -- just hardcode `"primary_user"` and `"ADMIN"` role like the existing codebase does
- DO NOT modify existing stores (dashboardStore, chartStore, notificationStore)
- DO NOT modify TopBar.jsx, DashboardPage.jsx, or any existing component
- DO NOT use CSS modules or styled-components -- everything is Tailwind utility classes

---

## Phase 1: Shared Infrastructure

**Goal:** Install missing deps, add missing formatters, create shared UI components and new Zustand stores. No page components yet.

### Task 1.1: Install Dependencies

```bash
cd /home/nomaan/captain-system/captain-gui
npm install recharts @tanstack/react-table
```

**Verification:** Run `npm ls recharts @tanstack/react-table` -- both should appear in tree.

### Task 1.2: Add Missing Formatters

**File:** `src/utils/formatting.js` (EDIT, do not replace)

Add two new functions to the existing file:

```javascript
export function formatTimestamp(isoString) {
  if (!isoString) return "—";
  const d = new Date(isoString);
  const month = d.toLocaleString("en-US", { timeZone: "America/New_York", month: "short" });
  const day = d.toLocaleString("en-US", { timeZone: "America/New_York", day: "2-digit" });
  const time = d.toLocaleTimeString("en-US", {
    timeZone: "America/New_York",
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  return `${month} ${day}, ${time}`;
}

export function formatTimeAgo(isoString) {
  if (!isoString) return "—";
  const ms = Date.now() - new Date(isoString).getTime();
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}
```

**Verification:** Grep for `formatTimestamp` and `formatTimeAgo` in `src/utils/formatting.js`.

### Task 1.3: Create Shared UI Components

Create these files in `src/components/shared/`:

#### `src/components/shared/StatusDot.jsx`
Colored dot with optional pulse animation.
- Props: `status` ("ok" | "error" | "halted" | "unknown"), `size` (default "5.5px"), `pulse` (boolean, default true for "ok")
- Color mapping: ok=#00ad74, error=#ef4444, halted=#f59e0b, unknown=#64748b
- Pulse: CSS animation `animate-pulse` when status is "ok" and pulse=true
- Pattern reference: TopBar.jsx status dots (lines showing `w-[5.5px] h-[5.5px] rounded-full`)

#### `src/components/shared/StatusBadge.jsx`
Colored text badge for status labels.
- Props: `status` (string), `colorMap` (optional object mapping status strings to {bg, border, text} classes)
- Default colorMap:
  - "ok"/"OK"/"ACTIVE"/"HEALTHY" -> green (bg-[rgba(16,185,129,0.15)] border-[rgba(16,185,129,0.3)] text-[#10b981])
  - "error"/"ERROR"/"CRITICAL"/"HALTED" -> red (bg-[rgba(239,68,68,0.15)] border-[rgba(239,68,68,0.3)] text-[#ef4444])
  - "halted"/"HALTED"/"DEGRADED"/"WARM_UP" -> amber (bg-[rgba(245,158,11,0.1)] border-[rgba(245,158,11,0.3)] text-[#f59e0b])
  - default -> gray (bg-[rgba(100,116,139,0.1)] border-[#374151] text-[#64748b])
- Styling: `px-2 py-0.5 text-[10px] font-mono border border-solid uppercase`
- Pattern reference: ModelsPage.jsx AIM status badge

#### `src/components/shared/DataTable.jsx`
Wrapper around @tanstack/react-table with search and the project's styling.
- Props: `columns` (TanStack column defs), `data` (array), `searchPlaceholder` (string), `emptyMessage` (string, default "No data")
- Features:
  - Search input at top (filters globally across all columns)
  - Column headers: `text-[10px] text-[#94a3b8] uppercase tracking-wider font-mono`
  - Data rows: `text-xs text-white font-mono border-b border-border-subtle`
  - Row hover: `hover:bg-[rgba(100,116,139,0.05)]`
  - Empty state: centered muted text using the empty state pattern
  - Search input styling: `bg-surface-dark border border-border-subtle text-white font-mono text-xs px-3 py-1.5 w-full mb-3 placeholder-[#64748b] focus:outline-none focus:border-border-accent`
- Table container: `bg-surface-card border border-border-subtle overflow-hidden`
- Pattern reference: TradeLog.jsx table structure (but generalized with TanStack)

#### `src/components/shared/CollapsiblePanel.jsx`
Section with toggle header, persists open/closed state to localStorage.
- Props: `title` (string), `storageKey` (string), `defaultOpen` (boolean, default true), `headerRight` (ReactNode, optional), `accentColor` (string, optional -- "green"/"blue"/"gray"), `children`
- Header styling: `bg-surface-card border border-border-subtle px-3 py-2 cursor-pointer flex items-center justify-between`
- Title: `text-sm font-mono uppercase tracking-[1.5px]` with accent color (green=text-captain-green, blue=text-captain-blue, gray=text-[#94a3b8])
- Chevron icon: simple ">" / "v" text rotation or unicode arrow
- Content area: conditionally rendered, `px-3 py-2` within the border
- localStorage persistence: read on mount, write on toggle

#### `src/components/shared/StatBox.jsx`
Large number + small label metric card.
- Props: `label` (string), `value` (string/number), `color` (optional, for value text color)
- Pattern reference: RiskPanel capital cards
- Styling:
  - Container: `bg-surface-card border border-border-accent flex flex-col py-2 px-3 min-h-[55px]`
  - Label: `text-[10px] text-[rgba(226,232,240,0.5)] font-mono uppercase tracking-wider`
  - Value: `text-lg text-white font-mono leading-tight` (override color with prop)

### Task 1.4: Create New Zustand Stores

Create these in `src/stores/`:

#### `src/stores/processesStore.js`
```javascript
import { create } from "zustand";
import api from "../api/client";

const useProcessesStore = create((set, get) => ({
  processes: {},        // { ONLINE: { status, timestamp }, OFFLINE: {...}, COMMAND: {...} }
  blocks: [],           // Array from API
  lockedStrategies: [], // Array from API
  apiConnections: { connected: 0, total: 0 },
  loading: true,
  error: null,
  pollInterval: null,

  fetch: async () => {
    try {
      const data = await api.processesStatus();
      set({
        processes: data.processes || {},
        blocks: data.blocks || [],
        lockedStrategies: data.locked_strategies || [],
        apiConnections: data.api_connections || { connected: 0, total: 0 },
        loading: false,
        error: null,
      });
    } catch (err) {
      set({ error: err.message, loading: false });
    }
  },

  startPolling: () => {
    const { fetch } = get();
    fetch();
    const id = setInterval(fetch, 15000);
    set({ pollInterval: id });
  },

  stopPolling: () => {
    const { pollInterval } = get();
    if (pollInterval) clearInterval(pollInterval);
    set({ pollInterval: null });
  },
}));

export default useProcessesStore;
```

#### `src/stores/reportsStore.js`
```javascript
import { create } from "zustand";
import api from "../api/client";

const useReportsStore = create((set) => ({
  reportTypes: [],
  selectedType: null,
  generating: false,
  result: null,
  error: null,
  loading: true,

  fetchTypes: async () => {
    try {
      const data = await api.reportTypes();
      const types = Array.isArray(data) ? data : data.report_types || [];
      set({ reportTypes: types, selectedType: types[0] || null, loading: false });
    } catch (err) {
      set({ error: err.message, loading: false });
    }
  },

  selectType: (type) => set({ selectedType: type, result: null, error: null }),

  generate: async (reportType, userId) => {
    set({ generating: true, result: null, error: null });
    try {
      const data = await api.generateReport({ report_type: reportType, user_id: userId, params: {} });
      set({ result: data, generating: false });
    } catch (err) {
      set({ error: err.message, generating: false });
    }
  },
}));

export default useReportsStore;
```

#### `src/stores/systemOverviewStore.js`
```javascript
import { create } from "zustand";
import api from "../api/client";

const useSystemOverviewStore = create((set) => ({
  overview: null,
  loading: true,
  error: null,

  fetch: async () => {
    try {
      const data = await api.systemOverview();
      set({ overview: data, loading: false, error: null });
    } catch (err) {
      set({ error: err.message, loading: false });
    }
  },

  setOverview: (data) => set({ overview: data, loading: false }),
}));

export default useSystemOverviewStore;
```

**Note:** The WebSocket hook in `src/ws/useWebSocket.js` already handles `"system_overview"` message type. After creating this store, the executing agent should check if the WS hook calls `setOverview` -- if not, add a single line to the WS handler to wire it up.

### Task 1.5: Extend WebSocket Hook (if needed)

**File:** `src/ws/useWebSocket.js` (READ first, then EDIT if needed)

Check whether the `"system_overview"` case in the message handler updates the new `systemOverviewStore`. If it doesn't exist or writes to an old location, add:

```javascript
import useSystemOverviewStore from "../stores/systemOverviewStore";
// Inside the message handler switch:
case "system_overview":
  useSystemOverviewStore.getState().setOverview(parsed.data || parsed);
  break;
```

**Verification Checklist for Phase 1:**
1. `npm ls recharts @tanstack/react-table` both appear
2. `grep -r "formatTimestamp\|formatTimeAgo" src/utils/` returns both functions
3. Files exist: `src/components/shared/StatusDot.jsx`, `StatusBadge.jsx`, `DataTable.jsx`, `CollapsiblePanel.jsx`, `StatBox.jsx`
4. Files exist: `src/stores/processesStore.js`, `reportsStore.js`, `systemOverviewStore.js`
5. `npm run build` (or `npx vite build`) completes without errors

---

## Phase 2: Settings Page

**Goal:** Build the simplest tab -- Settings at `/settings`. No API calls, pure local state.

**Spec Reference:** `OLD_GUI_TAB_SPECIFICATIONS.md` Section 1 (Settings Tab)

### Task 2.1: Create SettingsPage Component

**File:** `src/pages/SettingsPage.jsx`

**Structure:**
```
SettingsPage
  Page shell (h-screen bg-surface p-4 overflow-y-auto)
  Page title: "Settings"
  
  Section 1: User Information
    Card panel with:
    - "User ID" label + "primary_user" in monospace
    - "Role" label + "ADMIN" in plain text
  
  Section 2: Appearance
    Card panel with:
    - "Theme" label + current theme name
    - Toggle button: "Switch to Light" / "Switch to Dark"
```

**Data Sources:**
- User ID: hardcode `"primary_user"` (matching existing pattern from DashboardPage.jsx line 186)
- Role: hardcode `"ADMIN"` (no auth context exists)
- Theme: read from localStorage key `"captain-theme"`, default `"dark"`
- On toggle: write to localStorage and update body class (note: the app is dark-only currently, so the toggle only needs to persist state and show visual feedback. Actual light theme CSS does not exist.)

**Styling (copy from existing pages):**
- Page shell: `className="h-screen bg-surface p-4 overflow-y-auto"`
- Page title: `className="text-lg font-mono text-white tracking-[2px] uppercase mb-6"`
- Section header: `className="text-sm font-mono text-captain-green tracking-[1.5px] uppercase mb-3"`
- Card: `className="bg-surface-card border border-border-subtle p-3 font-mono text-xs"`
- User ID value: `className="text-white font-mono"` (monospace is default)
- Role value: `className="text-white"`
- Toggle button: style like the chart overlay toggle buttons from ChartOverlayToggles.jsx: `px-2 py-1 text-[10px] font-mono border border-solid cursor-pointer` with active/inactive colors matching the captain badge pattern
- Em-dash or separator between fields

**Anti-patterns:**
- Do NOT create a theme context provider
- Do NOT install a UI library for the toggle
- Do NOT create light theme CSS (just persist the preference)

### Task 2.2: Wire Route

**File:** `src/App.jsx` (EDIT)

Add import and route:
```jsx
import SettingsPage from "./pages/SettingsPage";
// Inside <Routes>:
<Route path="/settings" element={<SettingsPage />} />
```

Also add title case in the switch statement:
```javascript
case "/settings":
  title = "Captain Settings";
  break;
```

**Verification Checklist for Phase 2:**
1. Navigate to `/settings` -- page renders without errors
2. User ID shows "primary_user" in monospace
3. Role shows "ADMIN"
4. Theme toggle button is visible and clickable
5. localStorage key `"captain-theme"` updates on toggle
6. Page styling matches ModelsPage/ConfigPage shell pattern

---

## Phase 3: History Page

**Goal:** Build the History tab at `/history` with 5 sub-tabs of searchable data tables.

**Spec Reference:** `OLD_GUI_TAB_SPECIFICATIONS.md` Section 5 (History Tab)

### Task 3.1: Create HistoryPage Component

**File:** `src/pages/HistoryPage.jsx`

**Structure:**
```
HistoryPage
  Page shell (h-screen bg-surface p-4 overflow-y-auto)
  Page title: "History"
  
  Tab Bar: [Signals] [Trade Outcomes] [Decay Events] [AIM Changes] [System Events]
    Active tab: green highlight (matching TopBar nav active style)
    Inactive tab: muted
  
  Content: One <DataTable /> per tab, conditionally rendered
```

**Data Source:** Fetch once on mount from `api.dashboard("primary_user")`. This returns the same snapshot as the Dashboard. Extract:
- `pending_signals` or `pendingSignals` -> Signals tab
- (empty array) -> Trade Outcomes tab (backend not wired)
- `decay_alerts` or `decayAlerts` -> Decay Events tab
- `aim_states` or `aimStates` -> AIM Changes tab
- (empty array) -> System Events tab (backend not wired)

**Alternative approach:** Instead of a separate fetch, read from `useDashboardStore` directly (it already has `pendingSignals`, `decayAlerts`, `aimStates`). This avoids a duplicate API call. The Dashboard page's WebSocket keeps these fresh.

**Tab Bar Styling** (derive from SystemLog filter tabs in SystemLog.jsx):
```jsx
<button className={`px-3 py-1.5 text-[10px] font-mono uppercase tracking-wider border border-solid transition-colors ${
  isActive
    ? "bg-[rgba(16,185,129,0.15)] border-[rgba(16,185,129,0.3)] text-[#10b981]"
    : "bg-transparent border-[#2e4e5a] text-[#64748b] hover:bg-[rgba(100,116,139,0.05)]"
}`}>
  {tabName}
</button>
```

### Task 3.2: Define Column Configurations

Each sub-tab uses the `<DataTable />` shared component with these column definitions:

**Signals Tab:**
| Column | Accessor | Cell Renderer |
|--------|----------|---------------|
| Time | `timestamp` | `formatTimestamp(value)` |
| Asset | `asset` | plain text |
| Dir | `direction` | plain text |
| Confidence | `confidence_tier` | plain text |
| Quality | `quality_score` | `value.toFixed(3)` |
| ID | `signal_id` | `<span className="text-[10px] font-mono text-[#64748b]">{value}</span>` |

**Trade Outcomes Tab:**
| Column | Accessor | Cell Renderer |
|--------|----------|---------------|
| Time | `timestamp` | `formatTimestamp(value)` |
| Asset | `asset` | plain text |
| Dir | `direction` | plain text |
| Outcome | `outcome` | StatusBadge: TP_HIT=green, SL_HIT=red |
| P&L | `pnl` | `formatCurrency(value)` + green/red color |
| Account | `account_id` | plain text |

Empty state: "No trade outcomes recorded"

**Decay Events Tab:**
| Column | Accessor | Cell Renderer |
|--------|----------|---------------|
| Time | `timestamp` | `formatTimestamp(value)` |
| Asset | `asset` | plain text |
| Level | `level` | plain text |
| CP Prob | `cp_prob` | `formatPercent(value * 100, 1)` |
| CUSUM | `cusum_stat` | `value.toFixed(4)` |

**AIM Changes Tab:**
| Column | Accessor | Cell Renderer |
|--------|----------|---------------|
| AIM ID | `aim_id` | plain text |
| Name | `aim_name` | plain text |
| Status | `status` | plain text |
| Weight | `meta_weight` | `value.toFixed(4)` |
| Modifier | `modifier` | `value?.toFixed(4) ?? "—"` |

**System Events Tab:**
| Column | Accessor | Cell Renderer |
|--------|----------|---------------|
| Time | `timestamp` | `formatTimestamp(value)` |
| Type | `event_type` | plain text |
| Asset | `asset` | plain text |
| User | `user_id` | plain text |
| Event ID | `event_id` | monospace small text |

Empty state: "No system events recorded"

### Task 3.3: Wire Route

**File:** `src/App.jsx` (EDIT)

Add import and route:
```jsx
import HistoryPage from "./pages/HistoryPage";
<Route path="/history" element={<HistoryPage />} />
```

**Verification Checklist for Phase 3:**
1. Navigate to `/history` -- page renders without errors
2. 5 tab buttons visible, first tab (Signals) active by default
3. Clicking each tab switches the displayed table
4. Tables show correct columns for each tab
5. Search input filters table rows
6. Trade Outcomes and System Events tabs show empty state message
7. If dashboard store has data (from WebSocket), Signals/Decay/AIM tabs show real data

---

## Phase 4: Reports Page

**Goal:** Build the Reports tab at `/reports` with report type selector and generation.

**Spec Reference:** `OLD_GUI_TAB_SPECIFICATIONS.md` Section 2 (Reports Tab)

### Task 4.1: Create ReportsPage Component

**File:** `src/pages/ReportsPage.jsx`

**Structure:**
```
ReportsPage
  Page shell
  Page title: "Reports"
  
  Two-panel grid: grid grid-cols-3 gap-4
  
  Left panel (col-span-1): Report Type Selector
    Card panel with scrollable list of report types
    Each item: report ID badge + name + trigger badge + format badge
    Selected item: green highlight
    Loading state: "Loading report types..."
    Error state: "Failed to load report types"
  
  Right panel (col-span-2): Generation Area
    Card panel with:
    - Selected report name + ID
    - "Generate" button (disabled when generating)
    - Loading: "Generating..." with disabled button
    - Result: metadata (report_id, generated_at) + format badge
    - Download buttons (CSV, JSON) based on format
    - Preview area (<pre> block with max-height scroll)
```

**Data Sources:**
- `useReportsStore.fetchTypes()` on mount -> populates left panel
- `useReportsStore.generate(reportType, "primary_user")` on button click -> populates right panel

**Report Type List (from spec, 11 types):**
The left panel fetches from `GET /api/reports/types`. If the backend returns data, use it. If fetch fails, show error state -- do NOT hardcode the list.

**Trigger Badge Colors:**
- `"pre_session"`, `"session_open"`, `"scheduled"` -> blue: `bg-[rgba(59,130,246,0.15)] border-[rgba(59,130,246,0.3)] text-[#3b82f6]`
- `"per_trade"`, `"per_session"`, `"daily"` -> amber: `bg-[rgba(245,158,11,0.1)] border-[rgba(245,158,11,0.3)] text-[#f59e0b]`
- `"on_demand"`, `"on_p1p2_run"`, `"regime_change"` -> gray: `bg-[rgba(100,116,139,0.1)] border-[#374151] text-[#64748b]`
- `"monthly"`, `"first_of_month"`, `"end_of_week"`, `"annually"` -> cyan: `bg-[rgba(6,182,212,0.15)] border-[rgba(6,182,212,0.3)] text-[#06b6d4]`

**Format Badge Colors:**
- `"csv"` -> gray badge
- `"in_app"` -> green badge

**Download Logic:**
```javascript
function downloadFile(content, filename, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// CSV download:
downloadFile(result.data, `${result.report_type}_${date}.csv`, "text/csv");

// JSON download:
downloadFile(JSON.stringify(result.data, null, 2), `${result.report_type}_${date}.json`, "application/json");
```

**Preview Logic:**
- CSV format: show first 20 rows of `result.data` string in `<pre>` with `max-h-[400px] overflow-y-auto bg-surface-dark border border-border-subtle p-3 text-xs font-mono text-[#e2e8f0]`
- in_app format: show `JSON.stringify(result.data, null, 2)` in same `<pre>` style

### Task 4.2: Wire Route

**File:** `src/App.jsx` (EDIT)

```jsx
import ReportsPage from "./pages/ReportsPage";
<Route path="/reports" element={<ReportsPage />} />
```

**Verification Checklist for Phase 4:**
1. Navigate to `/reports` -- page renders without errors
2. Left panel shows loading state initially, then either report types or error
3. Clicking a report type selects it (green highlight) and clears any previous result
4. Generate button visible in right panel, disabled when generating
5. After generation: metadata displayed, download buttons functional
6. CSV preview shows `<pre>` block with scrollable content
7. In-app preview shows JSON in `<pre>` block

---

## Phase 5: Processes Page

**Goal:** Build the data-dense Processes tab at `/processes`.

**Spec Reference:** `OLD_GUI_TAB_SPECIFICATIONS.md` Section 3 (Processes Tab)

### Task 5.1: Create Block Registry Constants

**File:** `src/constants/blockRegistry.js`

Hardcode the full block registry from the spec (39 blocks total). This is reference metadata that does NOT come from the API. Structure:

```javascript
export const BLOCK_REGISTRY = {
  ONLINE: [
    { id: "online-orchestrator", name: "Online Orchestrator", trigger: "always_on", triggerLabel: "24/7 session loop", description: "Session loop: evaluates at NY/LON/APAC opens, sequences B1-B9 per session", sourceFile: "captain_online/main.py" },
    { id: "online-b1", name: "B1 Data Ingestion", trigger: "session_open", triggerLabel: "Session open", description: "Loads active assets, validates data quality, resolves contracts, computes features", sourceFile: "captain_online/blocks/b1_data_ingestion.py" },
    // ... all 13 ONLINE blocks from spec section 3.4
  ],
  OFFLINE: [
    // ... all 15 OFFLINE blocks from spec section 3.4
  ],
  COMMAND: [
    // ... all 11 COMMAND blocks from spec section 3.4
  ],
};
```

Copy ALL block entries verbatim from the spec sections 3.4 (Online: 13, Offline: 15, Command: 11).

### Task 5.2: Create ProcessesPage Component

**File:** `src/pages/ProcessesPage.jsx`

**Structure:**
```
ProcessesPage
  Page shell (h-screen bg-surface p-4 overflow-y-auto)
  Page title: "Processes"
  
  Section 1: Process Health Cards (3-column grid)
    3 cards: CAPTAIN ONLINE, CAPTAIN OFFLINE, CAPTAIN COMMAND
    Each card: StatusDot + name + StatusBadge + last heartbeat
    Grid: grid grid-cols-3 gap-4
  
  Section 2: Locked Strategies Table
    DataTable with columns: Asset, Status, m, k, OO, Sessions
    EmptyState: "No locked strategies loaded"
  
  Section 3: Block Groups (3 CollapsiblePanels)
    CAPTAIN ONLINE (green accent, 13 blocks)
    CAPTAIN OFFLINE (blue accent, 15 blocks)
    CAPTAIN COMMAND (gray accent, 11 blocks)
    Each block row: StatusDot + name (bold) + trigger badge + description + source file
    Header right: "{N} blocks" count + process StatusDot
    localStorage keys: "processes-ONLINE", "processes-OFFLINE", "processes-COMMAND"
  
  Section 4: API Connections
    StatusDot + "X/Y connected" text
```

**Data Source:**
- `useProcessesStore.startPolling()` on mount (fetches + starts 15s interval)
- `useProcessesStore.stopPolling()` on unmount (cleanup)
- Process health: `store.processes.ONLINE`, etc.
- Locked strategies: `store.lockedStrategies`
- API connections: `store.apiConnections`
- Block live status: `store.blocks` (merge with hardcoded registry for display)

**Process Health Card Styling:**
```jsx
<div className="bg-surface-card border border-border-subtle p-3 font-mono">
  <div className="flex items-center gap-2 mb-2">
    <StatusDot status={process.status} />
    <span className="text-sm text-white uppercase tracking-wider">{processName}</span>
  </div>
  <div className="flex items-center justify-between">
    <StatusBadge status={process.status} />
    <span className="text-[10px] text-[#64748b]">{formatTime(process.timestamp)}</span>
  </div>
</div>
```

**Locked Strategies Table Columns:**
| Column | Accessor | Cell |
|--------|----------|------|
| Asset | `asset` | `<span className="font-bold">{value}</span>` |
| Status | `captain_status` | StatusBadge (ACTIVE=green, WARM_UP=amber, other=gray) |
| m | `m` | right-aligned monospace, or "—" if null |
| k | `k` | right-aligned monospace, or "—" if null |
| OO | `oo` | `value?.toFixed(4) ?? "—"`, right-aligned monospace |
| Sessions | `sessions` | `value?.join(", ") ?? "—"` |

**Trigger Badge Colors (for block rows):**
- `"always_on"` -> green
- `"session_open"`, `"scheduled"` -> blue
- `"per_trade"`, `"per_session"` -> amber
- default -> gray

### Task 5.3: Wire Route

**File:** `src/App.jsx` (EDIT)

```jsx
import ProcessesPage from "./pages/ProcessesPage";
<Route path="/processes" element={<ProcessesPage />} />
```

**Verification Checklist for Phase 5:**
1. Navigate to `/processes` -- page renders without errors
2. 3 process health cards in a row with status dots and badges
3. Locked strategies table with correct columns
4. 3 collapsible panels with correct block counts (13, 15, 11)
5. Collapse/expand persists to localStorage
6. API connections section shows connection status
7. 15-second polling starts on mount, stops on unmount (check Network tab)
8. Error state shown gracefully when backend unavailable

---

## Phase 6: System Overview Page

**Goal:** Build the most complex tab -- System Overview at `/system` with 19 panels. ADMIN-only.

**Spec Reference:** `OLD_GUI_TAB_SPECIFICATIONS.md` Section 4 (System Overview Tab)

### Task 6.1: Create SystemOverviewPage Component

**File:** `src/pages/SystemOverviewPage.jsx`

**Access Control:**
Since there is no auth context, hardcode the admin check:
```jsx
const isAdmin = true; // Role hardcoded as ADMIN (matches existing pattern)
if (!isAdmin) {
  return (
    <div className="h-screen bg-surface p-4 flex items-center justify-center">
      <div className="text-[#64748b] text-sm font-mono">Access restricted to administrators.</div>
    </div>
  );
}
```

**Data Fetching:**
```jsx
useEffect(() => {
  useSystemOverviewStore.getState().fetch();
}, []);
```

Also subscribe to WS updates if the store is already wired (Phase 1, Task 1.5).

**Page Layout:**
```
SystemOverviewPage
  Page shell
  Page title: "System Overview"
  Loading: show if overview is null
  
  Row 1: grid grid-cols-2 gap-4
    Panel 4.1: System Health (radar + scores)
    Panel 4.2: Network Concentration (DataTable)
  
  Row 2: grid grid-cols-3 gap-4
    Panel 4.3: Signal Quality (stat boxes + progress bar)
    Panel 4.4: Capacity Utilization (key-value list)
    Panel 4.5: Compliance Status (badge + requirements)
  
  Row 3: grid grid-cols-2 gap-4
    Panel 4.6: Action Queue (scrollable list)
    Panel 4.7: Data Quality (asset freshness rows)
  
  Row 4: grid grid-cols-2 gap-4
    Panel 4.8: Circuit Breaker (independent fetch, 6 stats)
    Panel 4.9: Deployment Status (6 container cards)
  
  Row 5: grid grid-cols-3 gap-4
    Panel 4.10: Active Constraints (key-value list)
    Panel 4.11: Reconciliation Status (process dots)
    Panel 4.12: Performance (bar chart placeholder)
  
  Row 6: grid grid-cols-3 gap-4
    Panel 4.13: Model Validation (static text)
    Panel 4.14: Governance Schedule (hardcoded table)
    Panel 4.15: Capacity Recommendations (static text)
  
  Row 7: full width
    Panel 4.16: Incident Log (searchable DataTable)
  
  Row 8: grid grid-cols-3 gap-4
    Panel 4.17: Admin Decision Log (static text)
    Panel 4.18: Stress Test Review (static text)
    Panel 4.19: Version History (hardcoded entries)
```

### Task 6.2: Build Individual Panels

Each panel follows this wrapper pattern:
```jsx
<div className="bg-surface-card border border-border-subtle p-3">
  <h3 className="text-sm font-mono text-captain-green tracking-[1.5px] uppercase mb-3">
    Panel Title
  </h3>
  {/* panel content */}
</div>
```

**Panel 4.1: System Health Dashboard**
- Data: `overview.diagnostic_health` (array of {dimension, score, status, details, timestamp})
- Chart: Recharts `<RadarChart>` with `<PolarGrid>`, `<PolarAngleAxis>`, `<Radar>`
- Fill color: `#0faf7a` (captain green) with opacity 0.3
- Stroke: `#0faf7a`
- Below chart: 2-column grid of dimension scores with StatusBadge per status
- Empty state: "No diagnostic data"

**Panel 4.2: Network Concentration**
- Data: `overview.network_concentration.exposures`
- Use `<DataTable>` with columns: Asset, Direction (badge: LONG=green, SHORT=red), Contracts, Users
- Header count: "X positions"

**Panel 4.3: Signal Quality**
- Data: `overview.signal_quality` ({total_evaluated, passed, pass_rate})
- 3 StatBox components in a row: Total Evaluated, Passed (green), Pass Rate (percentage)
- Progress bar below: width = pass_rate * 100 %, color: >= 70% green, >= 40% amber, < 40% red
- Use same progress bar pattern as RiskPanel payout target

**Panel 4.4: Capacity Utilization**
- Data: `overview.capacity_state` (arbitrary dict)
- Scrollable key-value definition list
- Empty state: "No capacity data"

**Panel 4.5: Compliance Status**
- Data: `overview.compliance_gate` ({execution_mode, requirements})
- Header badge: StatusBadge for execution_mode (AUTOMATIC=green, SEMI_AUTOMATIC=amber, other=gray)
- Body: key-value list of requirements
- Empty state: "No active requirements"

**Panel 4.6: Action Queue**
- Data: `overview.action_queue` (array of {dimension, status, details, timestamp})
- Scrollable list (max-h-[300px] overflow-y-auto)
- Each item: StatusBadge for status (CRITICAL=red, STALE=amber, other=gray) + dimension name (bold) + details (muted) + timestamp (right-aligned)
- Empty state: "No open actions"

**Panel 4.7: Data Quality**
- Data: `overview.data_quality.assets` (array of {asset_id, status, last_data_update})
- Each row: StatusDot (green if < 5 min since update, red if stale) + asset_id (bold) + status + formatTimeAgo(last_data_update)
- Empty state: "No asset data"

**Panel 4.8: Circuit Breaker / System Status**
- INDEPENDENT fetch from `api.health()` (not from system overview)
- Auto-refresh: 30-second setInterval (with cleanup)
- Manual refresh button
- 6 StatBox components in 2x3 grid:
  - System: StatusBadge (health.status)
  - Circuit Breaker: StatusBadge (health.circuit_breaker)
  - Uptime: `(health.uptime_seconds / 3600).toFixed(1) + "h"`
  - Active Users: number
  - API Connections: `${health.api_connections}` (connected/total string)
  - Last Signal: formatTimestamp(health.last_signal_time) or "—"

**Panel 4.9: Deployment Status**
- Independent fetch from `api.status()`, extract `processes`
- Hardcoded container list: `["questdb", "redis", "captain-offline", "captain-online", "captain-command", "nginx"]`
- Grid of 6 container cards, each: StatusDot (ok=green, error=red, other=amber) + container name
- For infra containers (questdb, redis, nginx): default to "ok" if not in API response

**Panel 4.10: Active Constraints**
- Data: `overview.system_params` (dict of key-value)
- Scrollable key-value list (max-h-[200px])
- Empty state: "No constraints loaded"

**Panel 4.11: Reconciliation Status**
- Independent fetch from `api.status()`, extract `processes`
- List of process roles with StatusDot + status text
- Empty state: "No process status available"

**Panel 4.12: Performance Panel**
- Recharts `<BarChart>` placeholder
- Currently no data: show "Performance data available via RPT-02 / RPT-10" centered muted text

**Panel 4.13: Model Validation**
- Static text: "AIM model validation metrics are available via RPT-04 (AIM Effectiveness Report). Decay detection monitors model drift continuously."

**Panel 4.14: Governance Schedule**
- Hardcoded table (8 rows):

| Event | Frequency | Status |
|-------|-----------|--------|
| SOD Reset | Daily 19:00 ET | Automated |
| Decay Detection | Per-session | Automated |
| AIM Rebalance | Weekly | Automated |
| Kelly Update | Per-trade | Automated |
| Strategy Injection Check | Monthly | Admin review |
| P1/P2 Rerun (Level 3) | On decay trigger | Admin review |
| System Health Diagnostic | 8h | Automated |
| Contract Roll | Quarterly | Admin confirm |

Status color: Automated=green, Admin review/confirm=amber

**Panel 4.15: Capacity Recommendations**
- Static text: "Capacity recommendations are computed by Online B9 (Capacity Evaluator). Data appears here when capacity evaluations run at session boundaries."

**Panel 4.16: Incident Log**
- Data: `overview.incident_log` (array)
- Full-width `<DataTable>` with search
- Columns: Time, Severity (badge), Type, Component, Status, Details (truncated)
- Severity badge colors: P1_CRITICAL=red (#ef4444), P2_HIGH=captain-orange (#ff8800), P3_MEDIUM=amber (#f59e0b), P4_LOW=gray (#64748b)
- Header count: "X incidents"

**Panel 4.17: Admin Decision Log**
- Static text: "Admin decisions (strategy adoptions, AIM toggles, TSM switches) are logged in P3-D17 session event log. View in History -> System Events tab."

**Panel 4.18: Stress Test Review**
- Static text: "Stress test results will be available after Phase 7 validation. Generate via RPT-08 (Regime Calibration)."

**Panel 4.19: Version History**
- Hardcoded:
  - v1.0.0 | 2026-03-14 | Initial Captain Function release -- V1+V2+V3 unified build
- Each entry: version badge (`px-2 py-0.5 text-[10px] font-mono bg-[rgba(59,130,246,0.15)] border border-[rgba(59,130,246,0.3)] text-[#3b82f6]`) + date + description

### Task 6.3: Wire Route

**File:** `src/App.jsx` (EDIT)

```jsx
import SystemOverviewPage from "./pages/SystemOverviewPage";
<Route path="/system" element={<SystemOverviewPage />} />
```

**Verification Checklist for Phase 6:**
1. Navigate to `/system` -- page renders without errors
2. All 19 panels visible in correct grid layout (8 rows)
3. Radar chart renders (even with no data -- show empty state)
4. Static placeholder panels show correct text from spec
5. Governance schedule table shows 8 rows with colored status
6. Incident log DataTable has search functionality
7. Circuit breaker panel fetches from /api/health independently
8. 30-second polling on circuit breaker (check Network tab)
9. Deployment status shows 6 container cards
10. Version history shows v1.0.0 entry

---

## Phase 7: Route Wiring + Validation Sweep

**Goal:** Ensure all routes are wired, all pages render correctly, all interactions work.

### Task 7.1: Final Route Verification

**File:** `src/App.jsx` should now have all 8 routes:
```jsx
<Routes>
  <Route path="/" element={<DashboardPage />} />
  <Route path="/models" element={<ModelsPage />} />
  <Route path="/config" element={<ConfigPage />} />
  <Route path="/settings" element={<SettingsPage />} />
  <Route path="/history" element={<HistoryPage />} />
  <Route path="/reports" element={<ReportsPage />} />
  <Route path="/processes" element={<ProcessesPage />} />
  <Route path="/system" element={<SystemOverviewPage />} />
</Routes>
```

Verify TopBar NavLink `to` values match these paths exactly:
- `/` (Dashboard)
- `/system` (System)
- `/processes` (Processes)
- `/history` (History)
- `/reports` (Reports)
- `/settings` (Settings)

### Task 7.2: Build Verification

Run `npx vite build` (or `npm run build`). Fix any compilation errors.

### Task 7.3: Dev Server Validation

Start dev server with `npm run dev`. Navigate to each route and verify:

1. **No console errors** -- no React warnings, no unhandled promise rejections
2. **Styling consistency** -- all panels/cards/tables use the same Tailwind patterns
3. **Data fetching** -- API calls attempted (will likely fail if backend not running, that's OK)
4. **Error states** -- graceful error messages when API calls fail
5. **Empty states** -- correct messages when data arrays are empty
6. **localStorage** -- Settings theme toggle and Processes collapse state persist across refresh
7. **Polling** -- Processes 15s interval and System Overview Circuit Breaker 30s interval start on mount, stop on unmount
8. **Search** -- History tables and System Overview incident log filter when typing
9. **Sub-tabs** -- History tab switches between 5 data views
10. **Downloads** -- Reports page download buttons create Blob URLs and trigger download

### Task 7.4: Cleanup

- Remove any unused imports
- Ensure all useEffect hooks have proper cleanup (clearInterval, etc.)
- Verify no eslint warnings in new files

**Final Verification Checklist:**
1. `npx vite build` succeeds with no errors
2. All 6 TopBar nav links route to correct pages
3. Each page has correct title (document.title updates)
4. No white screens or unhandled errors on any route
5. Responsive behavior: pages scroll vertically when content overflows

---

## Files Created/Modified Summary

### New Files
| File | Purpose |
|------|---------|
| `src/components/shared/StatusDot.jsx` | Colored status dot with pulse |
| `src/components/shared/StatusBadge.jsx` | Colored text badge |
| `src/components/shared/DataTable.jsx` | TanStack React Table wrapper |
| `src/components/shared/CollapsiblePanel.jsx` | Collapsible section with localStorage |
| `src/components/shared/StatBox.jsx` | Large number + label metric |
| `src/stores/processesStore.js` | Processes tab state + polling |
| `src/stores/reportsStore.js` | Reports tab state + generation |
| `src/stores/systemOverviewStore.js` | System overview state |
| `src/constants/blockRegistry.js` | Hardcoded 39-block registry |
| `src/pages/SettingsPage.jsx` | Settings tab |
| `src/pages/HistoryPage.jsx` | History tab with 5 sub-tabs |
| `src/pages/ReportsPage.jsx` | Reports tab with generation |
| `src/pages/ProcessesPage.jsx` | Processes tab |
| `src/pages/SystemOverviewPage.jsx` | System Overview tab (19 panels) |

### Modified Files
| File | Change |
|------|--------|
| `src/utils/formatting.js` | Add formatTimestamp, formatTimeAgo |
| `src/App.jsx` | Add 5 new route imports + Route entries + title cases |
| `src/ws/useWebSocket.js` | Wire system_overview to systemOverviewStore (if needed) |
| `package.json` / `package-lock.json` | Add recharts + @tanstack/react-table |

### NOT Modified (preserve exactly)
- `src/pages/DashboardPage.jsx`
- `src/pages/ModelsPage.jsx`
- `src/pages/ConfigPage.jsx`
- `src/components/layout/TopBar.jsx`
- `src/stores/dashboardStore.js`
- `src/stores/chartStore.js`
- `src/stores/notificationStore.js`
- `tailwind.config.js`
- `vite.config.mjs`
- All existing component files

---

## Dependencies to Install
- `recharts` (for RadarChart in System Overview 4.1 and BarChart in 4.12)
- `@tanstack/react-table` (for searchable data tables in History, Processes, System Overview)

## Tabs Functional vs Waiting on Backend
| Tab | Status | Notes |
|-----|--------|-------|
| Settings | Fully functional | No API calls needed |
| History | Partially functional | Signals/Decay/AIM from dashboard store; Trade Outcomes + System Events empty (backend not wired) |
| Reports | Functional with backend | Report type fetch + generation require running captain-command; graceful error state without it |
| Processes | Functional with backend | 15s polling to /api/processes/status; graceful error state without backend |
| System Overview | Functional with backend | Initial fetch + WS subscription; graceful error states; Circuit Breaker + Deployment panels have independent fetches |
