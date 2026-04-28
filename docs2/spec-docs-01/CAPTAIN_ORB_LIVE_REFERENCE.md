# Captain Live ORB — Reference for Agents

**Purpose:** Context for **`captain-system/`** when wiring live opening-range (OR) formation, breakout direction, TP/SL, and Topstep market data. Anchors OR semantics to the **local backtesting stack** (the path used for multi-asset P1/P2 screening), not to QuantConnect cloud execution.

**Not spec law:** Isaac’s specs and `docs/` remain authoritative for product intent; this file describes **repo reality** and **alignment targets**.

---

## MOST project — what it is (whole pipeline)

**MOST (Market Open Short-Term)** is a futures **opening-range breakout (ORB)** system: the first segment of the regular session defines a high/low “box”; trades are conditioned on whether and how price leaves that box, with exits scaled by **OR range** (multiples of the box height). Machine learning selects **which control model** and **which feature** (among 144 engineered signals) gate entries per asset.

End-to-end stages:

| Stage | Role | Where it lives (this repo) |
|-------|------|----------------------------|
| **Program 1** | Screen control models × features × exit grids; produce datasets (trades, features, correlations) | Historically bootstrapped from QC Object Store extracts; **production screening runs locally** via `local_backtester/`, `run_full_screening.py`, `model_generator/`, `mega-backtest-pipeline-extraction-new-decode/` (minute OHLCV), `pipeline/` adapters |
| **Program 2** | Lock one **(m, k)** strategy per asset (model id + feature id), regime class, thresholds, OO metrics | `pipeline_p2/`; outputs staged under `captain-system/data/p2_outputs/{ASSET}/` (e.g. `p2_d06_locked_strategy.json`) |
| **Program 3 — Captain** | **Operate** the locked strategies in production: data → regime/AIM → risk → signals → broker/UI feedback | `captain-system/` (Docker: Offline, Online, Command), QuestDB, Redis, TopstepX |

**Research vs live data:** P1/P2 consume **local minute bars** (ET) and shared **`config.py`** session/OR parameters. Captain consumes **TopstepX streams + REST**, **QuestDB state**, and the same **locked JSON** loaded into `p3_d00`. Aligning live OR clocks and OR high/low logic to **`config.py` + local backtester behavior** keeps research and production comparable.

---

## Local backtesting approach (primary OR / session reference)

QuantConnect Cloud is **not** the execution path for bulk P1/P2 screening today. The authoritative **operational** picture is:

1. **Minute market data** — CSV pipelines under `mega-backtest-pipeline-extraction-new-decode/` (and related exports); ET timestamps; per-asset combined minute files.
2. **Core engine** — `local_backtester/backtest_engine.py`: day-by-day OR → sizing → entry/exit; uses `config.StrategyConfig`, `risk_manager`, **`feature_bridge.FeatureBridge`** / **`ORState`** (OR high/low from first N minutes of session bars).
3. **Features** — `local_backtester/feature_bridge.py` feeds pandas bars into `pipeline/feature_engine_adapter.py` (`FeatureEngineRunner`) **without** a QC runtime.
4. **Orchestration** — `run_full_screening.py`, `local_backtester/run_pipeline.py`, `batch_runner.py`, `pipeline_p2/` for multi-tier and P2 regime steps.

**OR window in local research:** Still defined by root **`config.py`**:

- **`StrategyConfig`:** `or_start`, `or_end`, `or_window_minutes` (e.g. NY-style 09:30–09:35 = 5 minutes).
- **`SESSION_REGISTRY`:** Per session type (`NY`, `LONDON`, `NY_PRE`, `APAC`): `or_start`, `or_end`, `eod_*`, `filter_*`, `overnight`.
- **`ASSET_SESSION_MAP`:** Asset symbol → session type (e.g. `ES` → `NY`, `NKD` → `APAC`).

**Legacy / QC Algorithm Lab:** Root **`opening_range.py`** (`OpeningRangeTracker`) mirrors **bar-based** OR accumulation for the QC-deployed algorithm. It is **LOCKED**. For Captain live code, **do not edit** it; **replicate semantics** (session bounds + first-*m*-minute high/low + completion after OR end) using Topstep bars/quotes or REST minute bars. **`local_backtester`’s `ORState` + `FeatureBridge`** document the fields local screening expects (upper/lower bound, OR open/close, volume, validity).

**Further reading:** `local_backtester/PLAN.md`, `docs/MOST_COMPLETE_REFERENCE.md` (section on local P1/P2 infrastructure).

---

## 1. P1/P2 notation — `m` and `k`

| Symbol | Meaning | NOT |
|--------|---------|-----|
| **`m`** | P2 **control model id** (which screened model locked for the asset) | OR length in minutes |
| **`k`** | P2 **feature id** (which of the 144 engineered features the lock uses) | Tick count, SL distance, breakout threshold, OR width multiplier |

**Authoritative per-asset locks (on disk):** `captain-system/data/p2_outputs/{ASSET}/p2_d06_locked_strategy.json`. Same payload is loaded into QuestDB `p3_d00_asset_universe.locked_strategy` by loaders/fix scripts.

---

## 2. OR window duration — Captain vs research (gap)

### 2.1 Research source of truth (local stack)

Use **`config.py`** (`SESSION_REGISTRY`, `ASSET_SESSION_MAP`, `StrategyConfig`) **and** the **local backtester** day loop / `FeatureBridge` OR construction — that is what P1/P2 screening assumed.

### 2.2 Captain / QuestDB today

- **`p3_d00_asset_universe.session_hours`:** Venue open/close (e.g. NY 09:30–16:00). **Not** the same granularity as `or_start` / `or_end`.
- **Staged `locked_strategy` JSON** usually does **not** embed full `SESSION_REGISTRY` OR times.

### 2.3 `OR_window_minutes` inside Captain code

**File:** `captain-system/captain-online/captain_online/blocks/b1_features.py`

```text
get_or_window_minutes(locked_strategy) →
    locked_strategy["strategy_params"]["OR_window_minutes"]  # default 15 if missing
```

Used for **AIM-15** (`opening_volume_ratio`). **Default 15** may **differ** from the **5-minute** OR in `config.py` unless you set `strategy_params` explicitly.

### 2.4 What implementers should do

For **live OR** to match **local research**:

1. Treat **`config.py` + session type for the asset** as the calendar authority for OR start/end (or equivalent minutes).
2. Optionally mirror into `captain-system/config/` or `locked_strategy.strategy_params` / D00 so Online does not depend on reading the QC project tree.
3. Do **not** assume `get_or_window_minutes()` equals the OR window used in `local_backtester` without checking.

---

## 3. `locked_strategy` JSON — what actually gets stored

### 3.1 Shape written by production loaders / fix scripts

**Sources:** `captain-system/scripts/load_p2_multi_asset.py`, `fix_locked_strategies.py`, `seed_real_asset.py`.

**Typical keys:**

| Field | Description |
|-------|-------------|
| `model` / `m` | P2 control model id |
| `feature` / `k` | P2 feature id |
| `threshold` | Classifier / signal threshold from P2 |
| `regime_class` | e.g. REGIME_NEUTRAL |
| `OO` | Out-of-sample objective metric |
| `composite_score`, `complexity_tier`, `dominant_regime` | P2 metadata |
| `accuracy_OOS`, `confidence_flag` | From P2-D08 |
| `source` | e.g. `"P2-D06"` |

**Often missing** in DB (B6 uses **defaults**):

- `tp_multiple`, `sl_multiple` (defaults 2.0 / 1.0 in B6)
- `sl_method` (`OR_RANGE`)
- `default_direction` (**0** until live breakout resolved)
- `strategy_params` (e.g. `OR_window_minutes`)

### 3.2 Tests / synthetic fixtures

**File:** `captain-system/tests/fixtures/synthetic_data.py` — extended shape for unit tests; **do not assume** production rows match.

### 3.3 B6 TP/SL wiring today

**File:** `captain-system/captain-online/captain_online/blocks/b6_signal_output.py`

- TP/SL from `tp_multiple` / `sl_multiple`, `features["or_range"]`, `features["entry_price"]`, **`direction`** (levels `None` if `direction == 0`).
- `_determine_direction` is still **stub** (`default_direction` only) — **no** live breakout.

---

## 4. `quote_cache` — shape and semantics

**File:** `captain-system/shared/topstep_stream.py` — `QuoteCache`, global `quote_cache`.

- **Key:** TopstepX `contract_id`.
- **Value:** **Latest merged quote** per contract (partial GatewayQuote updates overlaid).
- **Not:** Tick history or QuestDB mirror.

**GatewayQuote fields** (see **`TOPSTEPX_API_REFERENCE.md`**):  
`symbol`, `lastPrice`, `bestBid`, `bestAsk`, `change`, `changePercent`, `open`, `high`, `low`, `volume`, `timestamp`

**OR extremes live:** Prefer **`lastPrice`** on each update (with `on_quote`) **or** build **1-minute bars** via REST `History/bars` to match **local backtester** bar-based OR.

**B1 today:** `_get_latest_price()` uses `quote_cache[...]lastPrice` with REST fallback.

---

## 5. MarketStream — hook points

**File:** `captain-system/shared/topstep_stream.py` — `MarketStream`.

```python
MarketStream(token, contract_id=..., contract_ids=..., on_quote=..., on_trade=..., on_depth=...)
```

**Flow:** `GatewayQuote` → `quote_cache.update` → optional **`on_quote`** callback.

**`captain-online/main.py`** currently starts the stream **without** `on_quote` — no built-in OR accumulator yet.

**Threading:** Stream thread + asyncio loop; use thread-safe OR state or hand off to the orchestrator.

---

## 6. Quick file index

| Topic | Path |
|--------|------|
| Local backtest engine + OR day loop | `local_backtester/backtest_engine.py` |
| Local OR state / feature bridge | `local_backtester/feature_bridge.py` (`ORState`, `FeatureBridge`) |
| Local backtester plan / data layout | `local_backtester/PLAN.md`, `local_backtester/COMMANDS.md` |
| P1/P2 screening orchestration | `run_full_screening.py`, `pipeline_p2/` |
| Session/OR calendar (shared with research) | `config.py` (`SESSION_REGISTRY`, `ASSET_SESSION_MAP`, `StrategyConfig`) |
| QC Algorithm OR tracker (locked, legacy path) | `opening_range.py` |
| Captain stream + cache | `captain-system/shared/topstep_stream.py` |
| Captain Online entry | `captain-system/captain-online/captain_online/main.py` |
| B1 price / features | `b1_data_ingestion.py`, `b1_features.py` |
| B6 direction / TP/SL | `b6_signal_output.py` |
| Locked JSON → DB | `load_p2_multi_asset.py`, `fix_locked_strategies.py` |
| Topstep API field names | `TOPSTEPX_API_REFERENCE.md` |

---

## 7. Consolidated answers (copy-paste for other agents)

1. **OR window (research):** **`config.py`** + **local backtester** (`local_backtester/`, minute bars). Not QC cloud as the screening runtime.
2. **OR window (Captain):** D00 `session_hours` is coarse; AIM-15 uses `strategy_params.OR_window_minutes` (default 15). **Explicitly align** Captain to `config.py` / local OR length.
3. **locked_strategy:** P2 metadata + optional execution fields; B6 defaults missing TP/SL/direction.
4. **quote_cache / stream:** Last quote per contract; use **`on_quote`** or REST minute bars for OR accumulation.

---

## 8. Captain (Program 3) — function at the end of the pipeline

Captain is the **operational layer** that runs **after** P1/P2 have frozen per-asset **(m, k)** and supporting datasets. It does **not** re-screen the full model grid; it **executes and governs** the locked configuration in real time.

**Responsibilities:**

- **Ingest** live and near-live data (TopstepX MarketStream/REST, external feeds where implemented), **validate** quality, and compute **pre-session / intraday features** consistent with the locked feature engine expectations.
- **Load** immutable research outputs from QuestDB: locked strategies (P2-D06 analog), EWMA/Kelly/AIM state (Offline-maintained), TSM/user silos, system params.
- **Captain Online** — session-aware orchestration: regime/AIM aggregation → circuit breaker / fees → sizing → **signal output (B6)** → Redis streams for Command; **position monitor (B7)** for outcomes.
- **Captain Offline** — strategic maintenance: AIM training hooks, decay, Kelly/EWMA/BOCPD updates, pseudotrader/diagnostics — fed by trade outcomes and research tables.
- **Captain Command** — **human and API surface**: route signals to GUI, TAKEN/SKIPPED, reconciliation, notifications, multi-user isolation intent.

**Why ORB live wiring matters here:** Research (local backtester) fixes **when** the OR completes and **what** high/low/range mean on **minute bars**. Captain must reproduce that **clock and price semantics** on **Topstep data** so **direction**, **entry**, and **OR-range-based TP/SL** are not arbitrary relative to the backtest that justified the lock.

**Critical loop (summary):** Online produces signals → Command/GUI/trader → positions → B7 detects exits → outcomes → Offline updates state → next session’s Online run reflects updated risk/intelligence.

---

*Last updated: 2026-03-27 — local backtester as primary research reference; MOST + Captain roles appended.*
