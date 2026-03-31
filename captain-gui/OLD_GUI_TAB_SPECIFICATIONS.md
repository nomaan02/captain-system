# Old GUI Tab Specifications

Reference document for rebuilding the Settings, Reports, System, and Processes tabs in the new captain-gui. Covers only **functionality, data, and behavior** -- no styling details.

---

## Table of Contents

1. [Settings Tab](#1-settings-tab)
2. [Reports Tab](#2-reports-tab)
3. [Processes Tab](#3-processes-tab)
4. [System Overview Tab](#4-system-overview-tab)
5. [History Tab](#5-history-tab)
6. [Shared Infrastructure](#6-shared-infrastructure)

---

## 1. Settings Tab

**Route:** `/settings`
**Access:** All authenticated users
**Data source:** Local auth context + localStorage (no API calls)

### Sections

#### 1.1 User Information Panel

Displays the currently authenticated user's identity:

| Field   | Source            | Format    |
|---------|-------------------|-----------|
| User ID | `auth.user.user_id` | Monospace |
| Role    | `auth.user.role`   | Plain text |

#### 1.2 Appearance Panel

A single toggle for light/dark theme:

- **Current state** is read from a Zustand store backed by `localStorage` key `"captain-theme"`
- **Default** is `"dark"`
- Button label: `"Switch to Light"` when dark, `"Switch to Dark"` when light
- On click: toggles the theme and persists to localStorage

### Data Flow

No API calls. All data comes from the auth context (injected at app level) and local storage.

---

## 2. Reports Tab

**Route:** `/reports`
**Access:** All authenticated users
**Data source:** REST API
**Polling:** None (on-demand generation)

### Layout

Two-panel grid layout:

1. **Left panel** (1/3 width): Report type selector list
2. **Right panel** (2/3 width): Generation controls + preview

### Report Types (from backend `REPORT_TYPES` dict)

The left panel fetches available report types from `GET /api/reports/types` on mount. Each entry displays:

| Report ID | Name | Trigger | Render Format |
|-----------|------|---------|---------------|
| RPT-01 | Pre-Session Signal Report | pre_session | in_app |
| RPT-02 | Weekly Performance Review | end_of_week | csv |
| RPT-03 | Monthly Decay & Warm-Up Report | first_of_month | csv |
| RPT-04 | AIM Effectiveness Report | monthly | csv |
| RPT-05 | Strategy Comparison Report | on_p1p2_run | csv |
| RPT-06 | Regime Change Report | regime_change | csv |
| RPT-07 | Daily Prop Account Report | daily | in_app |
| RPT-08 | Regime Calibration Report | monthly | csv |
| RPT-09 | Parameter Change Audit | on_demand | csv |
| RPT-10 | Annual Performance Report | annually | csv |
| RPT-11 | Financial Summary Export | monthly | csv |

### Behavior

1. **On mount:** Fetch report types, auto-select the first one
2. **Report selector (left):** Clicking a report type selects it and clears any previous result
3. **Generate button (right):** Calls `POST /api/reports/generate` with `{ report_type, user_id, params: {} }`
4. **While generating:** Button shows "Generating...", disabled state, plus a loading spinner
5. **After generation:** Displays:
   - Report metadata: `report_id`, `generated_at` timestamp (formatted as ET)
   - The render format badge (e.g., "csv" or "in_app")

### Download/Preview Behavior

After a report is generated, the right panel shows download buttons and a preview depending on the format:

- **CSV format** (`format === "csv"` or `data` is a string):
  - "CSV" download button: creates a Blob with `text/csv` type, downloads as `{report_type}_{date}.csv`
  - "JSON" download button: wraps the data in JSON, downloads as `{report_type}_{date}.json`
  - CSV preview: shows the first 20 rows of the CSV string in a `<pre>` block (scrollable, max height)

- **in_app format** (`format === "in_app"` and `data` is an object):
  - "JSON" download button
  - In-app preview: renders `JSON.stringify(data, null, 2)` in a `<pre>` block (scrollable, max height)

### API Contract

**Request:**
```json
POST /api/reports/generate
{
  "report_type": "RPT-01",
  "user_id": "primary_user",
  "params": {}
}
```

**Response:**
```json
{
  "report_id": "RPT-A1B2C3D4E5F6",
  "report_type": "RPT-01",
  "name": "Pre-Session Signal Report",
  "format": "in_app",
  "data": { ... },
  "generated_at": "2026-03-31T09:30:00"
}
```

---

## 3. Processes Tab

**Route:** `/processes`
**Access:** All authenticated users
**Data source:** REST API at `GET /api/processes/status`
**Polling:** Every 15 seconds (auto-refresh via `setInterval`)

### Sections (top to bottom)

#### 3.1 Process Health Cards (3-column row)

Three cards side by side, one for each process: **ONLINE**, **OFFLINE**, **COMMAND**.

Each card displays:

| Field | Source | Display |
|-------|--------|---------|
| Process name | Hardcoded | "CAPTAIN ONLINE" / "CAPTAIN OFFLINE" / "CAPTAIN COMMAND" |
| Status dot | `processes[role].status` | Green (ok), Yellow (halted), Red (error), Gray (unknown) -- pulsing when "ok" |
| Status badge | `processes[role].status` | Text badge: "OK" / "HALTED" / "ERROR" / "UNKNOWN" |
| Last heartbeat | `processes[role].timestamp` | Formatted as HH:MM:SS ET |

Status-to-dot mapping:
- `"ok"` -> green dot (pulsing)
- `"halted"` -> yellow dot
- `"error"` -> red dot
- anything else -> gray dot (off)

Status-to-badge mapping:
- `"ok"` -> green badge
- `"error"` -> red badge
- `"halted"` -> yellow badge
- anything else -> neutral/gray badge

#### 3.2 Locked Strategies Table

A data table showing each asset's locked ORB strategy parameters. Fetched from backend (which queries `p3_d00_asset_universe` and parses `locked_strategy` JSON).

| Column | Field | Format |
|--------|-------|--------|
| Asset | `asset` | Bold text |
| Status | `captain_status` | Badge: green="ACTIVE", yellow="WARM_UP", gray=other |
| m | `m` | Right-aligned monospace, or em-dash if null |
| k | `k` | Right-aligned monospace, or em-dash if null |
| OO | `oo` | Right-aligned monospace, 4 decimal places, or em-dash |
| Sessions | `sessions` | Comma-separated list (e.g., "NY") or em-dash |

If no strategies loaded, show: "No locked strategies loaded" (centered).

#### 3.3 Block Groups (3 collapsible sections)

Three collapsible panels, one per process: **CAPTAIN ONLINE**, **CAPTAIN OFFLINE**, **CAPTAIN COMMAND**.

Each panel:
- **Title:** "CAPTAIN {PROCESS}"
- **Header right:** Block count (e.g., "13 blocks") + status dot matching the process health
- **Collapsible:** Yes, with state persisted to localStorage key `processes-{process}`
- **Accent color:** ONLINE=green, OFFLINE=blue, COMMAND=gray

Each block row within a panel displays:

| Field | Source | Display |
|-------|--------|---------|
| Status dot | Inherits from parent process health | Green/yellow/red/gray dot |
| Block name | `block.name` | Bold text (e.g., "B1 Data Ingestion") |
| Trigger badge | `block.trigger_label` | Colored badge (see trigger colors below) |
| Description | `block.description` | Muted text description |
| Source file | `block.source_file` | Monospace path |

Trigger badge colors:
- `"always_on"` -> green
- `"session_open"`, `"scheduled"` -> blue/info
- `"per_trade"`, `"per_session"` -> yellow/warning
- anything else -> gray/neutral

#### 3.4 Full Block Registry (28 blocks total)

The complete block registry returned by the backend:

**Captain Online (13 blocks):**

| Block ID | Name | Trigger | Description |
|----------|------|---------|-------------|
| online-orchestrator | Online Orchestrator | 24/7 session loop | Session loop: evaluates at NY/LON/APAC opens, sequences B1-B9 per session |
| online-b1 | B1 Data Ingestion | Session open | Loads active assets, validates data quality, resolves contracts, computes features |
| online-b1f | B1 Feature Computation | Per session | Computes OHLCV, bid-ask spread, VIX, ATR, skew, volatility per asset |
| online-b2 | B2 Regime Probability | Per session | Classifies market regime (HIGH_VOL / LOW_VOL) via locked classifier or binary rule |
| online-b3 | B3 AIM Aggregation | Per session | Aggregates 15 AIM modifiers via Mixture-of-Experts gating with DMA weights |
| online-b4 | B4 Kelly Sizing | Per user/session | Computes optimal contract sizing per asset under regime uncertainty and TSM constraints |
| online-b5 | B5 Trade Selection | Per user/session | Universe-level asset selection using expected edge and correlation filters |
| online-b5b | B5B Quality Gate | Per user/session | Filters trades by quality threshold (edge x modifier x maturity) |
| online-b5c | B5C Circuit Breaker | Per user/session | 7-layer circuit breaker: scaling cap, halt, budget, expectancy, Sharpe, regime, manual |
| online-b6 | B6 Signal Output | Per user/session | Generates trading signals (direction, TP, SL, sizing) and publishes to Redis |
| online-b7 | B7 Position Monitor | Always-on (10s poll) | Monitors open positions (P&L, TP/SL proximity, regime shifts, time exits) |
| online-b8 | B8 Concentration Monitor | Post-session | Aggregates network-level exposure across users (V1: single-user pass-through) |
| online-b9 | B9 Capacity Evaluation | Post-session | Updates capacity metrics (signal supply, demand, constraints, diversity) |

**Captain Offline (15 blocks):**

| Block ID | Name | Trigger | Description |
|----------|------|---------|-------------|
| offline-orchestrator | Offline Orchestrator | Event-driven + scheduled | Event-driven scheduler: trade outcomes, daily/weekly/monthly/quarterly tasks |
| offline-b1-aim | B1 AIM Lifecycle | Per trade + daily + weekly | AIM state machine: INSTALLED -> COLLECTING -> WARM_UP -> ELIGIBLE -> ACTIVE |
| offline-b1-dma | B1 DMA Update | Per trade | Updates AIM inclusion probabilities using Dynamic Model Averaging (lambda=0.99) |
| offline-b1-drift | B1 Drift Detection | Daily (16:00 ET) | Daily AutoEncoder + ADWIN check for per-AIM concept drift |
| offline-b1-hdwm | B1 HDWM Diversity | Weekly (Monday) | Weekly: force-reactivate best AIM if all of a seed type are suppressed |
| offline-b1-hmm | B1 HMM Training (AIM-16) | Weekly/on-demand | Trains 3-state HMM for opportunity regime classification (LOW/NORMAL/HIGH) |
| offline-b2-bocpd | B2 BOCPD Decay | Per trade | Bayesian Online Changepoint Detection for strategy decay monitoring |
| offline-b2-cusum | B2 CUSUM Decay | Per trade + quarterly recal | Two-sided CUSUM for persistent mean shift detection (complementary to BOCPD) |
| offline-b2-esc | B2 Level Escalation | Per trade | Decay level 2: sizing reduction. Level 3: halt + P1/P2 rerun + AIM-14 |
| offline-b3 | B3 Pseudotrader | On demand | Signal replay engine for historical trade comparison and parameter sensitivity |
| offline-b4 | B4 Injection Comparison | On command / Level 3 | Compares candidate strategy vs current: ADOPT if 1.2x better AND pbo < 0.5 |
| offline-b5 | B5 Sensitivity Scanner | Monthly (1st) | Monthly perturbation grid for locked strategy parameters; flags FRAGILE |
| offline-b6 | B6 Auto-Expansion (AIM-14) | On Level 3 trigger | GA search for replacement strategy on Level 3 decay trigger |
| offline-b7 | B7 TSM Simulation | Per trade + on command | Block bootstrap Monte Carlo (10K paths) for prop firm pass probability |
| offline-b8-cb | B8 CB Params | Per trade | Estimates circuit breaker parameters: r_bar, beta_b, sigma, rho_bar |
| offline-b8-kelly | B8 Kelly Update | Per trade | Updates EWMA (win_rate, avg_win, avg_loss) and Kelly formula after each trade |
| offline-b9 | B9 System Diagnostic | Weekly + monthly | 8-dimension health check: strategy, features, staleness, AIM, edge, data, pipeline |
| offline-bootstrap | Asset Bootstrap | On ASSET_ADDED | Initializes new asset: D-22 trades, EWMA, BOCPD/CUSUM, Kelly, Tier 1 AIMs |
| offline-versioning | Version Snapshot | On model update | Records model versions before updates for auditability and rollback |

**Captain Command (11 blocks):**

| Block ID | Name | Trigger | Description |
|----------|------|---------|-------------|
| command-orchestrator | Command Orchestrator | Always-on | Always-on event loop: signal stream, Redis pub/sub, scheduler, FastAPI server |
| command-b1 | B1 Core Routing | Event-driven | Central message bus: signals -> GUI + API, commands -> handlers, alerts -> pub/sub |
| command-b2 | B2 GUI Data Server | 60s refresh + events | Dashboard assembly: capital, positions, signals, AIM, TSM, regime, notifications |
| command-b3 | B3 API Adapter | 30s health check | TopstepX integration: REST + WebSocket, 30s health monitoring, auto-reconnect |
| command-b4 | B4 TSM Manager | On startup | Loads and validates TSM JSON configs: fee schedule, scaling, payout rules |
| command-b5 | B5 Injection Flow | On P1/P2 events | Routes strategy injection: P1/P2 completion -> comparison -> user decision |
| command-b6 | B6 Reports | Scheduled + on-demand | 11 report types: pre-session, weekly, monthly decay, AIM, strategy, prop firm |
| command-b7 | B7 Notifications | Event-driven | 26 event types, 4 priority levels, Telegram + GUI + email with quiet hours |
| command-b8 | B8 Reconciliation | Daily 19:00 EST | Daily 19:00 EST: broker sync, SOD param computation, payout check, daily reset |
| command-b9 | B9 Incident Response | Event-driven | Auto-generated incident reports with severity routing (P1 -> P4) |
| command-b10 | B10 Data Validation | On user input | Validates all user-provided data: asset onboarding, TSM params, decisions |
| command-telegram | Telegram Bot | Always-on polling | Telegram integration: notifications + inline decisions (TAKEN/SKIPPED) |

#### 3.5 API Connections Panel

A simple status display at the bottom:

| Field | Source | Display |
|-------|--------|---------|
| Status dot | `api_connections.connected > 0` | Green (connected) or gray (disconnected), pulsing when connected |
| Connection count | `api_connections.connected` / `api_connections.total` | Text: "X/Y connected" |

### API Contract

**Request:**
```
GET /api/processes/status
```

**Response:**
```json
{
  "timestamp": "2026-03-31T09:30:00",
  "processes": {
    "ONLINE": { "status": "ok", "timestamp": "2026-03-31T09:29:55" },
    "OFFLINE": { "status": "ok", "timestamp": "2026-03-31T09:29:50" },
    "COMMAND": { "status": "ok", "timestamp": "2026-03-31T09:30:00" }
  },
  "blocks": [ ... ],
  "locked_strategies": [
    { "asset": "ES", "captain_status": "ACTIVE", "m": 7, "k": 33, "oo": 0.8832, "sessions": ["NY"] },
    ...
  ],
  "api_connections": { "connected": 1, "total": 1 }
}
```

---

## 4. System Overview Tab

**Route:** `/system`
**Access:** ADMIN role only (wrapped in `RequireRole` component)
**Data source:** REST API at `GET /api/system-overview` (single fetch on mount)
**State:** Zustand store (`systemOverviewStore`) -- also receives WebSocket pushes of type `"system_overview"`

### Layout (8 rows of panels)

The page is a vertically stacked grid of 19 admin panels. Loading spinner shown until data arrives.

#### Row 1: System Health + Concentration (2 columns)

**Panel 4.1: System Health Dashboard (8 Dimensions)**

A radar chart (Recharts `RadarChart`) visualizing 8 diagnostic dimensions, plus a grid of dimension scores below.

- **Data:** `overview.diagnostic_health` (array of `DiagnosticScore`)
- **Chart:** Radar chart with polar grid, dimension labels around the perimeter, scores 0-100
- **Score grid:** 2-column grid below the chart, each row showing:
  - Dimension name (text)
  - Score badge with color:
    - `"CRITICAL"` -> red
    - `"DEGRADED"` -> yellow
    - `"HEALTHY"` / other -> green
- **Empty state:** "No diagnostic data"

Data structure per score:
```typescript
{
  dimension: string;    // e.g., "strategy_health", "feature_staleness", "aim_coverage"
  score: number;        // 0-100
  status: string;       // "CRITICAL" | "DEGRADED" | "HEALTHY"
  details: string | null;
  timestamp: string;
}
```

The 8 dimensions (from P3-D22 system health diagnostic table):
Strategy health, feature staleness, AIM coverage, edge quality, data freshness, pipeline health, and more -- whatever the `b9_diagnostic.py` block computes.

**Panel 4.2: Network Concentration**

A data table (TanStack React Table) showing aggregate exposure across all users.

- **Data:** `overview.network_concentration.exposures` (array of `Exposure`)
- **Header count:** Shows number of positions
- **Columns:**

| Column | Field | Display |
|--------|-------|---------|
| Asset | `asset` | Plain text |
| Direction | `direction` | Badge: green="LONG", red="SHORT" |
| Contracts | `total_contracts` | Number |
| Users | `user_count` | Number |

- **Empty state:** Empty table

#### Row 2: Signal Quality + Capacity + Compliance (3 columns)

**Panel 4.3: Signal Quality Dashboard**

Displays signal pass/fail metrics from the last 7 days.

- **Data:** `overview.signal_quality` (type `SignalQuality`)
- **3 stat boxes (centered):**
  - Total Evaluated (large number)
  - Passed (large number, green)
  - Pass Rate (percentage, formatted to 1 decimal)
- **Progress bar below:**
  - Value: pass rate as percentage
  - Color: green (>= 70%), yellow (>= 40%), red (< 40%)
  - Label: "7-day pass rate"

**Panel 4.4: Capacity Utilization**

Generic key-value display of capacity state data.

- **Data:** `overview.capacity_state` (arbitrary dict from Online B9 `CAPACITY_EVALUATION` event)
- **Display:** Definition list of key-value pairs
  - Key: text label
  - Value: monospace string
- **Empty state:** "No capacity data"

**Panel 4.5: Compliance Status (Compliance Gate)**

Shows the execution mode and compliance requirements.

- **Data:** `overview.compliance_gate` (`{ execution_mode, requirements }`)
- **Header badge:** Execution mode with color:
  - `"AUTOMATIC"` -> green
  - `"SEMI_AUTOMATIC"` -> yellow
  - Other (e.g., `"MANUAL"`) -> gray
- **Body:** Definition list of requirements (key-value pairs)
- **Empty state:** "No active requirements"

The compliance gate is loaded from `config/compliance_gate.json`.

#### Row 3: Action Queue + Data Quality (2 columns)

**Panel 4.6: Action Queue**

Scrollable list of open/stale/critical action items from P3-D22.

- **Data:** `overview.action_queue` (array of `ActionItem`)
- **Header count:** Shows number open
- **Each item displays:**
  - Status badge with color:
    - `"CRITICAL"` -> red
    - `"STALE"` -> yellow
    - Other -> gray
  - Dimension name (bold)
  - Details text (small, muted -- if present)
  - Timestamp (right-aligned, small)
- **Scrollable:** Max height container with vertical scroll
- **Empty state:** "No open actions"

**Panel 4.7: Data Quality Dashboard**

Shows data freshness per asset.

- **Data:** `overview.data_quality.assets` (array of `DataQualityAsset`)
- **Each asset row:**
  - Status dot: green if `last_data_update` is within 5 minutes, red (pulsing) if stale
  - Asset ID (bold)
  - Captain status text
  - Time ago (e.g., "2m ago", "1h ago" -- relative time)
- **Empty state:** "No asset data"

#### Row 4: Circuit Breaker + Deployment (2 columns)

**Panel 4.8: Circuit Breaker / System Status**

Fetches data independently from `GET /api/health` (not from system overview).
Auto-refreshes every 30 seconds. Has a manual refresh button.

- **6 stat boxes (2x3 or 4-column grid):**

| Stat | Source | Display |
|------|--------|---------|
| System | `health.status` | Badge: green="OK", yellow="DEGRADED" |
| Circuit Breaker | `health.circuit_breaker` | Badge: green="ACTIVE", red="HALTED" |
| Uptime | `health.uptime_seconds` | Formatted as hours (e.g., "12.5h") |
| Active Users | `health.active_users` | Number |
| API Connections | `health.api_connections` | "connected/total" |
| Last Signal | `health.last_signal_time` | Timestamp or em-dash |

**Panel 4.9: Deployment Status**

Shows container status for all 6 Docker services.

- **Data:** Fetches from `GET /api/status`, extracts `processes` dict
- **Hardcoded container list:** `questdb`, `redis`, `captain-offline`, `captain-online`, `captain-command`, `nginx`
- **Display:** Grid of container cards, each showing:
  - Status dot: green="ok", red="error", yellow=other
  - Container name text
- For infra containers (questdb, redis, nginx): assumes "ok" if not in the processes dict

#### Row 5: Constraints + Reconciliation + Performance (3 columns)

**Panel 4.10: Active Constraints**

Shows current system parameters from P3-D17.

- **Data:** `overview.system_params` (dict of `param_key` -> `param_value`)
- **Display:** Scrollable key-value list (max height)
  - Key: text label
  - Value: monospace
- **Empty state:** "No constraints loaded"

**Panel 4.11: Reconciliation Status**

Shows process-level reconciliation status.

- **Data:** Fetches independently from `GET /api/status`, extracts `processes` dict
- **Display:** List of process roles with status dots
  - Green="ok", red="error", yellow=other
  - Shows the status text as a label
- **Empty state:** "No process status available"

**Panel 4.12: Performance Panel**

Bar chart of P&L performance data.

- **Data:** Optional `data` prop (array of `{ label: string, pnl: number }`)
- **Chart:** Recharts `BarChart` with X-axis labels and Y-axis values
- **Current state:** No data source wired -- shows placeholder: "Performance data available via RPT-02 / RPT-10"

#### Row 6: Model + Governance + Capacity Recs (3 columns)

**Panel 4.13: Model Validation**

Static placeholder panel.

- **Display:** "AIM model validation metrics are available via RPT-04 (AIM Effectiveness Report). Decay detection monitors model drift continuously."

**Panel 4.14: Governance Schedule**

Static table of governance events (hardcoded data, not from API).

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

- Status color: green for "Automated", yellow for "Admin review" and "Admin confirm"

**Panel 4.15: Capacity Recommendations**

Static placeholder panel.

- **Display:** "Capacity recommendations are computed by Online B9 (Capacity Evaluator). Data appears here when capacity evaluations run at session boundaries."

#### Row 7: Incident Log (full width)

**Panel 4.16: Incident Log**

Full-width searchable data table (TanStack React Table) with incident records.

- **Data:** `overview.incident_log` (array of `Incident`)
- **Header count:** Shows number of records
- **Searchable:** Has a search input placeholder "Search incidents..."
- **Columns:**

| Column | Field | Display |
|--------|-------|---------|
| Time | `timestamp` | Formatted timestamp (ET) |
| Severity | `severity` | Badge with color: P1_CRITICAL=red, P2_HIGH=orange, P3_MEDIUM=yellow, P4_LOW=gray |
| Type | `type` | Plain text |
| Component | `component` | Plain text |
| Status | `status` | Plain text |
| Details | `details` | Truncated text (max width), or em-dash |

Severity badge colors:
- `"P1_CRITICAL"` -> red
- `"P2_HIGH"` -> orange
- `"P3_MEDIUM"` -> yellow
- `"P4_LOW"` -> gray

#### Row 8: Admin Log + Stress Test + Version (3 columns)

**Panel 4.17: Admin Decision Log**

Static placeholder panel.

- **Display:** "Admin decisions (strategy adoptions, AIM toggles, TSM switches) are logged in P3-D17 session event log. View in History -> System Events tab."

**Panel 4.18: Stress Test Review**

Static placeholder panel.

- **Display:** "Stress test results will be available after Phase 7 validation. Generate via RPT-08 (Regime Calibration)."

**Panel 4.19: Version History**

Hardcoded version changelog.

- **Data:** Static array (not from API)
- **Current entries:**

| Version | Date | Changes |
|---------|------|---------|
| v1.0.0 | 2026-03-14 | Initial Captain Function release -- V1+V2+V3 unified build |

Each entry displays: version badge (monospace, blue tint), date, description.

### System Overview API Contract

**Request:**
```
GET /api/system-overview
```

**Response:**
```json
{
  "type": "system_overview",
  "timestamp": "2026-03-31T09:30:00",
  "network_concentration": {
    "exposures": [
      { "asset": "ES", "direction": "LONG", "total_contracts": 2, "user_count": 1 }
    ]
  },
  "signal_quality": {
    "total_evaluated": 150,
    "passed": 120,
    "pass_rate": 0.800
  },
  "capacity_state": { ... },
  "diagnostic_health": [
    { "dimension": "strategy_health", "score": 85, "status": "HEALTHY", "details": null, "timestamp": "..." }
  ],
  "action_queue": [
    { "dimension": "feature_staleness", "status": "STALE", "details": "VIX data 2h old", "timestamp": "..." }
  ],
  "system_params": { "max_positions": "5", "kelly_fraction_cap": "0.25", ... },
  "data_quality": {
    "assets": [
      { "asset_id": "ES", "status": "ACTIVE", "last_data_update": "2026-03-31T09:29:00" }
    ]
  },
  "incident_log": [
    {
      "incident_id": "INC-001",
      "type": "API_DISCONNECT",
      "severity": "P2_HIGH",
      "component": "topstep_stream",
      "details": "WebSocket connection lost",
      "status": "RESOLVED",
      "timestamp": "2026-03-31T08:15:00"
    }
  ],
  "compliance_gate": {
    "execution_mode": "AUTOMATIC",
    "requirements": { "min_winning_days": 5, "profit_threshold": 200 }
  }
}
```

---

## 5. History Tab

**Route:** `/history`
**Access:** All authenticated users
**Data source:** REST API at `GET /api/dashboard/{userId}` (single fetch on mount)

### Layout

Tab bar at top with 5 tabs, content area below showing one data table at a time.

### Tabs

#### 5.1 Signals Tab

Displays pending (unacted) signals.

- **Data:** `dashboard.pending_signals` array
- **Searchable:** "Search signals..."
- **Columns:**

| Column | Field | Format |
|--------|-------|--------|
| Time | `timestamp` | Formatted timestamp (ET) |
| Asset | `asset` | Plain text |
| Dir | `direction` | Plain text |
| Confidence | `confidence_tier` | Plain text |
| Quality | `quality_score` | 3 decimal places |
| ID | `signal_id` | Monospace, small text |

#### 5.2 Trade Outcomes Tab

Historical trade results.

- **Data:** Currently empty array (backend wiring pending)
- **Searchable:** "Search trades..."
- **Columns:**

| Column | Field | Format |
|--------|-------|--------|
| Time | `timestamp` | Formatted timestamp (ET) |
| Asset | `asset` | Plain text |
| Dir | `direction` | Plain text |
| Outcome | `outcome` | Badge: green="TP_HIT", red="SL_HIT" |
| P&L | `pnl` | Currency format, green if positive, red if negative |
| Account | `account_id` | Plain text |

#### 5.3 Decay Events Tab

BOCPD/CUSUM decay alerts.

- **Data:** `dashboard.decay_alerts` array
- **Searchable:** "Search decay events..."
- **Columns:**

| Column | Field | Format |
|--------|-------|--------|
| Time | `timestamp` | Formatted timestamp (ET) |
| Asset | `asset` | Plain text |
| Level | `level` | Number |
| CP Prob | `cp_prob` | Percentage (value * 100, 1 decimal) |
| CUSUM | `cusum_stat` | 4 decimal places |

#### 5.4 AIM Changes Tab

Current AIM state snapshot.

- **Data:** `dashboard.aim_states` array
- **Searchable:** "Search AIMs..."
- **Columns:**

| Column | Field | Format |
|--------|-------|--------|
| AIM ID | `aim_id` | Plain text |
| Name | `aim_name` | Plain text |
| Status | `status` | Plain text |
| Weight | `meta_weight` | 4 decimal places |
| Modifier | `modifier` | 4 decimal places |

#### 5.5 System Events Tab

System-wide event log.

- **Data:** Currently empty array (backend wiring pending)
- **Searchable:** "Search events..."
- **Columns:**

| Column | Field | Format |
|--------|-------|--------|
| Time | `timestamp` | Formatted timestamp (ET) |
| Type | `event_type` | Plain text |
| Asset | `asset` | Plain text |
| User | `user_id` | Plain text |
| Event ID | `event_id` | Monospace, small text |

---

## 6. Shared Infrastructure

### 6.1 API Client

All REST calls go through a centralized API client with base URL `/api`:

| Method | Endpoint | Used By |
|--------|----------|---------|
| `GET` | `/api/health` | Circuit Breaker panel (30s poll) |
| `GET` | `/api/status` | Deployment Status, Reconciliation panels |
| `GET` | `/api/dashboard/{userId}` | History tab (one-time fetch) |
| `GET` | `/api/system-overview` | System Overview page (one-time fetch + WS) |
| `GET` | `/api/processes/status` | Processes tab (15s poll) |
| `GET` | `/api/reports/types` | Reports tab (one-time fetch) |
| `POST` | `/api/reports/generate` | Reports tab (on-demand) |
| `POST` | `/api/validate/input` | Validation (unused in these tabs) |
| `POST` | `/api/validate/asset-config` | Validation (unused in these tabs) |

### 6.2 WebSocket

- Endpoint: `ws://{host}/ws/{userId}`
- The System Overview store can be updated via WebSocket messages of type `"system_overview"`
- Dashboard store receives updates via type `"dashboard"`, `"live_market"`, `"signal"`, `"command_ack"`, `"notification"`

### 6.3 Timestamp Formatting

All timestamps are displayed in **America/New_York** timezone:

- **Full timestamp:** `formatTimestamp()` -> "Mar 31, 09:30:00" (24h format)
- **Time only:** `formatTime()` -> "09:30:00" (24h format, ET suffix)
- **Relative time:** `formatTimeAgo()` -> "2m ago", "1h ago", "3d ago"
- **Currency:** `formatCurrency()` -> "$1,234.56"
- **Percentage:** `formatPct()` -> "85.0%"

### 6.4 Shared Enums/Constants

```typescript
CaptainStatus = "ACTIVE" | "WARM_UP" | "TRAINING_ONLY" | "INACTIVE" | "DATA_HOLD" | "ROLL_PENDING" | "PAUSED" | "DECAYED"
AimStatus = "INSTALLED" | "COLLECTING" | "WARM_UP" | "BOOTSTRAPPED" | "ELIGIBLE" | "ACTIVE" | "SUPPRESSED"
TradeOutcome = "TP_HIT" | "SL_HIT" | "MANUAL_CLOSE" | "TIME_EXIT"
IncidentSeverity = "P1_CRITICAL" | "P2_HIGH" | "P3_MEDIUM" | "P4_LOW"
NotificationPriority = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"
Regime = "LOW_VOL" | "HIGH_VOL"
CommandType = "TAKEN_SKIPPED" | "ADOPT_STRATEGY" | "REJECT_STRATEGY" | "PARALLEL_TRACK" | "SELECT_TSM" | "ACTIVATE_AIM" | "DEACTIVATE_AIM" | "CONCENTRATION_PROCEED" | "CONCENTRATION_PAUSE" | "CONFIRM_ROLL" | "UPDATE_ACTION_ITEM" | "TRIGGER_DIAGNOSTIC" | "MANUAL_PAUSE" | "MANUAL_RESUME"
Sessions = { 1: "NY", 2: "LON", 3: "APAC" }
```

### 6.5 Authentication Context

The auth context provides:
```typescript
{
  user: {
    user_id: string;    // e.g., "primary_user"
    role: string;       // "ADMIN" | "TRADER" | "VIEWER"
  }
}
```

System Overview page is gated to `role === "ADMIN"`.
