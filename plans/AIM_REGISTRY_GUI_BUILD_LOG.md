# AIM Registry Dashboard — GUI Build Log

**Started:** 2026-04-01 05:35 ET
**Branch:** finalising
**Goal:** Replace primitive ModelsPage AIM list with a real-time 4x4 AIM registry grid + clickable detail modals with QuestDB validation data.

---

## Implementation Order

1. Backend endpoint (b2_gui_data_server.py + api.py)
2. API client method (client.js)
3. AimDetailModal component
4. AimRegistryPanel component
5. Dashboard integration (DashboardPage.jsx)
6. GUI rebuild + test

---

## Step 1: Backend Endpoint ✅

**Files changed:**
- `captain-command/captain_command/blocks/b2_gui_data_server.py`
- `captain-command/captain_command/api.py`

### Changes to b2_gui_data_server.py

**1a. Added AIM-05 to `_AIM_NAMES`** (line ~391)
- Was missing from the dict. Added `5: "Order Book Depth"`.

**1b. Added `_AIM_TIERS` dict** (line ~397)
- Maps aim_id → tier number. Values from reconciliation matrix:
  - Tier 1 (weekly): 4, 6, 8, 11, 12, 15
  - Tier 2 (monthly): 1, 2, 3, 7, 9, 10
  - Tier 3 (quarterly): 13, 14
  - 0 (N/A): 5 (deferred), 16 (session weights only)

**1c. Added `_AIM_FEATURE_CONNECTED` dict** (line ~401)
- Maps aim_id → bool. Per F5.9 reconciliation finding:
  - `False`: AIMs 1, 2, 3, 5, 7 (data adapters return None / STUB_NONE)
  - `True`: all others (4, 6, 8–16)

**1d. Added `get_aim_detail(aim_id: int) -> dict` function** (after `_get_aim_states`)
- Queries P3-D01 `p3_d01_aim_model_states` filtered by aim_id, deduped by (asset_id) keeping newest row. Extracts: status, current_modifier, warmup_progress, last_retrained.
- Queries P3-D02 `p3_d02_aim_meta_weights` filtered by aim_id, deduped by (asset_id). Extracts: inclusion_flag, inclusion_probability, recent_effectiveness, days_below_threshold.
- For AIM-16 only: checks P3-D26 `p3_d26_hmm_opportunity_state` row count.
- Parses `current_modifier` from STRING to float (D01 stores it as STRING in QuestDB).
- Serializes `last_retrained` timestamp to ISO string.
- Merges D01+D02 by asset, returns `per_asset` list + `validation` summary.

**Return shape:**
```json
{
  "aim_id": 4,
  "aim_name": "IVTS",
  "tier": 1,
  "per_asset": [
    {
      "asset_id": "ES",
      "d01_status": "ACTIVE",
      "d01_modifier": 1.10,
      "d01_warmup_progress": 100.0,
      "d01_last_retrained": "2026-04-01T...",
      "d02_inclusion_flag": true,
      "d02_inclusion_probability": 0.15,
      "d02_recent_effectiveness": 0.73,
      "d02_days_below_threshold": 0
    }
  ],
  "validation": {
    "d01_populated": true,
    "d02_populated": true,
    "d26_populated": null,
    "feature_data_connected": true,
    "all_checks_pass": true
  }
}
```

### Changes to api.py

**1e. Added import** of `get_aim_detail` from b2_gui_data_server (line ~43).

**1f. Added route** `GET /api/aim/{aim_id}/detail` (after `/api/dashboard/{user_id}`).
- Sync def (runs in thread pool like the dashboard endpoint).
- Passes through `_make_json_safe()` for NaN/Infinity handling.

### Design decisions

- **Dedup strategy:** Same pattern as `_get_aim_states` — ORDER BY last_updated DESC, keep first per key. QuestDB LATEST ON only works with SYMBOL columns and aim_id is INT.
- **Modifier parsing:** D01 stores `current_modifier` as STRING. We parse to float in the backend so the frontend gets a number. None/unparseable → null.
- **D26 check:** Simple row count rather than complex state validation. If any rows exist, it's considered populated.
- **all_checks_pass:** Requires d01 + d02 populated + feature connected. For AIM-16 also requires d26.

---

## Step 2: API Client Method ✅

**File changed:** `captain-gui/src/api/client.js`

Added `aimDetail(aimId)` method — calls `GET /api/aim/{aimId}/detail`. Uses existing `get()` helper (fetchJson with Content-Type header). Placed in a new `// AIM Registry` section above `// System`.

## Step 3: AimDetailModal Component ✅

**File created:** `captain-gui/src/components/aim/AimDetailModal.jsx`

### Props
- `aimId` (int) — which AIM to load
- `aimName` (string) — display name for header
- `onClose` (function) — callback to dismiss

### Behavior
- On mount, calls `api.aimDetail(aimId)` to fetch backend data.
- Click-outside-to-close via mousedown listener on document (same pattern as TopBar dropdown).
- Escape key also closes.
- Shows loading spinner, error state, or data.

### Layout (3 sections)
**Section A — Per-Asset Breakdown Table:**
- Columns: Asset, Status (StatusBadge), Modifier (green >1.0, red <1.0, white =1.0), Weight (inclusion_probability), Warmup (%), Last Retrained (short date).
- Missing/null values show red ✗ icon.

**Section B — Data Validation:**
- 2-col grid showing D01, D02, feature feed, D26 (AIM-16 only) with ✓/✗ icons.
- Summary banner: "ALL CHECKS PASS" (green) or "VALIDATION INCOMPLETE" (red).

**Section C — AIM Configuration (static):**
- Tier + retrain frequency, feed status, feature gate days, learning gate trades, z-score thresholds.
- Data hardcoded in `AIM_CONFIG` dict — sourced from reconciliation matrix.

### Design decisions
- `AIM_CONFIG` is static (from reconciliation matrix). Thresholds don't change at runtime.
- Unicode arrows (→) used in threshold strings for compactness.
- Feed status color-coded: CONNECTED=green, STUB_NONE=red, N/A/Internal=gray.
- Modal: `max-w-[640px]`, `max-h-[80vh]`, `bg-surface-elevated`, `border-border-accent`.
- Footer matches RiskPanel pattern (`SYS:AIM_REGISTRY` / `SRC:P3-D01+D02`).

## Step 4: AimRegistryPanel Component ✅

**File created:** `captain-gui/src/components/aim/AimRegistryPanel.jsx`

### Data flow
- Reads `aimStates` from `useDashboardStore` (populated by WebSocket dashboard snapshot).
- Groups rows by `aim_id`, then aggregates across assets per AIM.
- Always renders all 16 AIMs (ALL_AIMS constant) even if backend has no data for some.

### Aggregation logic (`aggregateAim`)
- **Status:** Worst across assets. Priority order: BLOCKED < INACTIVE/DEFERRED < WARM_UP < BOOTSTRAPPED < ELIGIBLE < ACTIVE.
- **Modifier:** Shows range (e.g., "0.85–1.10") if min != max, otherwise single value. Parsed from string or number.
- **Warmup:** Shows minimum across assets (conservative — the lagging asset matters).
- **Weight:** Average of meta_weight across assets (for the tiny bar).

### AimCard design (~80px tall)
- Header row: `AIM-{id:02d}` + status badge (6 color variants from spec).
- Short name below header (abbreviated for card width).
- Modifier value: green if all >1.0, red if all <1.0, white if mixed/neutral. AIM-16 shows "SESSION BUDGET" in cyan instead.
- Meta-weight bar: 3px green fill bar (0-100% of inclusion weight).
- Warmup progress bar: 2px amber bar, only visible when status=WARM_UP.
- ELIGIBLE shows "Features ready" text in cyan.
- Tier badge: tiny T1/T2/T3 in top-right corner (T1=green, T2=blue, T3=amber). Hidden for tier 0 (AIM-05, AIM-16).
- AIM-05 special: dashed border + 60% opacity + always shows DEFERRED.

### Layout
- 4-column grid by default, responsive: 3-col at lg, 2-col at md/sm.
- Wrapped in `CollapsiblePanel` with localStorage key `captain-aim-registry-open`.
- Header shows `{activeCount}/16 active` counter.

### Modal trigger
- Clicking any AimCard sets `selectedAim` state, rendering `AimDetailModal` as a portal overlay.
- `onClose` clears the selection.

### Design decisions
- Short names (e.g., "Opts Skew" not "Options Skew & Positioning Analyzer") to fit card width.
- Status badge uses inline styles matching StatusBadge.jsx colors but with smaller py-0 for compactness.
- Tier badge positioned absolute top-right to avoid interfering with status badge flow.
- No external deps — pure Tailwind + existing CollapsiblePanel.

## Step 5: Dashboard Integration ✅

**File changed:** `captain-gui/src/pages/DashboardPage.jsx`

- Imported `AimRegistryPanel` from `../components/aim/AimRegistryPanel`.
- Placed `<AimRegistryPanel />` directly below `<RiskPanel />` in the left column (`Panel id="left"`).
- Both are inside `overflow-y-auto` div, so the left column scrolls naturally when content exceeds viewport.
- **Layout choice: Option C** — left column below RiskPanel. User can collapse via CollapsiblePanel toggle (persisted to localStorage key `captain-aim-registry-open`).

## Step 6: Rebuild + Test ✅

**Command:** `docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build captain-gui captain-command`

- Vite build: 758 modules transformed, built in 3.22s. No errors.
- Both containers recreated and healthy within 6 seconds.
- captain-gui container serves new static assets via nginx.

### Endpoint verification

| AIM | D01 | D02 | D26 | Feature | all_checks | Assets |
|-----|-----|-----|-----|---------|------------|--------|
| 01 (VRP) | false | false | n/a | false | false | 0 |
| 04 (IVTS) | true | true | n/a | true | true | 10 |
| 16 (HMM) | false | false | false | true | false | 0 |

- AIM-04 returns 10 assets all BOOTSTRAPPED with equal DMA weights (0.1667).
- AIM-01 correctly shows no data (STUB_NONE — external options data unavailable).
- AIM-16 correctly checks D26 table (empty — HMM not yet trained).
- GUI accessible at http://localhost:80, AIM Registry panel visible below RiskPanel in left column.

---

## Cosmetic Adjustments (post-build) ✅

### 1. Left column vertical resize

**File changed:** `captain-gui/src/pages/DashboardPage.jsx`

- Added `useLeftLayout` persistence hook (localStorage key `captain-left-layout`).
- Replaced single `overflow-y-auto` div with a `Group orientation="vertical"` containing two Panels:
  - `Panel id="risk" defaultSize={60} minSize={15}` — RiskPanel with own scrollable overflow
  - `ResizeHandle orientation="vertical"` — draggable separator (same cyan highlight as other separators)
  - `Panel id="aim-registry" defaultSize={40} minSize={10}` — AimRegistryPanel with own scrollable overflow
- Layout is persisted to localStorage, so user's resize preference survives page reloads.

### 2. Custom scrollbar styling

**File changed:** `captain-gui/src/global.css`

- Added Firefox support: `scrollbar-width: thin; scrollbar-color: #1a3038 transparent` (uses border-subtle color).
- Added WebKit (Chrome/Edge/Safari) scrollbar overrides:
  - Width/height: 5px (down from browser default ~12px)
  - Track: transparent background
  - Thumb: `#1a3038` (border-subtle), square corners (`border-radius: 0`)
  - Thumb hover: `#2e4e5a` (border-accent) for visibility on interaction
  - Corner: transparent
- Applied globally via `*` selector so all scrollable areas match.

---

## AIM Activation Buttons ✅

### Backend (api.py)

Added two REST endpoints that reuse the existing `route_command` → Redis → Offline pipeline:

- `POST /api/aim/{aim_id}/activate` — sends `ACTIVATE_AIM` command
- `POST /api/aim/{aim_id}/deactivate` — sends `DEACTIVATE_AIM` command

Both use a no-op `gui_push_fn` since there's no active WebSocket context in a REST call. The Offline orchestrator's `_handle_aim_activation()` handles the actual D01 status update for all assets.

### API client (client.js)

- `aimActivate(aimId)` → POST
- `aimDeactivate(aimId)` → POST

### AimRegistryPanel changes

- Added `CAN_ACTIVATE` set: `INACTIVE`, `BOOTSTRAPPED`, `ELIGIBLE`, `SUPPRESSED`.
- Each AimCard now shows a toggle button:
  - Green "Activate" for INACTIVE/BOOTSTRAPPED/ELIGIBLE/SUPPRESSED
  - Red "Deactivate" for ACTIVE
  - No button for DEFERRED (AIM-05) or WARM_UP (feature gate not met)
- Button uses `e.stopPropagation()` so clicking it doesn't also open the detail modal.
- `togglingAim` state tracks which AIM is mid-request (shows "..." and disables button).
- 1.5s cooldown after API call before re-enabling, to let Offline process the command.

### Activation lifecycle (existing backend, not modified)

| From Status | Action | Result |
|---|---|---|
| BOOTSTRAPPED | ACTIVATE_AIM | → ACTIVE (no gate check) |
| ELIGIBLE | ACTIVATE_AIM | → ACTIVE (learning gate soft-checked, logged if not met) |
| INACTIVE | ACTIVATE_AIM | → ACTIVE (creates rows for all universe assets) |
| SUPPRESSED | ACTIVATE_AIM | → ACTIVE (re-activation) |
| ACTIVE | DEACTIVATE_AIM | → SUPPRESSED |

---

## D02 Meta-Weight Seeding for Tier 2/3 AIMs ✅

**Date:** 2026-04-01

### Problem
AIMs 9, 10, 13, 14 showed "VALIDATION INCOMPLETE" because bootstrap only seeded D02 for Tier 1 AIMs (4, 6, 8, 11, 12, 15).

### Pre-seed validation
- Confirmed existing D02 shape: `inclusion_probability=0.1667 (1/6), inclusion_flag=true, recent_effectiveness=0.0, days_below_threshold=0`
- Confirmed B3 aggregation normalizes weights at runtime (`dma_weight / total_weight`), so absolute values don't matter
- No need to update existing Tier 1 weights

### Seeded
40 rows: AIMs [9, 10, 13, 14] × 10 assets, `inclusion_probability=0.166667`, matching Tier 1 pattern.

### Post-seed validation
- 10 AIMs now have D02 data (6 Tier 1 + 4 Tier 2/3)
- AIMs 9, 10, 13, 14: all_checks_pass = true
- Remaining INCOMPLETE (expected): AIMs 1, 2, 3, 5, 7 (STUB_NONE feeds), AIM-16 (D26 empty)

### Command used
```bash
docker compose exec captain-command python3 -c "..."
```
Ran inside captain-command container to use shared.questdb_client.
