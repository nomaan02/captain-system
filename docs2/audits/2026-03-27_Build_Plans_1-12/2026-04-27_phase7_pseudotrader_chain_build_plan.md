---
title: Phase 7 — PG-09 / PG-10 / PG-13 Pseudotrader Chain Build Plan
date: 2026-04-27
phase: 7
campaign: Captain Offline Audit Fix Campaign (12 phases)
companion_to:
  - docs2/audits/2026-04-22_offline_spec_vs_code_audit copy.md
  - docs2/audits/phase-ref-docs/phase-2/captain_offline_audit_decisions_2026-04-27.md
  - docs2/audits/phase-ref-docs/phase-7/2026-04-27_phase7_stage1a_audit_pass.md
  - docs2/audits/phase-ref-docs/phase-7/2026-04-27_phase7_design_captain_online_replay.md
  - docs2/spec-docs-02/offline/32_P3_Offline_Full_Pseudocode.md
  - docs2/spec-docs-02/online/33_P3_Online_Full_Pseudocode 1.md
status: GO — 14 batches GO, 1 watch item (PG-11 / Q-04) flagged as out-of-scope dependency
executor: Cursor Composer 2
---

# Phase 7 — PG-09 / PG-10 / PG-13 Pseudotrader Chain

This plan covers audit findings **F-22, F-23, F-24, F-25, F-26, F-27, F-28, F-29** plus the cross-cutting Q-14 / Q-15 mandate to build a real `captain_online_replay` driven by the live online B1–B6 modules and to source PG-09's `actual_trade_outcome(d)` from D03 realised P&L. It splits the work into 15 numbered batches (**7.0 through 7.14**).

This is the largest phase in the 12-phase campaign by scope. The first six batches (**7.0–7.5**) are infrastructure that must land in order; batches **7.6–7.11** apply the per-finding fixes against that infrastructure; batches **7.12–7.13** clean up the legacy replay engines; **7.14** is the verification suite that converts G-OFF-016's stale on-paper RESOLVED status into an in-fact-with-tests RESOLVED status.

## Spec authority chain (resolved at top of phase)

1. **Decisions log** — `phase-ref-docs/phase-2/captain_offline_audit_decisions_2026-04-27.md` §2 Group C, §3.2, §5 Phase 7
2. **Design doc** — `phase-ref-docs/phase-7/2026-04-27_phase7_design_captain_online_replay.md` (binding on this plan)
3. **Audit findings** — `2026-04-22_offline_spec_vs_code_audit copy.md` F-22…F-29
4. **Spec authority** — doc 32 PG-09 (L337–378), PG-10 (L385–413), PG-11 (L416–442), PG-13 (L498–541), Audit Resolutions (L794–795); doc 33 PG-21–PG-26
5. **Code** is overridden where (1)–(4) disagree

Where the design doc is silent, follow the audit. Where the audit is silent, follow the spec. Never invent a third option.

## Out-of-scope dependencies

| Item | Owner phase | Effect on Phase 7 |
|---|---|---|
| **Q-04** — `blend_signal` consumer for PG-11 transition | Phase 4 (or wherever Q-04 lands) | PG-10's ADOPT decision is consumed by PG-11. PG-11's blend wiring is not Phase 7 scope. **If Q-04 is unresolved when Phase 7 ships, PG-10 batches stay green** — PG-10 only writes the decision; PG-11's reader is a separate phase. |
| `b5_sensitivity.py` migration off `SignalReplayEngine` | Phase 12 hygiene | Phase 7 deprecates `SignalReplayEngine` to a warning stub but does not delete it; sensitivity caller continues to work via the stub. Phase 12 deletes the class. |

## Cross-cutting decisions baked in (from Stage 1B design approval)

| # | Decision | Source |
|---|---|---|
| D1 | `signal_id STRING` added to `p3_d03_trade_outcome_log` as Phase 1.5 amendment, executed as Batch 7.0. | Stage 1B §0, Q-15 |
| D2 | Headless function-shaped driver: `OnlineReplayContext` → `replay_session(...)` → `captain_online_replay(d, *, using=parameters)`. No daemon, no 1s loop. | Stage 1B §1 |
| D3 | `MarketDataProvider` protocol with `LiveMarketDataProvider` (default) + `HistoricalMarketDataProvider`. B1/b1_features accept provider as kwarg, `None` default routes to live. | Stage 1B §1 / §2 |
| D4 | Explicit `replay_reset()` hook list — closed at design time (5 hooks). New hooks added during implementation must amend the design doc, not silently extend in code. | Stage 1B §2.2 |
| D5 | `SignalSink` protocol; `CapturingSignalSink` for replay. CB-failure CRITICAL alert publishes also captured (no operator pages from replay). | Stage 1B §2.4 |
| D6 | Phase A → fast-forward OR-tracker bars to OR-close → Phase B inline. AIM-15 post-OR recompute included. | Stage 1B §0 / §8.6 |
| D7 | HMM state in replay = current D26 (limitation logged; Phase 10 introduces snapshots). | Stage 1B §0 / §8.7 |
| D8 | Single-user replay. PG-09/PG-10 run for the user whose strategy is changing; PG-13 is per-asset. | Stage 1B §0 / §8.8 |
| D9 | `SignalReplayEngine` reduced to deprecation stubs in Phase 7; class deleted in Phase 12. | Stage 1B §0 / §8.9 |
| D10 | `replay_engine.py` refactored in place. `run_replay`/`run_whatif` keep public API; internals delegate to `replay_session`. | Stage 1B §0 / §8.10 |
| D11 | `aim_retroactive_replay` is a standalone function in new `shared/aim_retroactive.py`; reuses `shared/aim_compute.py`. | Stage 1B §0 / §8.11 |
| D12 | Legacy D03 rows backfilled with `LEGACY-`-prefixed synthetic UUIDs in Batch 7.0 to keep backwards-window retests joinable. | Stage 1B §0 / §5.4 |

## Pass-2-level open questions (resolved per-batch, not at architecture level)

These items came out of Stage 1B with deliberate "decide during implementation" guidance. Each is pinned to its owning batch.

| # | Question | Owner batch | Default if unresolved |
|---|---|---|---|
| O1 | D11 / D06 column completeness — do `p3_d11_pseudotrader_results` / `p3_d06_injection_decisions` cover Sharpe-baseline / Sharpe-updated / DSR / per-day pair series? | 7.0 | Add missing columns alongside `signal_id`; flag in PR description. |
| O2 | Backfill UUID prefix for legacy D03 rows | 7.0 | `LEGACY-` per Stage 1B §5.4. |
| O3 | Bar table identity — confirm `p3_d29_session_bars` and `p3_d30_daily_ohlcv` are the right table names | 7.1 | Use whatever names the canonical_schemas + grep produce; if neither exists, surface a bar-storage gap to Nomaan as a Phase 7.5 follow-up. |
| O4 | D29 historical depth — is 252-day window achievable? | 7.1 | If insufficient, write a one-shot backfill script from TopstepX; flag if neither path works. |
| O5 | Other `replay_engine.run_replay` callers besides `b11_replay_runner.py`? | 7.12 | If callers exist, stage the refactor; otherwise refactor in place. |
| O6 | PG-13 rolling-fold parameters | 7.9 | Defaults: 5 expanding folds, equal-size validation slice. Document in PR; Isaac amendment can override. |
| O7 | `aim_retroactive_replay` historical feature loader — direct or via discarded `replay_session`? | 7.7 | Direct: load features from D29/D30/D31/D33 and call `shared/aim_compute.py`. If feature loader requires too much B1 plumbing to inline, fall back to `replay_session(...).discard(non_aim_outputs)`. |
| O8 | D03 `signal_id` index strategy | 7.0 | STRING column, lookup partition-scoped by `(user_id, entry_time)`; no secondary index. Add if perf shows up as a problem in 7.6 testing. |
| O9 | Live-parity baseline capture method (for the regression guard in 7.14) | 7.14 | Snapshot test: dry-run `_run_session(session_id=1)` against a sealed QuestDB fixture, capture published signals as JSON, store in `tests/fixtures/phase7_live_parity_baseline.json`. |

---

## Batch index

| Batch | Title | F-IDs / decisions | Status | Risk |
|---|---|---|---|---|
| **7.0** | Schema migration — `signal_id` in D03; D11 / D06 column verify; legacy backfill | D1, D12, Q-15 enabler | **GO** | LOW (additive column; backfill is one-shot script) |
| **7.1** | `MarketDataProvider` protocol + `LiveMarketDataProvider` + `HistoricalMarketDataProvider` | D3 (infra) | **GO** | LOW (additive; no live behavior change) |
| **7.2** | B1 + `b1_features` accept `MarketDataProvider` kwarg | D3 (infra wire-up) | **GO** | MEDIUM (touches the busiest module; live default preserves behavior) |
| **7.3** | `SignalSink` + `signal_id` flow B6 → Command → B7 → D03 | D5, D1 (writer side) | **GO** | MEDIUM (cross-process change; live default preserves behavior) |
| **7.4** | `OnlineReplayContext`, `replay_session`, `replay_reset`, B5C reset accessor | D2, D4 (infra) | **GO** | LOW (new module + one accessor refactor) |
| **7.5** | `actual_trade_outcome` helper + reader-side D03 `signal_id` lookup | Q-15, F-23 enabler | **GO** | LOW (read helper) |
| **7.6** | PG-09 rebuild — `captain_online_replay` Layer 3 wrapper, metric rebuild from D03 pairs, gate rewire | **F-22, F-23** | **GO** | MEDIUM-HIGH (largest single batch; central to phase) |
| **7.7** | `aim_retroactive_replay` + PG-10 Step 1 wire-up | **F-24** | **GO** | LOW (additive function + 20-line caller change) |
| **7.8** | PG-10 Step 3 — internal `pseudotrader_compare` via replay (drop precomputed branch) | **F-25** | **GO** | MEDIUM (changes `run_injection_comparison` data flow) |
| **7.9** | PG-13 walk-forward train + validate windows; DSR from holdout-OOS Sharpe | **F-28, F-29** | **GO** | MEDIUM |
| **7.10** | PG-13 candidate handoff to PG-10 — per-candidate `oos` series (drop identical-`holdout_returns` bug) | **F-26** | **GO** | LOW (caller-shape change; depends on 7.8) |
| **7.11** | PG-12 sensitivity — `compute_CSCV_PBO(results, S=8)` over full grid (Q-16 resolved-by-spec) | **F-27** | **GO** | LOW (single-line replacement + test) |
| **7.12** | `shared/replay_engine.py` refactor — delete parallel B-block logic; `run_replay`/`run_whatif` thin-wrap `replay_session` | D10 (infra cleanup) | **GO** | MEDIUM (~600 LOC delete; GUI replay is the consumer to verify) |
| **7.13** | `SignalReplayEngine` → deprecation stub | D9 (infra cleanup) | **GO** | LOW (callers migrated in 7.6 / 7.9; only `b5_sensitivity.py` still calls it via stub) |
| **7.14** | G-OFF-016 verification suite + live-parity regression guard | (verification) | **GO** | LOW (test-only) |

---

## Batch 7.0 — Schema migration: `signal_id` in D03; D11 / D06 column verify; legacy backfill

**Status:** GO

### Spec citation

- **Decisions log:** §2 Group C Q-15 (line 59 — strict realised P&L from D03); §5 Phase 7 row (line 256 — Phase 7 scope expansion).
- **Audit:** F-23 `2026-04-22_offline_spec_vs_code_audit copy.md` (PG-09 metrics must source realised P&L from D03 paired with originating signal).
- **Design doc:** §0 D1 / §5.2 (signal_id flow); §0 D12 (legacy backfill); Appendix B (schema impact).
- **Stage 1A audit pass:** §4.3 (no current D03 column ties row back to signal); §8.1 (largest open question — closed by D1).

### Pre-flight checks

1. Confirm Phase 1 schema migrations are merged on `main`. Phase 1 added `model_m INT` to D03 and `last_p1p2_rerun_ts` to D22 — those columns must exist before this batch lands.
2. Confirm `compact_questdb_tables.py` is the migration mechanism. Per memory observation 2838, `compact_questdb_tables.py` was rewritten to import canonical DDLs. Per memory observation 3007, no ALTER TABLE infrastructure exists; the supported pattern is "rebuild the table from canonical DDL via compaction". This batch follows that pattern.
3. Read `shared/canonical_schemas.py:398–427` to capture the current D03 DDL exactly. Read `shared/canonical_schemas.py:479…` to capture the current D11 DDL.
4. `grep -rn "p3_d03_trade_outcome_log" /home/nomaan/captain-system --include='*.py'` — enumerate every reader and writer site that may need `signal_id` column awareness in subsequent batches. Cross-check against Stage 1A §4.1–§4.2.
5. Run baseline tests: `PYTHONPATH=./:./captain-online:./captain-offline:./captain-command python3 -B -m pytest tests/ --ignore=tests/test_integration_e2e.py --ignore=tests/test_pipeline_e2e.py --ignore=tests/test_pseudotrader_account.py --ignore=tests/test_offline_feedback.py --ignore=tests/test_stress.py --ignore=tests/test_account_lifecycle.py -v` — must be green.

### Files + line ranges to modify

| File | Lines | Change |
|---|---|---|
| `shared/canonical_schemas.py` | 398–427 (D03 DDL) | Add `signal_id STRING` column |
| `shared/canonical_schemas.py` | 479–~510 (D11 DDL) | If missing: add `sharpe_baseline DOUBLE`, `sharpe_updated DOUBLE`, `pbo DOUBLE`, `dsr DOUBLE`, `recommendation STRING`, `pair_series STRING` (JSON); verify per O1 |
| `shared/canonical_schemas.py` | (D06 DDL location) | Verify columns: `expected_new`, `expected_current`, `recommendation`, `pbo`, `dsr`, `transition_days`, `tracking_days`. Add any missing |
| `scripts/compact_questdb_tables.py` | (whole file) | Re-run after canonical_schemas.py edits — idempotent rebuild |
| `scripts/backfill_d03_signal_ids.py` | NEW | One-shot backfill: `UPDATE p3_d03_trade_outcome_log SET signal_id = 'LEGACY-' \|\| concat(uuid()) WHERE signal_id IS NULL` (or QuestDB-flavored equivalent — likely SELECT-and-INSERT into a new partition since QuestDB UPDATEs are limited) |
| `tests/test_schema_d03_signal_id.py` | NEW | Schema test (column exists, type STRING, nullable) + backfill test (legacy rows get LEGACY- prefix) |

### Exact change shape

**`shared/canonical_schemas.py` D03 DDL (BEFORE → AFTER):**

```python
# BEFORE (L398–427, current 23 columns)
"""
CREATE TABLE IF NOT EXISTS p3_d03_trade_outcome_log (
    trade_id STRING,
    user_id SYMBOL,
    account_id SYMBOL,
    asset SYMBOL,
    direction INT,
    entry_price DOUBLE,
    signal_entry_price DOUBLE,
    exit_price DOUBLE,
    contracts INT,
    gross_pnl DOUBLE,
    commission DOUBLE,
    pnl DOUBLE,
    slippage DOUBLE,
    outcome STRING,
    entry_time TIMESTAMP,
    exit_time TIMESTAMP,
    regime_at_entry STRING,
    aim_modifier_at_entry DOUBLE,
    aim_breakdown_at_entry STRING,
    session INT,
    tsm_used STRING,
    model_m INT,
    ts TIMESTAMP
) timestamp(ts) PARTITION BY DAY WAL DEDUP UPSERT KEYS (ts);
"""

# AFTER (24 columns — added signal_id)
"""
CREATE TABLE IF NOT EXISTS p3_d03_trade_outcome_log (
    trade_id STRING,
    signal_id STRING,                  -- NEW Phase 7 — links D03 row to originating signal (PG-09 pair)
    user_id SYMBOL,
    account_id SYMBOL,
    asset SYMBOL,
    direction INT,
    entry_price DOUBLE,
    signal_entry_price DOUBLE,
    exit_price DOUBLE,
    contracts INT,
    gross_pnl DOUBLE,
    commission DOUBLE,
    pnl DOUBLE,
    slippage DOUBLE,
    outcome STRING,
    entry_time TIMESTAMP,
    exit_time TIMESTAMP,
    regime_at_entry STRING,
    aim_modifier_at_entry DOUBLE,
    aim_breakdown_at_entry STRING,
    session INT,
    tsm_used STRING,
    model_m INT,
    ts TIMESTAMP
) timestamp(ts) PARTITION BY DAY WAL DEDUP UPSERT KEYS (ts);
"""
```

**`scripts/backfill_d03_signal_ids.py` (NEW; sketch):**

```python
"""One-shot backfill — assign LEGACY- UUIDs to D03 rows missing signal_id.

QuestDB UPDATEs on partitioned tables are restricted; use INSERT-into-new + DROP
pattern via compact_questdb_tables.py if needed. For this batch, prefer the
simpler approach: query rows with NULL signal_id, generate IDs in Python,
re-insert with the same ts (DEDUP UPSERT KEYS makes this idempotent).
"""
import uuid
from shared.questdb_client import get_cursor

def main():
    with get_cursor() as cur:
        cur.execute("SELECT * FROM p3_d03_trade_outcome_log WHERE signal_id IS NULL")
        rows = cur.fetchall()
        for row in rows:
            new_id = f"LEGACY-{uuid.uuid4()}"
            # Re-INSERT with all columns including signal_id; DEDUP UPSERT on ts
            # carries forward the row. Idempotent.
            ...

if __name__ == "__main__":
    main()
```

### Test additions

**`tests/test_schema_d03_signal_id.py` (NEW):**

| Test | Assertion |
|---|---|
| `test_d03_has_signal_id_column` | Query `pragma_table_info` (or QuestDB equivalent) — `signal_id` exists, type `STRING`, nullable. |
| `test_d03_canonical_schema_includes_signal_id` | `import shared.canonical_schemas` — DDL string contains `signal_id STRING`. |
| `test_legacy_backfill_assigns_legacy_prefix` | Seed 5 rows with NULL signal_id, run backfill script, assert all 5 rows have `signal_id LIKE 'LEGACY-%'` and the UUID portion is unique. |
| `test_d11_columns_complete` | Per O1, assert columns enumerated above exist. |
| `test_d06_columns_complete` | Per O1 + Stage 1B Appendix B — assert columns enumerated above exist. |

### Exit criteria

- All schema tests pass.
- Baseline test suite (per Pre-flight 5) still green.
- `compact_questdb_tables.py` runs to completion against a fresh QuestDB instance and produces the new schema.
- Backfill script tested against a fixture with mixed NULL / non-NULL `signal_id` rows.
- D11 and D06 column gaps (O1) either filled by this batch or explicitly flagged in PR description.

### Rollback procedure

1. Revert the canonical_schemas.py edit (`git revert <commit>`).
2. Re-run `compact_questdb_tables.py` — produces the prior 23-column D03 schema.
3. Backfilled `LEGACY-` rows are harmless (column doesn't exist in reverted schema, data discarded by compaction).
4. No data loss: D03 realised P&L rows retain `pnl`, `gross_pnl`, etc.

---

## Batch 7.1 — `MarketDataProvider` protocol + Live + Historical implementations

**Status:** GO

### Spec citation

- **Design doc:** §1 (architecture); §2.1 (public API); §2.3 (bar/quote substitution); §3.2 (read surface).
- **Decisions log:** Q-14 (build replay against real online B1–B6).

### Pre-flight checks

1. Batch 7.0 merged.
2. `grep -rn "topstep_client.get_bars\|quote_cache\[" /home/nomaan/captain-system/captain-online --include='*.py'` — enumerate every B1 / b1_features call site that needs to be routed through the provider in 7.2.
3. Confirm bar tables exist (O3): `grep -n "p3_d29\|p3_d30\|p3_d31\|p3_d33" /home/nomaan/captain-system/shared/canonical_schemas.py`. If a referenced table doesn't exist, surface to Nomaan and resolve before proceeding.
4. Confirm `bar_cache.py` is reusable as-is (Stage 1A §5.3) — no audit findings; pure infrastructure.

### Files + line ranges to modify

| File | Lines | Change |
|---|---|---|
| `shared/online_replay.py` | NEW | Define `MarketDataProvider`, `SignalSink`, `TimeProvider` protocols (Layer 1 stubs only — full driver is 7.4) |
| `shared/online_replay_providers.py` | NEW | `LiveMarketDataProvider`, `HistoricalMarketDataProvider`, `RedisSignalPublisher`, `CapturingSignalSink`, `LiveTimeProvider`, `FixedTimeProvider` |
| `tests/test_online_replay_providers.py` | NEW | Unit tests for both providers (live wraps existing infra; historical reads QuestDB fixtures) |

### Exact change shape

**`shared/online_replay.py` (NEW; protocols only):**

```python
"""Phase 7 — captain_online_replay infrastructure.

Layer 1 (this file): protocols + dataclasses.
Layer 2 (this file in 7.4): replay_session, replay_reset.
Layer 3 (this file in 7.4): captain_online_replay.

Live B1-B6 modules are unchanged semantically; they accept these protocol
instances as kwargs and default to None (live path).
"""
from datetime import datetime
from typing import Protocol, Any, Callable
from dataclasses import dataclass, field


class MarketDataProvider(Protocol):
    """Substitution seam for B1's external market data reads.
    
    Live impl wraps shared.topstep_client + topstep_stream.quote_cache.
    Historical impl reads from QuestDB historical bar storage.
    """
    def get_bars(
        self, asset_id: str, timeframe: str, start: datetime, end: datetime
    ) -> list[dict]: ...

    def get_current_quote(self, asset_id: str) -> dict | None: ...

    def get_current_session_volume(self, asset_id: str) -> int | None: ...

    def get_avg_session_volume_20d(self, asset_id: str) -> float | None: ...

    def get_prior_close(self, asset_id: str) -> float | None: ...

    def get_intraday_bars(self, asset_id: str, lookback_minutes: int) -> list[dict]: ...

    def get_historical_session_volumes(self, asset_id: str, n_sessions: int) -> list[int]: ...

    def get_daily_closes(self, asset_id: str, n_days: int) -> list[float]: ...


class SignalSink(Protocol):
    """Substitution seam for B6's Redis signal publish."""
    def publish(self, channel: str, payload: dict) -> bool: ...
    def captured(self) -> list[dict]: ...


class TimeProvider(Protocol):
    """Substitution seam for now_et() in B1/B6/orchestrator."""
    def now_et(self) -> datetime: ...
```

**`shared/online_replay_providers.py` (NEW; concrete impls):**

```python
"""Phase 7 — concrete provider implementations.

Split from online_replay.py so live and historical impls don't import each other.
"""
from datetime import datetime, date
from zoneinfo import ZoneInfo
from typing import Any
from shared.online_replay import MarketDataProvider, SignalSink, TimeProvider


_ET = ZoneInfo("America/New_York")


class LiveMarketDataProvider:
    """Default provider — wraps existing shared.topstep_client + quote_cache."""
    def get_bars(self, asset_id, timeframe, start, end):
        from shared.topstep_client import get_topstep_client
        client = get_topstep_client()
        return client.get_bars(asset_id, timeframe, start, end)

    def get_current_quote(self, asset_id):
        from shared.topstep_stream import quote_cache
        return quote_cache.get(asset_id)

    # … etc, one method per protocol member, each thin-wrapping current call sites.


class HistoricalMarketDataProvider:
    """Replay provider — reads from QuestDB historical bar storage.
    
    Caches bars within a session via shared/bar_cache.py to avoid repeated reads.
    """
    def __init__(self, as_of: datetime, *, bar_cache=None):
        self._as_of = as_of  # FixedTimeProvider's value at session-open
        from shared.bar_cache import get_cached_bars, cache_bars
        self._get_cached = get_cached_bars
        self._cache = cache_bars

    def get_bars(self, asset_id, timeframe, start, end):
        # QuestDB query against p3_d29_session_bars (1m) or p3_d30_daily_ohlcv (1d).
        # Bar table identity per O3 (verified in 7.0 pre-flight).
        ...

    def get_current_quote(self, asset_id):
        # Synthesize from most recent 1-min bar before self._as_of.
        bars = self.get_bars(asset_id, "1m", self._as_of.replace(hour=0, minute=0), self._as_of)
        if not bars:
            return None
        last = bars[-1]
        return {
            "bid": last["open"], "ask": last["open"],
            "bid_size": 1, "ask_size": 1, "ts": last["ts"],
        }

    # … etc


class RedisSignalPublisher:
    """Default sink — publishes to live Redis STREAM_SIGNALS."""
    def __init__(self):
        self._captured = []

    def publish(self, channel, payload):
        from shared.redis_client import get_redis
        get_redis().xadd(channel, payload)
        return True

    def captured(self):
        return []  # live publisher does not capture


class CapturingSignalSink:
    """Replay sink — captures signals to a list, never publishes."""
    def __init__(self):
        self._captured = []

    def publish(self, channel, payload):
        self._captured.append({"channel": channel, "payload": payload})
        return True

    def captured(self):
        return [c["payload"] for c in self._captured]


class LiveTimeProvider:
    def now_et(self):
        return datetime.now(_ET)


class FixedTimeProvider:
    """Replay time — returns a fixed timestamp (advanceable for Phase B)."""
    def __init__(self, fixed: datetime):
        self._t = fixed if fixed.tzinfo else fixed.replace(tzinfo=_ET)

    def now_et(self):
        return self._t

    def advance(self, seconds: int):
        from datetime import timedelta
        self._t = self._t + timedelta(seconds=seconds)
```

### Test additions

**`tests/test_online_replay_providers.py` (NEW):**

| Test | Assertion |
|---|---|
| `test_live_provider_wraps_topstep_client` | Patch `shared.topstep_client.get_topstep_client`; call `LiveMarketDataProvider().get_bars(...)`; assert wrapped client was called with same args. |
| `test_historical_provider_reads_d29` | Seed `p3_d29_session_bars` fixture with 100 1-min bars; call `HistoricalMarketDataProvider(as_of=...).get_bars(...)`; assert returned bars match seeded rows in order. |
| `test_historical_quote_synthesis` | Seed bars; call `get_current_quote(asset_id)`; assert returned quote has `bid == ask == last_bar.open`. |
| `test_capturing_signal_sink_collects_publishes` | Instantiate `CapturingSignalSink`; call `publish` 3 times; assert `captured()` returns 3 payloads in order. |
| `test_redis_publisher_does_not_capture` | Mock Redis; assert `RedisSignalPublisher().captured()` returns `[]` regardless of publishes. |
| `test_fixed_time_provider_advance` | `FixedTimeProvider(t).advance(60)` returns time `t + 60s` from `now_et()`. |
| `test_provider_isolation_guarantee` | Pass `HistoricalMarketDataProvider` to `LiveMarketDataProvider`'s slot in a faked context — runtime should `RuntimeError` (Stage 1B §1.2 invariant 2). |

### Exit criteria

- All provider tests pass.
- Baseline test suite still green (no live behavior touched yet — providers exist but aren't wired).
- `b11_replay_runner.py` still passes its existing tests (it doesn't import these protocols yet).

### Rollback procedure

1. Delete `shared/online_replay.py`, `shared/online_replay_providers.py`, `tests/test_online_replay_providers.py`.
2. No production code change to revert; live path untouched.

---

## Batch 7.2 — B1 + `b1_features` accept `MarketDataProvider`

**Status:** GO

### Spec citation

- **Design doc:** §1.3 (file impact); §3.2 (read surface enumeration).
- **Decisions log:** Q-14.

### Pre-flight checks

1. Batches 7.0–7.1 merged.
2. Re-run the 7.1 pre-flight grep to confirm the call-site list is current. Cross-check against Stage 1A B1 / b1_features mapping.
3. Read each B1 / b1_features I/O site to understand the exact arguments passed (so the routed call preserves them).

### Files + line ranges to modify

| File | Lines | Change |
|---|---|---|
| `captain-online/captain_online/blocks/b1_data_ingestion.py` | 778 (`run_data_ingestion` signature) | Add `market_data: MarketDataProvider \| None = None` kwarg |
| `captain-online/captain_online/blocks/b1_data_ingestion.py` | 526–602 (`_get_latest_price`, `_get_prior_close`, `_get_current_session_volume`, `_get_avg_session_volume_20d`) | Route through `market_data` when provided; default falls through to current behavior |
| `captain-online/captain_online/blocks/b1_data_ingestion.py` | 357–383 (`_prefetch_market_data`) | Accept and forward `market_data` |
| `captain-online/captain_online/blocks/b1_features.py` | 556 (`compute_all_features` signature) | Add `market_data: MarketDataProvider \| None = None` kwarg |
| `captain-online/captain_online/blocks/b1_features.py` | 1212–1251 (`_get_intraday_bars`, `_get_historical_volume_first_N_min`) | Route through `market_data` when provided |
| `captain-online/captain_online/blocks/b1_features.py` | 1103–1128 (`_get_daily_closes`) | Route through `market_data` |
| `captain-online/captain_online/blocks/b1_features.py` | 1483–1525 (`_get_recent_5min_vol`) | Route through `market_data` |
| `captain-online/captain_online/blocks/orchestrator.py` | 244–384 (`_run_session`) | No change — calls `run_data_ingestion(session_id)` with no `market_data`, default-None routes to live. **Verify byte-identical baseline** in 7.14. |
| `tests/test_b1_provider_routing.py` | NEW | Tests that B1 routes through provider when supplied; falls back to live behavior when None |

### Exact change shape

**`b1_data_ingestion.py:778` signature change:**

```python
# BEFORE
def run_data_ingestion(session_id: int) -> dict | None:
    """B1 entry — returns dict or None if no active assets."""
    ...

# AFTER
def run_data_ingestion(
    session_id: int,
    *,
    market_data: "MarketDataProvider | None" = None,
) -> dict | None:
    """B1 entry — returns dict or None if no active assets.
    
    Phase 7: when market_data is supplied, all bar/quote/volume reads route
    through it. Default None preserves the live path (LiveMarketDataProvider
    semantics implemented inline via topstep_client + quote_cache).
    """
    if market_data is None:
        # Lazy-import to avoid coupling production B1 to the protocol module.
        from shared.online_replay_providers import LiveMarketDataProvider
        market_data = LiveMarketDataProvider()
    ...  # unchanged below; pass market_data into helpers
```

**Helper rewrite pattern (`_get_latest_price`):**

```python
# BEFORE (L526)
def _get_latest_price(asset_id: str) -> float | None:
    from shared.topstep_stream import quote_cache
    quote = quote_cache.get(asset_id)
    if quote and "bid" in quote and "ask" in quote:
        return (quote["bid"] + quote["ask"]) / 2.0
    # … existing fallback to topstep_client.get_bars

# AFTER
def _get_latest_price(asset_id: str, *, market_data) -> float | None:
    quote = market_data.get_current_quote(asset_id)
    if quote and "bid" in quote and "ask" in quote:
        return (quote["bid"] + quote["ask"]) / 2.0
    # Bars fallback — also via provider
    bars = market_data.get_bars(asset_id, "1m", ..., ...)
    ...
```

Repeat the pattern for every helper enumerated above. Caller sites within `run_data_ingestion` thread `market_data` through.

### Test additions

**`tests/test_b1_provider_routing.py` (NEW):**

| Test | Assertion |
|---|---|
| `test_b1_default_uses_live_provider` | Patch `LiveMarketDataProvider`; call `run_data_ingestion(1)`; assert provider was instantiated and methods called. |
| `test_b1_uses_supplied_provider` | Pass a `Mock(spec=MarketDataProvider)`; call `run_data_ingestion(1, market_data=mock)`; assert mock methods called and live provider was NOT instantiated. |
| `test_b1_returns_identical_output_with_live_default` | Capture `run_data_ingestion(1)` output before Phase 7 (sealed fixture); call again post-Phase-7; assert byte-identical (live-parity invariant). |
| `test_b1_features_routes_intraday_bars_through_provider` | Mock provider; call `compute_all_features(...)`; assert provider's `get_intraday_bars` was called instead of `_get_intraday_bars`'s old TopstepX path. |

### Exit criteria

- All B1 provider tests pass.
- Baseline test suite green; **live-parity invariant** verified (B1 with default `None` produces same output as before Phase 7).
- No new TopstepX or QuestDB calls introduced; existing calls just routed through the provider.

### Rollback procedure

1. `git revert <commit>` — restores B1 / b1_features signatures to no-kwarg form.
2. Live path unaffected; replay infrastructure remains in shared/ but is unwired.

---

## Batch 7.3 — `SignalSink` + `signal_id` flow B6 → Command → B7 → D03

**Status:** GO

### Spec citation

- **Decisions log:** Q-15 (realised P&L paired with originating signal).
- **Audit:** F-23.
- **Design doc:** §5.2 (signal_id flow); D5 (SignalSink); §1.3 (file impact list).

### Pre-flight checks

1. Batches 7.0–7.2 merged.
2. `grep -n "signal_id" /home/nomaan/captain-system/captain-online/captain_online/blocks/b6_signal_output.py` — confirm B6 already generates UUIDs (Stage 1A: L84). If `signal_id` already exists in payloads, the change is consumer-side propagation only.
3. `grep -n "open_positions\|_handle_taken_skipped" /home/nomaan/captain-system/captain-command --include='*.py'` — locate the command-side persistence site.
4. Read `b7_position_monitor.py:303–316` (`_write_trade_outcome`) to confirm the position dict shape.

### Files + line ranges to modify

| File | Lines | Change |
|---|---|---|
| `captain-online/captain_online/blocks/b6_signal_output.py` | 39 (`run_signal_output` signature) | Add `signal_sink: SignalSink \| None = None` kwarg |
| `captain-online/captain_online/blocks/b6_signal_output.py` | 84 (signal envelope build) | Confirm `signal_id` UUID is included in payload (likely already present); pin in test |
| `captain-online/captain_online/blocks/b6_signal_output.py` | 332–360 (`_publish_signals`) | Route through `signal_sink` when provided; default → existing Redis publish |
| `captain-online/captain_online/blocks/b6_signal_output.py` | 180–193 (CRITICAL alert publish) | Same pattern — route through signal_sink |
| `captain-command/captain_command/blocks/b1_core_routing.py` | (TAKEN handler — exact line per pre-flight grep) | Persist `signal_id` from envelope into `open_positions[account_id]` dict |
| `captain-online/captain_online/blocks/orchestrator.py` | 872–920 (`_handle_taken_skipped`) | Persist `signal_id` from incoming envelope into the in-memory position dict |
| `captain-online/captain_online/blocks/b7_position_monitor.py` | 303–316 (`_write_trade_outcome`) | Read `signal_id` from position dict; include in D03 INSERT |
| `scripts/paper_trader.py` | 393–404 (`_log_trade_open`), 416–433 (`_log_trade_close`) | Generate UUID at open if signal source doesn't supply one; persist on close |
| `shared/trade_source.py` | 295–314 (`seed_d03_from_synthetic`) | Generate UUID per row; or accept caller-supplied IDs |
| `tests/test_signal_id_flow.py` | NEW | End-to-end: B6 generates → Command persists → B7 writes; verify D03 row has signal_id |

### Exact change shape

**`b6_signal_output.py:39` signature change:**

```python
# BEFORE
def run_signal_output(recommended_trades, available_not_recommended, ...) -> dict:

# AFTER  
def run_signal_output(
    recommended_trades, available_not_recommended, ...,
    *, signal_sink: "SignalSink | None" = None,
) -> dict:
    if signal_sink is None:
        from shared.online_replay_providers import RedisSignalPublisher
        signal_sink = RedisSignalPublisher()
    ...
```

**`b6_signal_output.py:332` `_publish_signals` rewrite:**

```python
# BEFORE
def _publish_signals(signals: list[dict]) -> bool:
    """Publish to Redis STREAM_SIGNALS with retry."""
    from shared.redis_client import get_redis
    redis = get_redis()
    for signal in signals:
        for attempt in range(3):
            try:
                redis.xadd(STREAM_SIGNALS, signal)
                break
            except Exception:
                ...

# AFTER
def _publish_signals(signals: list[dict], *, signal_sink) -> bool:
    """Publish via signal_sink with retry. Live default = RedisSignalPublisher."""
    for signal in signals:
        for attempt in range(3):
            try:
                signal_sink.publish(STREAM_SIGNALS, signal)
                break
            except Exception:
                ...
```

**`b7_position_monitor.py:303–316` `_write_trade_outcome` rewrite:**

```python
# BEFORE
def _write_trade_outcome(self, position: dict, exit_price: float, exit_time: datetime):
    cursor = ...
    cursor.execute(
        "INSERT INTO p3_d03_trade_outcome_log "
        "(trade_id, user_id, account_id, asset, direction, entry_price, "
        " signal_entry_price, exit_price, contracts, gross_pnl, commission, "
        " pnl, slippage, outcome, entry_time, exit_time, regime_at_entry, "
        " aim_modifier_at_entry, aim_breakdown_at_entry, session, tsm_used, "
        " model_m, ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
        "?, ?, ?, ?, ?, ?, ?, ?)",
        (position["trade_id"], position["user_id"], ..., model_m, now_et()),
    )

# AFTER
def _write_trade_outcome(self, position: dict, exit_price: float, exit_time: datetime):
    cursor = ...
    signal_id = position.get("signal_id") or f"LEGACY-{uuid.uuid4()}"  # belt-and-braces
    cursor.execute(
        "INSERT INTO p3_d03_trade_outcome_log "
        "(trade_id, signal_id, user_id, account_id, asset, direction, ...) "
        "VALUES (?, ?, ?, ?, ?, ?, ...)",
        (position["trade_id"], signal_id, position["user_id"], ...),
    )
```

### Test additions

**`tests/test_signal_id_flow.py` (NEW):**

| Test | Assertion |
|---|---|
| `test_b6_includes_signal_id_in_payload` | Run `run_signal_output(...)` with mocked sink; assert each captured payload has `signal_id` matching UUID v4 format. |
| `test_command_persists_signal_id` | Simulate TAKEN message arriving; assert `open_positions[acct]["signal_id"]` matches incoming `signal_id`. |
| `test_b7_writes_signal_id_to_d03` | Seed open position with known signal_id; trigger TP; assert D03 row contains exact signal_id. |
| `test_b7_falls_back_to_legacy_id_when_missing` | Seed position without signal_id (legacy); trigger TP; assert D03 row has `LEGACY-<uuid>`. |
| `test_b6_default_uses_redis_publisher` | Patch `RedisSignalPublisher`; call `run_signal_output(...)` without sink; assert Redis publish was invoked. |
| `test_b6_supplied_sink_intercepts_publish` | Pass `CapturingSignalSink`; assert no Redis call; assert sink.captured() has the signals. |
| `test_paper_trader_generates_signal_id` | Run paper_trader through one open/close; assert D03 row has signal_id. |
| `test_e2e_signal_id_flow` | Full pipeline: B6 → command → B7 → D03; round-trip a signal_id and assert it appears in D03. |

### Exit criteria

- All signal-id flow tests pass.
- Baseline test suite green.
- Live B6 publish unchanged when sink defaults to None.

### Rollback procedure

1. `git revert <commit>` — restores B6 / Command / B7 to no-signal_id wiring.
2. D03 column remains (Batch 7.0 owns the schema). Rows already written with signal_id are harmless under the reverted writer.

---

## Batch 7.4 — `OnlineReplayContext`, `replay_session`, `replay_reset`, B5C reset accessor

**Status:** GO

### Spec citation

- **Design doc:** §1.1 (3-layer architecture); §1.2 (isolation invariants); §2.1 (driver public API); §2.2 (reset hooks).
- **Decisions log:** Q-14.

### Pre-flight checks

1. Batches 7.0–7.3 merged.
2. Read `b5c_circuit_breaker.py:2017` to capture the `_seen` set definition; confirm no other module mutates it.
3. `grep -rn "lru_cache\|@cache\|_cache\b" /home/nomaan/captain-system/shared/aim_compute.py` — enumerate any hidden caches that need reset hooks.
4. `grep -n "_session_evaluated_today\|_pending_sessions" /home/nomaan/captain-system/captain-online/captain_online/blocks/orchestrator.py` — confirm orchestrator-level state to reset.

### Files + line ranges to modify

| File | Lines | Change |
|---|---|---|
| `shared/online_replay.py` | (existing from 7.1) | Add `OnlineReplayContext` dataclass, `ReplayParameters`, `ReplayResult`, `replay_session`, `replay_reset`, `captain_online_replay` |
| `captain-online/captain_online/blocks/b5c_circuit_breaker.py` | ~2017 (`_seen` set) | Wrap in module-level `_get_seen()` accessor and `_reset_seen()` cleaner; existing call sites use accessor |
| `tests/test_replay_session.py` | NEW | Driver tests: round-trip B1→B6 with synthetic context; reset hooks invoked; isolation invariants |

### Exact change shape

**`shared/online_replay.py` driver section (extends 7.1's protocols-only file):**

```python
# … existing protocols from 7.1 …

@dataclass
class ReplayParameters:
    locked_strategies: dict[str, dict] | None = None
    aim_states: dict | None = None
    aim_weights: dict | None = None
    kelly_params: dict | None = None
    ewma_states: dict | None = None
    sizing_overrides: dict[str, float] | None = None


@dataclass
class ReplayResult:
    session_date: date
    session_id: int
    signals: list[dict]
    phase_a_outputs: dict
    phase_b_outputs: dict
    diagnostics: dict


@dataclass
class OnlineReplayContext:
    market_data: MarketDataProvider
    signal_sink: SignalSink
    time_provider: TimeProvider
    reset_hooks: list[Callable[[], None]] = field(default_factory=list)
    parameter_overrides: dict[str, Any] = field(default_factory=dict)

    def __enter__(self) -> "OnlineReplayContext":
        replay_reset(self.reset_hooks)
        return self

    def __exit__(self, *exc) -> None:
        replay_reset(self.reset_hooks)


def replay_reset(reset_hooks: list[Callable[[], None]]) -> None:
    """Invoke each reset hook. Safe to call repeatedly. Order = registration order."""
    for hook in reset_hooks:
        hook()


# Default hook list — closed at design time per Stage 1B §2.2 D4.
def default_reset_hooks() -> list[Callable[[], None]]:
    from captain_online.blocks.b5c_circuit_breaker import _reset_seen
    # … additional hooks per design doc §2.2:
    # _reset_aim_compute_caches, _reset_b1_prefetch_executor,
    # _reset_orchestrator_session_state, _reset_quote_cache_snapshot
    return [_reset_seen, ...]


def replay_session(
    session_date: date,
    session_id: int,
    ctx: OnlineReplayContext,
    parameters: ReplayParameters | None = None,
) -> ReplayResult:
    """Execute B1 → B6 chain for one session day under ctx.
    
    Phase A (B1-B5C) runs once; Phase B (B6) inlines the OR-tracker fast-forward
    and AIM-15 recompute per design doc §0 D6.
    """
    from captain_online.blocks.b1_data_ingestion import run_data_ingestion
    from captain_online.blocks.b2_regime_probability import run_regime_probability
    from shared.aim_compute import run_aim_aggregation
    from captain_online.blocks.b4_kelly_sizing import run_kelly_sizing
    from captain_online.blocks.b5_trade_selection import run_trade_selection
    from captain_online.blocks.b5b_quality_gate import run_quality_gate
    from captain_online.blocks.b5c_circuit_breaker import run_circuit_breaker_screen
    from captain_online.blocks.b6_signal_output import run_signal_output

    with ctx:
        # Phase A
        b1 = run_data_ingestion(session_id, market_data=ctx.market_data)
        if b1 is None:
            return ReplayResult(session_date, session_id, [], {}, {}, {"reason": "no_active_assets"})
        if parameters is not None:
            b1 = _apply_overrides(b1, parameters)
        b2 = run_regime_probability(b1["active_assets"], b1["features"], b1["regime_models"])
        b3 = run_aim_aggregation(b1["active_assets"], b1["features"],
                                 b1["aim_states"], b1["aim_weights"])
        # Per-user (single-user per design D8)
        user_id = _resolve_replay_user_id(ctx)
        b4 = run_kelly_sizing(b1["active_assets"], b2["regime_probs"], b2["regime_uncertain"],
                              b3["combined_modifier"], b1["kelly_params"], b1["ewma_states"],
                              b1["tsm_configs"], b1["sizing_overrides"], _user_silo(user_id),
                              b1["locked_strategies"], b1["assets_detail"], session_id)
        b5 = run_trade_selection(b1["active_assets"], b4["final_contracts"],
                                 b4["account_recommendation"], b4["account_skip_reason"],
                                 b1["ewma_states"], b2["regime_probs"], _user_silo(user_id), session_id)
        b5b = run_quality_gate(b5["selected_trades"], b5["expected_edge"],
                               b3["combined_modifier"], b2["regime_probs"], _user_silo(user_id),
                               session_id, b5["final_contracts"])
        b5c = run_circuit_breaker_screen(b5b["recommended_trades"], b5["final_contracts"],
                                         b4["account_recommendation"], b4["account_skip_reason"],
                                         _accounts(user_id), b1["tsm_configs"], session_id)
        # Phase B — fast-forward OR-tracker bars; AIM-15 recompute; B6
        # (Implementation per design D6 — uses ctx.market_data.get_bars to walk the OR window.)
        b6 = run_signal_output(b5c["recommended_trades"], b5["expected_edge"],
                               # … other args
                               signal_sink=ctx.signal_sink)

    return ReplayResult(
        session_date=session_date,
        session_id=session_id,
        signals=ctx.signal_sink.captured(),
        phase_a_outputs={"b1": b1, "b2": b2, "b3": b3, "b4": b4, "b5": b5, "b5b": b5b, "b5c": b5c},
        phase_b_outputs={"b6": b6},
        diagnostics={"reset_hooks_invoked": len(ctx.reset_hooks)},
    )


def captain_online_replay(
    d: date,
    *,
    using: ReplayParameters,
    user_id: str,
    asset: str | None = None,
    session_id: int | None = None,
) -> list[dict]:
    """Doc 32 PG-09 spec entry. Returns signals for session day d under `using` params."""
    from shared.online_replay_providers import (
        HistoricalMarketDataProvider, CapturingSignalSink, FixedTimeProvider,
    )
    session_id = session_id or _infer_session_id(asset, d)
    session_open = _session_open_dt(d, session_id)
    ctx = OnlineReplayContext(
        market_data=HistoricalMarketDataProvider(as_of=session_open),
        signal_sink=CapturingSignalSink(),
        time_provider=FixedTimeProvider(session_open),
        reset_hooks=default_reset_hooks(),
        parameter_overrides={},
    )
    result = replay_session(d, session_id, ctx, using)
    return result.signals
```

**`b5c_circuit_breaker.py:~2017` accessor wrap:**

```python
# BEFORE
_seen = set()  # module-level dedup set tracking D23 writes

# AFTER
_seen: set = set()


def _get_seen() -> set:
    """Module accessor — replay reset hooks clear via _reset_seen."""
    return _seen


def _reset_seen() -> None:
    """Reset hook — invoked by replay_reset() at session start."""
    _seen.clear()
```

All existing references to `_seen` within `b5c_circuit_breaker.py` change to `_get_seen()`.

### Test additions

**`tests/test_replay_session.py` (NEW):**

| Test | Assertion |
|---|---|
| `test_replay_session_invokes_live_b1` | Spy on `run_data_ingestion`; call `replay_session(...)`; assert spy called with `market_data=` set. |
| `test_replay_session_invokes_live_b6` | Spy on `run_signal_output`; assert called with `signal_sink=` set. |
| `test_replay_session_chains_b1_to_b6` | Mock all live blocks; call `replay_session(...)`; assert call order B1→B2→B3→B4→B5→B5B→B5C→B6. |
| `test_replay_session_applies_parameter_overrides` | Pass `ReplayParameters(aim_weights={'AIM-01': 0.5})`; assert B3 received `aim_weights['AIM-01'] == 0.5` not the live D02 value. |
| `test_replay_reset_clears_b5c_seen` | Add fake entries to `_get_seen()`; invoke `replay_reset(default_reset_hooks())`; assert `_get_seen()` empty. |
| `test_replay_context_resets_on_enter_and_exit` | `with OnlineReplayContext(...)` — verify reset hooks called twice (entry, exit). |
| `test_captain_online_replay_returns_signal_list` | Stub HistoricalMarketDataProvider with seeded bars; call `captain_online_replay(date(2026,1,15), using=...)`; assert returns `list[dict]`. |
| `test_replay_does_not_touch_redis` | Mock Redis at module level; run `replay_session`; assert no Redis call. |
| `test_replay_does_not_mutate_live_quote_cache` | Pre-populate live `quote_cache`; run replay; assert quote_cache unchanged. |
| `test_replay_resets_seen_between_sessions` | Run two `replay_session` calls in sequence; assert `_get_seen()` reset between them. |

### Exit criteria

- All driver tests pass.
- Baseline test suite green; live `_run_session` byte-identical.
- `_get_seen()` accessor adopted at every previous `_seen` reference site within `b5c_circuit_breaker.py`.

### Rollback procedure

1. `git revert <commit>` — removes driver, restores `_seen` direct access.
2. Provider/sink/time-provider modules from earlier batches stay; they're benign without the driver.

---

## Batch 7.5 — `actual_trade_outcome` helper + reader-side D03 `signal_id` lookup

**Status:** GO

### Spec citation

- **Decisions log:** Q-15 (line 59).
- **Audit:** F-23.
- **Spec authority:** doc 32 PG-09 line 357 (`outcome = actual_trade_outcome(d)`).
- **Design doc:** §5.3 (function shape); §5.4 (pair construction edge cases).

### Pre-flight checks

1. Batches 7.0–7.4 merged.
2. Confirm D03 has `signal_id` column populated (Batch 7.0 ran on the dev QuestDB; verify via `SELECT count() FROM p3_d03_trade_outcome_log WHERE signal_id IS NULL` returns 0 in test fixtures).
3. Read `shared/trade_source.py` to find the right insertion point (alongside `seed_d03_from_synthetic`).

### Files + line ranges to modify

| File | Lines | Change |
|---|---|---|
| `shared/trade_source.py` | (after L314 / module-bottom append) | Add `RealisedOutcome` dataclass + `actual_trade_outcome(d, *, user_id, asset=None, signal_id=None) → RealisedOutcome \| None` |
| `tests/test_actual_trade_outcome.py` | NEW | Read-helper tests covering signal_id lookup + edge cases |

### Exact change shape

**`shared/trade_source.py` (NEW additions):**

```python
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


_ET = ZoneInfo("America/New_York")


@dataclass
class RealisedOutcome:
    signal_id: str
    trade_id: str
    pnl: float            # D03.pnl  (realised, net of commission)
    gross_pnl: float
    commission: float
    contracts: int
    entry_price: float
    exit_price: float
    entry_time: datetime
    exit_time: datetime
    direction: int
    regime_at_entry: str | None


def actual_trade_outcome(
    d: date,
    *,
    user_id: str,
    asset: str | None = None,
    signal_id: str | None = None,
) -> RealisedOutcome | None:
    """Doc 32 PG-09 line 357: realised P&L from D03 for session day `d`.
    
    If signal_id is supplied, returns the matching trade (or None if not found).
    Otherwise returns the aggregate outcome for (user_id, asset) on day d as a
    single composite — sum pnl/gross_pnl/commission/contracts, first/last entry/exit.
    """
    from shared.questdb_client import get_cursor

    et_start = datetime.combine(d, time.min).replace(tzinfo=_ET)
    et_end = et_start + timedelta(days=1)

    with get_cursor() as cur:
        if signal_id is not None:
            cur.execute(
                """
                SELECT trade_id, signal_id, pnl, gross_pnl, commission, contracts,
                       entry_price, exit_price, entry_time, exit_time, direction,
                       regime_at_entry
                FROM p3_d03_trade_outcome_log
                WHERE signal_id = $1
                  AND user_id = $2
                  AND entry_time >= $3
                  AND entry_time < $4
                """,
                (signal_id, user_id, et_start, et_end),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return RealisedOutcome(*row)

        # Aggregate path (asset required when signal_id absent)
        if asset is None:
            raise ValueError("actual_trade_outcome requires either signal_id or asset")
        cur.execute(
            """
            SELECT trade_id, signal_id, pnl, gross_pnl, commission, contracts,
                   entry_price, exit_price, entry_time, exit_time, direction,
                   regime_at_entry
            FROM p3_d03_trade_outcome_log
            WHERE user_id = $1 AND asset = $2
              AND entry_time >= $3 AND entry_time < $4
            ORDER BY entry_time ASC
            """,
            (user_id, asset, et_start, et_end),
        )
        rows = cur.fetchall()
        if not rows:
            return None
        # Composite of multiple trades on same day → use a synthetic ID + summed metrics
        return _aggregate_outcomes(rows)


def _aggregate_outcomes(rows: list[tuple]) -> RealisedOutcome:
    """Combine multiple D03 rows into one composite outcome (PG-09 daily aggregate)."""
    # Sum pnl, gross_pnl, commission, contracts; take first entry, last exit; first regime.
    ...
```

### Test additions

**`tests/test_actual_trade_outcome.py` (NEW):**

| Test | Assertion |
|---|---|
| `test_actual_trade_outcome_by_signal_id` | Seed D03 with row `signal_id='SIG-1'`, `pnl=12.34`; call helper; assert returned outcome has `pnl=12.34`. |
| `test_actual_trade_outcome_signal_not_found_returns_none` | Call with unknown signal_id; assert returns `None`. |
| `test_actual_trade_outcome_aggregate_path` | Seed 3 D03 rows for same user/asset/day with pnl `[10, 20, -5]`; call without signal_id; assert composite pnl=25. |
| `test_actual_trade_outcome_session_day_boundary` | Seed row with entry_time at 23:59:59 ET on day d; call with d+1; assert returns `None` (boundary correctness). |
| `test_actual_trade_outcome_legacy_signal_id` | Seed row with `signal_id='LEGACY-<uuid>'`; call with that id; assert returns row (legacy IDs queryable). |
| `test_actual_trade_outcome_uses_realised_pnl` | Seed row with `gross_pnl=100, commission=5, pnl=95`; assert returned `pnl=95` (net), `gross_pnl=100`, `commission=5`. |

### Exit criteria

- All helper tests pass.
- Helper exported from `shared.trade_source` and importable from offline blocks.

### Rollback procedure

1. `git revert <commit>` — removes helper. No production callers yet (caller in 7.6).

---

## Batch 7.6 — PG-09 rebuild: metric reconstruction from D03 pairs + gate rewire

**Status:** GO

### Spec citation

- **Decisions log:** §2 Group C Q-14 (line 58); Q-15 (line 59).
- **Audit:** F-22, F-23.
- **Spec authority:** doc 32 PG-09 (L337–378) — the canonical pseudocode.
- **Design doc:** §1.3 file impact; §4 G-OFF-016 mapping; §5 P&L source.

### Pre-flight checks

1. Batches 7.0–7.5 merged.
2. Confirm `captain_online_replay` and `actual_trade_outcome` are importable.
3. Read `b3_pseudotrader.py:780–1038` (`run_pseudotrader`, `run_signal_replay_comparison`, `captain_online_replay` wrapper) to capture the existing call graph; map every caller for the rewire.
4. `grep -rn "run_signal_replay_comparison\|run_pseudotrader\b" /home/nomaan/captain-system --include='*.py'` — enumerate callers.
5. Read `captain-offline/.../orchestrator.py:62–127` (`_pseudotrader_gate`) and L252/L294/L348/L384 (handlers) to capture wiring.

### Files + line ranges to modify

| File | Lines | Change |
|---|---|---|
| `captain-offline/captain_offline/blocks/b3_pseudotrader.py` | 718–777 | Replace existing `captain_online_replay` wrapper that delegates to `replay_engine.run_replay`/`run_whatif`; new wrapper imports from `shared.online_replay` |
| `captain-offline/captain_offline/blocks/b3_pseudotrader.py` | 780–934 | Rewrite `run_pseudotrader` body: build `{signal, outcome}` pairs via `captain_online_replay` + `actual_trade_outcome`; compute Sharpe / PBO (S=8) / DSR from pair series |
| `captain-offline/captain_offline/blocks/b3_pseudotrader.py` | 937–1038 | Retire `run_signal_replay_comparison` — replace body with single-line delegation to new `run_pseudotrader` (preserves any external callers) |
| `captain-offline/captain_offline/blocks/b3_pseudotrader.py` | 688–715 | `fetch_d03_trade_outcomes` now used only as date-discovery helper; mark behavior |
| `captain-offline/captain_offline/blocks/orchestrator.py` | 62–127 (`_pseudotrader_gate`) | Replace `run_signal_replay_comparison` call with `run_pseudotrader` |
| `captain-offline/captain_offline/blocks/orchestrator.py` | 252, 294, 348, 384 (handlers) | Audit each call site; ensure `user_id` is threaded through (memory observation 2023 noted user_id missing) |
| `tests/test_pg09_pseudotrader.py` | NEW or refactor existing | Pair-construction correctness; metric correctness; D03 join behavior |

### Exact change shape

**`b3_pseudotrader.py:718–777` `captain_online_replay` wrapper rewrite:**

```python
# BEFORE — delegates to shared.replay_engine.run_replay/run_whatif (parallel B-block logic)
def captain_online_replay(d, using, ...):
    from shared.replay_engine import run_replay, run_whatif
    config = load_replay_config(...)
    if using is None:
        return run_replay(config, ...)
    else:
        return run_whatif(config, overrides=using, ...)

# AFTER — delegates to shared.online_replay (live B1-B6)
def captain_online_replay(d, *, using, user_id, asset=None, session_id=None):
    """Doc 32 PG-09 line 343/352 entry. Real B1-B6 against historical bars."""
    from shared.online_replay import captain_online_replay as _impl
    return _impl(d, using=using, user_id=user_id, asset=asset, session_id=session_id)
```

**`b3_pseudotrader.py:780–934` `run_pseudotrader` rewrite (skeleton):**

```python
# BEFORE — falls back to direct P&L compare or run_signal_replay_comparison
def run_pseudotrader(user_id, asset, proposed_update, historical_window, *, baseline_pnl=None, proposed_pnl=None):
    if baseline_pnl is not None and proposed_pnl is not None:
        # direct P&L path — F-25 path
        return _compare_direct(baseline_pnl, proposed_pnl)
    # else: use SignalReplayEngine via run_signal_replay_comparison — F-22 path
    return run_signal_replay_comparison(...)

# AFTER — pair-based per spec
def run_pseudotrader(
    user_id: str,
    asset: str | None,
    proposed_update: dict,
    historical_window: tuple[date, date],
    *,
    parameters_current: ReplayParameters | None = None,
    parameters_proposed: ReplayParameters | None = None,
) -> dict:
    """PG-09 — Phases 1–5 per doc 32 lines 339–377."""
    from shared.online_replay import captain_online_replay
    from shared.trade_source import actual_trade_outcome
    from shared.statistics import compute_sharpe, compute_cscv_pbo, compute_dsr, max_drawdown, win_rate

    parameters_current = parameters_current or _live_parameters(user_id)

    # Phase 1: replay WITHOUT update
    baseline_pairs = []
    for d in iter_session_days(*historical_window):
        signals = captain_online_replay(d, using=parameters_current, user_id=user_id, asset=asset)
        for sig in signals:
            outcome = actual_trade_outcome(d, user_id=user_id, asset=sig["asset"], signal_id=sig["signal_id"])
            baseline_pairs.append({"signal": sig, "outcome": outcome})

    # Phase 2: replay WITH update
    updated_pairs = []
    for d in iter_session_days(*historical_window):
        signals = captain_online_replay(d, using=parameters_proposed, user_id=user_id, asset=asset)
        for sig in signals:
            outcome = actual_trade_outcome(d, user_id=user_id, asset=sig["asset"], signal_id=sig["signal_id"])
            updated_pairs.append({"signal": sig, "outcome": outcome})

    # Phase 3: compare (drop unmatched signals — outcome=None means no D03 row)
    baseline_returns = [p["outcome"].pnl / max(p["outcome"].contracts, 1)
                       for p in baseline_pairs if p["outcome"] is not None]
    updated_returns = [p["outcome"].pnl / max(p["outcome"].contracts, 1)
                      for p in updated_pairs if p["outcome"] is not None]

    sharpe_baseline = compute_sharpe(baseline_returns)
    sharpe_updated  = compute_sharpe(updated_returns)
    sharpe_improvement = sharpe_updated - sharpe_baseline
    drawdown_baseline = max_drawdown(baseline_returns)
    drawdown_updated  = max_drawdown(updated_returns)
    winrate_baseline  = win_rate(baseline_returns)
    winrate_updated   = win_rate(updated_returns)

    # Phase 4: validate (anti-overfitting); S=8 per Q-16
    pbo = compute_cscv_pbo(updated_returns, S=8)
    dsr = compute_dsr(sharpe_updated, n_trials=_n_trials(proposed_update),
                      skew=_skew(updated_returns), kurtosis=_kurt(updated_returns),
                      T=len(updated_returns))

    # Phase 5: store + report
    recommendation = "ADOPT" if (sharpe_improvement > 0 and pbo < 0.5 and dsr > 0.5) else "REJECT"
    result = {
        "update_type": proposed_update["type"],
        "sharpe_baseline": sharpe_baseline,
        "sharpe_updated": sharpe_updated,
        "sharpe_improvement": sharpe_improvement,
        "drawdown_change": drawdown_updated - drawdown_baseline,
        "winrate_delta": winrate_updated - winrate_baseline,
        "pbo": pbo,
        "dsr": dsr,
        "recommendation": recommendation,
        "pair_series": {"baseline": baseline_pairs, "updated": updated_pairs},
    }
    _persist_to_p3_d11(result)
    _generate_rpt09(result)
    return result


# Existing run_signal_replay_comparison reduced to a thin shim for any external caller.
def run_signal_replay_comparison(*args, **kwargs):
    """DEPRECATED — delegates to run_pseudotrader. Will be removed in Phase 12."""
    return run_pseudotrader(*args, **kwargs)
```

**Orchestrator gate rewire (`captain-offline/.../orchestrator.py:79`):**

```python
# BEFORE
def _pseudotrader_gate(self, user_id, asset, proposed_update):
    return run_signal_replay_comparison(user_id, asset, proposed_update, ...)

# AFTER
def _pseudotrader_gate(self, user_id, asset, proposed_update, historical_window):
    return run_pseudotrader(
        user_id=user_id,
        asset=asset,
        proposed_update=proposed_update,
        historical_window=historical_window,
        parameters_proposed=_build_proposed_params(proposed_update),
    )
```

### Test additions

**`tests/test_pg09_pseudotrader.py` (NEW or refactor):**

| Test | Assertion |
|---|---|
| `test_pg09_builds_signal_outcome_pairs` | Seed D03 with 5 known signal_ids and pnl values; mock `captain_online_replay` to return signals with those IDs; assert `baseline_pairs` length 5 with correct outcomes. |
| `test_pg09_excludes_unmatched_signals` | Mock `captain_online_replay` to return 3 signals; seed D03 with only 2 of those signal_ids; assert returns metrics computed from 2 matched signals only. |
| `test_pg09_pbo_uses_S_eq_8` | Spy on `compute_cscv_pbo`; assert called with `S=8`. |
| `test_pg09_dsr_uses_updated_sharpe` | Spy on `compute_dsr`; assert first arg = `sharpe_updated`. |
| `test_pg09_recommendation_adopt_when_improving_and_validated` | Seed metrics: improvement>0, pbo<0.5, dsr>0.5; assert recommendation="ADOPT". |
| `test_pg09_recommendation_reject_otherwise` | Seed each gate-fail combo; assert recommendation="REJECT". |
| `test_pg09_persists_to_p3_d11` | Seed; run; query D11; assert row written with sharpe_baseline, sharpe_updated, recommendation, pair_series. |
| `test_pg09_orchestrator_gate_calls_run_pseudotrader` | Mock `run_pseudotrader`; trigger gate from orchestrator handler; assert called. |
| `test_pg09_no_signal_replay_engine_in_call_graph` | Static check: `import b3_pseudotrader; assert "SignalReplayEngine" not in dir(b3_pseudotrader)`. |
| `test_pg09_user_id_threaded_through_handlers` | Memory observation 2023 fix: simulate handler-level invocation; assert `user_id` reaches `actual_trade_outcome`. |

### Exit criteria

- All PG-09 tests pass.
- F-22 closed: `_pseudotrader_gate` no longer routes through `SignalReplayEngine`.
- F-23 closed: PG-09 metrics computed from D03 realised P&L pairs.
- D11 persistence verified.

### Rollback procedure

1. `git revert <commit>` — restores prior `run_pseudotrader` + `run_signal_replay_comparison`.
2. New `captain_online_replay` from Batch 7.4 stays — it's harmless without callers.

---

## Batch 7.7 — `aim_retroactive_replay` + PG-10 Step 1 wire-up

**Status:** GO

### Spec citation

- **Audit:** F-24.
- **Spec authority:** doc 32 PG-10 line 387 (`retroactive_modifiers[a] = aim_retroactive_replay(a, new_candidate, historical_window)`).
- **Design doc:** §1.3 (`shared/aim_retroactive.py` new); Appendix A (signature).

### Pre-flight checks

1. Batches 7.0–7.6 merged.
2. Read `shared/aim_compute.py` to confirm per-AIM modifier functions exist (`_aim01_vrp`, `_aim03_gex`, etc.); these are reused.
3. Confirm historical features are queryable from QuestDB tables D29/D30/D31/D33 (Batch 7.1 verified bar table identity).

### Files + line ranges to modify

| File | Lines | Change |
|---|---|---|
| `shared/aim_retroactive.py` | NEW | `aim_retroactive_replay(aim_id, candidate_strategy, historical_window, *, user_id, asset)` |
| `captain-offline/captain_offline/blocks/b4_injection.py` | 46–65 (`_compute_aim_adjusted_edge`) | Replace scalar heuristic with per-AIM retroactive replay; aggregate per-day returns |
| `captain-offline/captain_offline/blocks/b4_injection.py` | 109–169 (`run_injection_comparison`) | Update to call new AIM Step 1 path |
| `tests/test_aim_retroactive_replay.py` | NEW | Coverage of the new function + injection caller |

### Exact change shape

**`shared/aim_retroactive.py` (NEW):**

```python
"""Phase 7 — AIM retroactive replay (PG-10 Step 1).

Per Stage 1B Appendix A. Independent of replay_session — does not run B1-B6;
only replays the AIM modifier computation against historical features.
"""
from datetime import date
from shared.aim_compute import compute_aim_modifier  # dispatch table


def aim_retroactive_replay(
    aim_id: int,
    candidate_strategy: dict,
    historical_window: tuple[date, date],
    *,
    user_id: str,
    asset: str,
) -> list[tuple[date, float]]:
    """Per-day modifier series for AIM `aim_id` against `candidate_strategy`'s
    feature inputs over `historical_window`.
    
    Returns [(date, modifier), ...] sorted by date.
    """
    series = []
    for d in _iter_session_days(*historical_window):
        features = _load_historical_features(asset, d)  # reads D29/D30/D31/D33
        if features is None:
            continue
        # Build a synthetic state dict carrying candidate_strategy thresholds.
        state = _state_from_candidate(candidate_strategy, asset)
        result = compute_aim_modifier(aim_id, features, state)
        if result is None:
            continue
        series.append((d, result["modifier"]))
    return series


def _load_historical_features(asset: str, d: date) -> dict | None:
    """Load the feature row for asset on session day d from QuestDB."""
    ...


def _state_from_candidate(candidate_strategy: dict, asset: str) -> dict:
    """Build the state dict that AIM modifier functions expect, populated from
    candidate_strategy parameters."""
    ...


def _iter_session_days(start: date, end: date):
    ...
```

**`b4_injection.py:46–65` `_compute_aim_adjusted_edge` rewrite:**

```python
# BEFORE — scalar heuristic
def _compute_aim_adjusted_edge(strategy, historical_pnl, aim_weights):
    mean_pnl = mean(historical_pnl)
    mean_modifier = sum(aim_weights.values()) / len(aim_weights)
    return mean_pnl * mean_modifier

# AFTER — per-AIM retroactive replay
def _compute_aim_adjusted_edge(
    strategy: dict, historical_window: tuple[date, date],
    user_id: str, asset: str, aim_weights: dict,
) -> float:
    """PG-10 Step 1: aggregate per-AIM retroactive modifiers."""
    from shared.aim_retroactive import aim_retroactive_replay

    retroactive_modifiers = {}
    for aim_id, weight in aim_weights.items():
        if weight == 0:
            continue
        series = aim_retroactive_replay(aim_id, strategy, historical_window,
                                        user_id=user_id, asset=asset)
        retroactive_modifiers[aim_id] = series

    # Aggregate: for each day, weighted-avg modifier across active AIMs.
    aggregated = _aggregate_modifiers(retroactive_modifiers, aim_weights)

    # Multiply with realised P&L per day to get expected edge under candidate.
    daily_pnl = _load_daily_pnl(user_id, asset, historical_window)
    edge_series = [agg * pnl for agg, pnl in zip(aggregated, daily_pnl)]
    return mean(edge_series)
```

### Test additions

**`tests/test_aim_retroactive_replay.py` (NEW):**

| Test | Assertion |
|---|---|
| `test_retroactive_returns_per_day_series` | Seed historical features for 5 days; call replay; assert returned list length 5. |
| `test_retroactive_uses_candidate_thresholds_not_live` | Seed live state thresholds = X, candidate thresholds = Y; call replay; assert modifier reflects Y not X. |
| `test_retroactive_skips_days_without_features` | Seed features missing on day 3 of 5; assert returned series length 4 with correct dates. |
| `test_retroactive_aim_dispatch_correct` | Spy on `compute_aim_modifier`; assert called with the right `aim_id` and feature dict. |
| `test_pg10_step1_uses_retroactive_replay` | Mock `aim_retroactive_replay`; call `run_injection_comparison`; assert mock invoked once per active AIM. |
| `test_pg10_step1_aggregates_modifiers_correctly` | Seed two AIMs with known modifier series; assert weighted aggregate matches expected formula. |

### Exit criteria

- All retroactive tests pass.
- F-24 closed: PG-10 Step 1 invokes `aim_retroactive_replay` per active AIM.

### Rollback procedure

1. `git revert <commit>` — restores scalar heuristic.
2. `shared/aim_retroactive.py` deletion harmless if no other caller.

---

## Batch 7.8 — PG-10 Step 3 internal `pseudotrader_compare` via replay

**Status:** GO

### Spec citation

- **Audit:** F-25.
- **Spec authority:** doc 32 PG-10 line 396 (`pseudo_results = pseudotrader_compare(new_candidate, current_strategy, historical_window)`).
- **Design doc:** §1.3.

### Pre-flight checks

1. Batches 7.0–7.7 merged.
2. Read `b4_injection.py:131–134` to confirm where `baseline_pnl`/`proposed_pnl` are passed to `run_pseudotrader`.

### Files + line ranges to modify

| File | Lines | Change |
|---|---|---|
| `captain-offline/captain_offline/blocks/b4_injection.py` | 131–134 (Step 3 in `run_injection_comparison`) | Drop precomputed `baseline_pnl`/`proposed_pnl`; let `run_pseudotrader` execute its replay path |
| `tests/test_pg10_internal_compare.py` | NEW | Verify Step 3 takes the replay path |

### Exact change shape

**`b4_injection.py:131–134` rewrite:**

```python
# BEFORE
pseudo_results = run_pseudotrader(
    user_id=user_id,
    asset=asset,
    proposed_update=proposed_update,
    historical_window=historical_window,
    baseline_pnl=current_pnl,    # F-25 — precomputed; bypasses replay
    proposed_pnl=candidate_pnl,
)

# AFTER
pseudo_results = run_pseudotrader(
    user_id=user_id,
    asset=asset,
    proposed_update=proposed_update,
    historical_window=historical_window,
    parameters_current=ReplayParameters(locked_strategies={asset: current_strategy}),
    parameters_proposed=ReplayParameters(locked_strategies={asset: new_candidate}),
)
```

The `baseline_pnl`/`proposed_pnl` keyword args are removed from `run_pseudotrader`'s signature (no remaining callers after this batch + Batch 7.6 retired the direct path).

### Test additions

**`tests/test_pg10_internal_compare.py` (NEW):**

| Test | Assertion |
|---|---|
| `test_pg10_step3_invokes_replay_path` | Mock `captain_online_replay`; trigger `run_injection_comparison`; assert mock called with both current and proposed parameters. |
| `test_pg10_step3_no_precomputed_pnl_branch` | Static check: `b4_injection.run_injection_comparison` source contains no `baseline_pnl=` or `proposed_pnl=` kwargs. |
| `test_pg10_full_flow_returns_expected_decision` | Seed: replay produces sharpe_improvement > 0, pbo < 0.5, dsr > 0.5, expected_new = 1.5*expected_current; assert recommendation="ADOPT". |

### Exit criteria

- All Step 3 tests pass.
- F-25 closed.

### Rollback procedure

1. `git revert <commit>` — restores precomputed-P&L branch.

---

## Batch 7.9 — PG-13 walk-forward train + validate windows; DSR from holdout-OOS Sharpe

**Status:** GO

### Spec citation

- **Audit:** F-28, F-29.
- **Spec authority:** doc 32 PG-13 lines 514–530 (walk-forward + final OOS test).
- **Design doc:** §1.3; pass-2 open question O6 (rolling-fold defaults).

### Pre-flight checks

1. Batches 7.0–7.6 merged.
2. Read `b6_auto_expansion.py:117–205` (`_evaluate_candidate`), `:264–380` (`run_auto_expansion`).
3. Decide rolling-fold parameters per O6: 5 expanding folds, equal validation slices.

### Files + line ranges to modify

| File | Lines | Change |
|---|---|---|
| `captain-offline/captain_offline/blocks/b6_auto_expansion.py` | 117–205 (`_evaluate_candidate`) | Replace single 70/30 split with 5-fold expanding walk-forward via `replay_session`; fitness = average robust_sharpe across folds |
| `captain-offline/captain_offline/blocks/b6_auto_expansion.py` | 264–380 (`run_auto_expansion`) | Build `oos_result` per candidate via `replay_session` over holdout window; replace `_compute_dsr(candidate.fitness)` with `_compute_dsr(oos_result.sharpe)` |
| `captain-offline/captain_offline/blocks/b6_auto_expansion.py` | (whole file) | Remove all imports/calls to `SignalReplayEngine` |
| `tests/test_pg13_walkforward.py` | NEW | Walk-forward correctness; DSR-from-OOS fix; live-block fitness path |

### Exact change shape

**`b6_auto_expansion.py:117–205` `_evaluate_candidate` rewrite (skeleton):**

```python
# BEFORE — single 70/30 split, fitness = validation-tail Sharpe
def _evaluate_candidate(candidate, historical_returns):
    split = int(len(historical_returns) * 0.7)
    validation_returns = historical_returns[split:]  # F-29: train window unused
    engine = SignalReplayEngine.load_replay_context(...)
    daily_pnl = engine.strategy_replay(candidate, validation_returns)  # F-29
    fitness = compute_sharpe(daily_pnl)
    candidate.fitness = fitness
    return fitness

# AFTER — 5-fold expanding walk-forward via replay_session
def _evaluate_candidate(candidate, historical_window, *, user_id, asset, n_folds=5):
    """PG-13 walk-forward fitness — average robust_sharpe across folds."""
    from shared.online_replay import replay_session, OnlineReplayContext
    from shared.online_replay_providers import (
        HistoricalMarketDataProvider, CapturingSignalSink, FixedTimeProvider,
    )

    folds = _build_expanding_folds(historical_window, n_folds=n_folds)
    fold_sharpes = []
    for train_window, validate_window in folds:
        # Train: live params seeded; validate: candidate params replayed
        ctx = _build_replay_context(asset)
        validate_pnls = []
        for d in iter_session_days(*validate_window):
            signals = captain_online_replay(d, using=_params_from_candidate(candidate),
                                             user_id=user_id, asset=asset)
            for sig in signals:
                outcome = actual_trade_outcome(d, user_id=user_id, asset=asset, signal_id=sig["signal_id"])
                if outcome:
                    validate_pnls.append(outcome.pnl / max(outcome.contracts, 1))
        fold_sharpes.append(compute_robust_sharpe(validate_pnls))

    fitness = mean(fold_sharpes)
    candidate.fitness = fitness
    candidate.fold_sharpes = fold_sharpes  # diagnostic
    return fitness
```

**`b6_auto_expansion.py:264–380` `run_auto_expansion` DSR-from-OOS fix:**

```python
# BEFORE
for candidate in top_candidates:
    oos = _candidate_oos_returns(candidate, holdout_returns)  # F-26: discarded later
    pbo = _compute_pbo(oos)
    dsr = _compute_dsr(candidate.fitness, ...)   # F-28: WRONG — uses validation-tail Sharpe
    if pbo < 0.5 and dsr > 0.5:
        viable.append(...)

# AFTER
for candidate in top_candidates:
    oos = _candidate_oos_returns(candidate, holdout_window=holdout_window, user_id=user_id, asset=asset)
    oos_sharpe = compute_sharpe(oos)
    pbo = _compute_pbo(oos)
    dsr = _compute_dsr(oos_sharpe, n_trials=len(population)*50, ...)   # F-28 fixed
    if pbo < 0.5 and dsr > 0.5:
        viable.append({"candidate": candidate, "oos": oos, "pbo": pbo, "dsr": dsr})
```

### Test additions

**`tests/test_pg13_walkforward.py` (NEW):**

| Test | Assertion |
|---|---|
| `test_walkforward_uses_5_folds` | Spy on `_build_expanding_folds`; assert called with `n_folds=5`; returned list length 5. |
| `test_walkforward_train_window_distinct_from_validation` | Build folds; assert each fold's `train_window` end <= `validate_window` start (no leakage). |
| `test_walkforward_fitness_is_fold_mean` | Mock fold_sharpes = [1.0, 2.0, 3.0]; assert fitness = 2.0. |
| `test_walkforward_uses_replay_session_not_signal_replay_engine` | Spy on `captain_online_replay` and `SignalReplayEngine`; assert former called, latter not imported. |
| `test_dsr_uses_oos_sharpe` | Seed candidate.fitness=1.0, OOS Sharpe=2.0; spy on `_compute_dsr`; assert called with 2.0 not 1.0. |
| `test_pg13_no_signal_replay_engine_in_module` | Static check: `b6_auto_expansion` source no longer imports `SignalReplayEngine`. |

### Exit criteria

- All walk-forward tests pass.
- F-28 closed (DSR from OOS Sharpe).
- F-29 closed (walk-forward folds used).
- `SignalReplayEngine` import removed from `b6_auto_expansion.py`.

### Rollback procedure

1. `git revert <commit>` — restores 70/30 split + DSR-from-fitness.
2. `SignalReplayEngine` re-imported automatically by revert.

---

## Batch 7.10 — PG-13 candidate handoff to PG-10 (per-candidate `oos`)

**Status:** GO

### Spec citation

- **Audit:** F-26.
- **Spec authority:** doc 32 PG-13 lines 528–536 (per-candidate OOS).
- **Design doc:** §1.3.

### Pre-flight checks

1. Batches 7.7, 7.8, 7.9 merged.
2. Read `b6_auto_expansion.py:367–374` (final loop calling `run_injection_comparison`).
3. Read `b4_injection.run_injection_comparison` signature post-7.8 to confirm parameter shape.

### Files + line ranges to modify

| File | Lines | Change |
|---|---|---|
| `captain-offline/captain_offline/blocks/b6_auto_expansion.py` | 367–374 | Replace identical `holdout_returns` with per-candidate `oos` series |
| `captain-offline/captain_offline/blocks/b4_injection.py` | (signature site) | Accept `oos_returns_candidate` + `oos_returns_baseline` per call (or keep `parameters_proposed`/`parameters_current` from 7.8 if PG-10 internal compare path subsumes it) |
| `tests/test_pg13_handoff.py` | NEW | Each viable candidate hands its own oos to PG-10 |

### Exact change shape

**`b6_auto_expansion.py:367–374` rewrite:**

```python
# BEFORE
for fc in final_candidates:
    run_injection_comparison(
        new_candidate=fc.candidate,
        decayed_asset=decayed_asset,
        candidate_pnl=holdout_returns,   # F-26 BUG: same series for every candidate
    )

# AFTER  
for fc in final_candidates:
    run_injection_comparison(
        new_candidate=fc.candidate,
        decayed_asset=decayed_asset,
        oos_returns_candidate=fc.oos,    # per-candidate OOS from 7.9
        # baseline series produced by run_pseudotrader internally via replay
    )
```

### Test additions

**`tests/test_pg13_handoff.py` (NEW):**

| Test | Assertion |
|---|---|
| `test_each_candidate_uses_own_oos` | Mock 3 viable candidates with distinct oos series; spy on `run_injection_comparison`; assert each call received its candidate's oos, not a shared series. |
| `test_no_holdout_returns_arg_in_handoff` | Static check: `b6_auto_expansion` calls to `run_injection_comparison` do not pass `candidate_pnl=holdout_returns`. |

### Exit criteria

- All handoff tests pass.
- F-26 closed.

### Rollback procedure

1. `git revert <commit>` — restores identical-`holdout_returns` bug.

---

## Batch 7.11 — PG-12 sensitivity full-grid PBO (`compute_CSCV_PBO(results, S=8)`)

**Status:** GO

### Spec citation

- **Audit:** F-27.
- **Decisions log:** §2 Resolved-by-spec (Q-16 — full grid, S=8).
- **Spec authority:** doc 32 PG-12 line 470.

### Pre-flight checks

1. Batches 7.0 (D03) merged. (PG-12 doesn't depend on the replay harness.)
2. Read `b5_sensitivity.py:214–216` to capture current best-cell-only logic.
3. Confirm `compute_cscv_pbo` (or equivalent) supports S=8 grid input in `shared/statistics.py`.

### Files + line ranges to modify

| File | Lines | Change |
|---|---|---|
| `captain-offline/captain_offline/blocks/b5_sensitivity.py` | 214–216 | Replace single best-cell PBO with full-grid PBO at S=8 |
| `tests/test_pg12_pbo.py` | NEW | Verify PBO consumes the full grid |

### Exact change shape

**`b5_sensitivity.py:214–216` rewrite:**

```python
# BEFORE
best_cell = max(results, key=lambda r: r.sharpe)
pbo = compute_cscv_pbo([best_cell.returns_series], S=8)  # F-27: single cell

# AFTER
all_returns_series = [r.returns_series for r in results]
pbo = compute_cscv_pbo(all_returns_series, S=8)  # full grid per spec L470
```

### Test additions

**`tests/test_pg12_pbo.py` (NEW):**

| Test | Assertion |
|---|---|
| `test_pbo_consumes_full_grid` | Seed sensitivity grid with 49 cells; spy on `compute_cscv_pbo`; assert called with 49-element list, S=8. |
| `test_pbo_not_called_with_single_cell` | Same setup; assert spy NOT called with 1-element list. |

### Exit criteria

- F-27 closed.
- All PG-12 tests pass.

### Rollback procedure

1. `git revert <commit>` — restores best-cell-only PBO.

---

## Batch 7.12 — `shared/replay_engine.py` refactor in place

**Status:** GO

### Spec citation

- **Design doc:** D10; §1.3.
- **Pass-2 open question:** O5 (other callers besides `b11_replay_runner.py`).

### Pre-flight checks

1. Batches 7.0–7.11 merged.
2. `grep -rn "from shared.replay_engine\|shared.replay_engine import\|shared/replay_engine" /home/nomaan/captain-system --include='*.py'` — enumerate every caller.
3. Read `captain-command/.../b11_replay_runner.py` to confirm the public-API surface area it consumes (`run_replay`, `run_whatif`, `load_replay_config`).
4. If any caller besides `b11_replay_runner.py` exists, escalate to staged refactor; otherwise proceed in place.

### Files + line ranges to modify

| File | Lines | Change |
|---|---|---|
| `shared/replay_engine.py` | 58–382 (`load_replay_config`) | Keep — useful pattern for state hydration |
| `shared/replay_engine.py` | 556–770 (`simulate_orb`) | DELETE — duplicates B1 OR-tracker |
| `shared/replay_engine.py` | 777–816 (`_compute_regime_probs`) | DELETE — duplicates B2 |
| `shared/replay_engine.py` | 889–1167 (`compute_contracts`) | DELETE — duplicates B4 7-layer |
| `shared/replay_engine.py` | 1255–1438 (quality/correlation/portfolio cap) | DELETE — duplicates B5/B5B |
| `shared/replay_engine.py` | 1485–1879 (`run_replay`) | Replace body: thin wrapper that constructs `OnlineReplayContext` from `config` and calls `replay_session`; preserve return shape |
| `shared/replay_engine.py` | 1886–2071 (`run_whatif`) | Replace body: thin wrapper applying parameter overrides via `ReplayParameters` and calling `replay_session`; preserve return shape |
| `tests/test_replay_engine_refactor.py` | NEW | Verify GUI replay still works; assert behavior parity |

### Exact change shape

**`shared/replay_engine.py:1485` `run_replay` rewrite (skeleton):**

```python
# BEFORE — ~395 lines of parallel B1-B6 logic

# AFTER — thin wrapper
def run_replay(config: dict) -> dict:
    """GUI replay entry — preserved public API.
    
    Internals delegate to shared.online_replay.replay_session, ensuring GUI
    replay inherits live-block parity automatically.
    """
    from shared.online_replay import replay_session, OnlineReplayContext, ReplayParameters
    from shared.online_replay_providers import (
        HistoricalMarketDataProvider, CapturingSignalSink, FixedTimeProvider,
    )

    session_date = config["session_date"]
    session_id = config["session_id"]
    parameters = _config_to_parameters(config)  # ReplayParameters from current config dict
    ctx = OnlineReplayContext(
        market_data=HistoricalMarketDataProvider(as_of=_session_open(session_date, session_id)),
        signal_sink=CapturingSignalSink(),
        time_provider=FixedTimeProvider(_session_open(session_date, session_id)),
        reset_hooks=default_reset_hooks(),
    )
    result = replay_session(session_date, session_id, ctx, parameters)
    # Map ReplayResult → existing run_replay return shape (positions/sizing/metrics dict)
    return _result_to_legacy_shape(result)
```

### Test additions

**`tests/test_replay_engine_refactor.py` (NEW):**

| Test | Assertion |
|---|---|
| `test_run_replay_delegates_to_replay_session` | Spy on `replay_session`; call `run_replay(config)`; assert spy called with same date/session. |
| `test_run_replay_preserves_legacy_return_shape` | Pre-Phase-7 `run_replay` returned `{positions: ..., sizing: ..., metrics: ...}`; post-refactor must produce the same keys. |
| `test_run_whatif_applies_parameter_overrides` | Pass override dict; verify `ReplayParameters` is constructed and passed to `replay_session`. |
| `test_b11_replay_runner_smoke` | Run `b11_replay_runner` with a minimal seed; assert no exceptions and a reasonable result shape. |
| `test_no_parallel_b_block_logic_remains` | Static check: `simulate_orb`, `_compute_regime_probs`, `compute_contracts`, `_apply_quality_gate` not present in `replay_engine.py`. |
| `test_replay_engine_loc_reduced` | `wc -l shared/replay_engine.py` < 800 (was 2072); soft check. |

### Exit criteria

- All refactor tests pass.
- `b11_replay_runner.py` GUI replay smoke test green.
- ~600+ LOC deleted from `replay_engine.py`.
- Public API (`run_replay`, `run_whatif`, `load_replay_config`) unchanged.

### Rollback procedure

1. `git revert <commit>` — restores parallel B-block logic.
2. GUI replay continues working under either branch.

---

## Batch 7.13 — `SignalReplayEngine` deprecation stub

**Status:** GO

### Spec citation

- **Design doc:** D9; Appendix C (deprecation timeline).
- **Stage 1A audit:** §5.1.

### Pre-flight checks

1. Batches 7.6, 7.9, 7.12 merged (all in-Phase-7 callers migrated).
2. `grep -rn "SignalReplayEngine\|signal_replay" /home/nomaan/captain-system --include='*.py'` — confirm only `b5_sensitivity.py` (out-of-Phase-7) still calls it.

### Files + line ranges to modify

| File | Lines | Change |
|---|---|---|
| `shared/signal_replay.py` | 68–517 (`SignalReplayEngine`) | Reduce class body to deprecation stub — methods log `DeprecationWarning` and delegate to `replay_session` |
| `tests/test_signal_replay_deprecation.py` | NEW | Verify warning emitted; verify Phase 7 callers no longer import it |

### Exact change shape

**`shared/signal_replay.py:68–517` stub rewrite:**

```python
# BEFORE — 449-line class with sizing_replay, strategy_replay, load_replay_context

# AFTER — deprecation stub
import warnings
from typing import Any


class SignalReplayEngine:
    """DEPRECATED — Phase 7 migrated callers to shared.online_replay.replay_session.
    
    This class will be deleted in Phase 12. Remaining external callers (currently
    only b5_sensitivity.py) should migrate to replay_session before then.
    """

    @classmethod
    def load_replay_context(cls, *args, **kwargs):
        warnings.warn(
            "SignalReplayEngine is deprecated; use shared.online_replay.replay_session. "
            "Removal scheduled for Phase 12.",
            DeprecationWarning, stacklevel=2,
        )
        return cls()

    def sizing_replay(self, *args, **kwargs):
        warnings.warn(
            "SignalReplayEngine.sizing_replay is deprecated; use shared.online_replay.replay_session.",
            DeprecationWarning, stacklevel=2,
        )
        # Minimal compatibility shim — translates args to replay_session, returns matching shape.
        from shared.online_replay import replay_session
        ...
        return _legacy_shape_result

    def strategy_replay(self, *args, **kwargs):
        warnings.warn(
            "SignalReplayEngine.strategy_replay is deprecated; use shared.online_replay.replay_session.",
            DeprecationWarning, stacklevel=2,
        )
        from shared.online_replay import replay_session
        ...
        return _legacy_shape_result
```

### Test additions

**`tests/test_signal_replay_deprecation.py` (NEW):**

| Test | Assertion |
|---|---|
| `test_signal_replay_engine_emits_deprecation_warning` | `with warnings.catch_warnings(record=True): SignalReplayEngine.load_replay_context(...)`; assert `DeprecationWarning` recorded. |
| `test_b5_sensitivity_still_callable_via_stub` | Run sensitivity scan end-to-end (using the stub); assert no exceptions. |
| `test_phase7_modules_no_longer_import_signal_replay` | Static checks: `b3_pseudotrader`, `b6_auto_expansion` source contains no `SignalReplayEngine` reference. |
| `test_signal_replay_loc_reduced` | `wc -l shared/signal_replay.py` < 100 (stub-only). |

### Exit criteria

- All deprecation tests pass.
- Sensitivity scan still works via stub (Phase 12 will migrate).

### Rollback procedure

1. `git revert <commit>` — restores full `SignalReplayEngine` class.

---

## Batch 7.14 — G-OFF-016 verification suite + live-parity regression guard

**Status:** GO

### Spec citation

- **Design doc:** §4.3 (verification test that pins G-OFF-016 RESOLVED-in-fact).
- **Pass-2 open question:** O9 (live-parity baseline capture).

### Pre-flight checks

1. Batches 7.0–7.13 merged.
2. Capture pre-Phase-7 live-parity baseline before Phase 7 starts. (If Phase 7 is already in flight, capture from a pre-Phase-7 git tag.)

### Files + line ranges to modify

| File | Lines | Change |
|---|---|---|
| `tests/test_g_off_016_resolution.py` | NEW | Comprehensive G-OFF-016 verification suite |
| `tests/fixtures/phase7_live_parity_baseline.json` | NEW | Sealed baseline of `_run_session(session_id=1)` published signals |
| `tests/test_phase7_live_parity.py` | NEW | Live-parity regression guard |

### Test additions

**`tests/test_g_off_016_resolution.py` (NEW):**

| Test | Assertion |
|---|---|
| `test_captain_online_replay_invokes_live_b1` | Spy `b1_data_ingestion.run_data_ingestion`; call `captain_online_replay(d, using=...)`; assert spy was called with `market_data=` set to a `HistoricalMarketDataProvider` instance. |
| `test_captain_online_replay_invokes_live_b6` | Spy `b6_signal_output.run_signal_output`; assert called with `signal_sink=` set to `CapturingSignalSink`. |
| `test_captain_online_replay_invokes_live_b2_through_b5c` | Spies on B2/B3/B4/B5/B5B/B5C; assert each invoked once in order, exactly once per session. |
| `test_captain_online_replay_reads_d03_for_outcome` | Mock D03 with two rows: one signal has D03 row with known P&L, one does not; build pair series; assert matched outcome reflects seeded P&L; unmatched signal's outcome is `None`. |
| `test_pseudotrader_gate_does_not_use_signal_replay_engine` | Static: `b3_pseudotrader` does not import `SignalReplayEngine` (or it imports only the deprecation stub); confirm gate's call graph reaches `replay_session` not `SignalReplayEngine`. |
| `test_captain_online_replay_does_not_touch_redis` | Mock Redis at module level; run `captain_online_replay`; assert no Redis call. |
| `test_captain_online_replay_does_not_touch_topstep` | Mock `topstep_client`, `topstep_stream.quote_cache`; assert no read calls. |
| `test_replay_isolation_state_unchanged` | Capture `_seen` size + `_session_evaluated_today` before replay; run; assert unchanged. |

**`tests/test_phase7_live_parity.py` (NEW):**

| Test | Assertion |
|---|---|
| `test_live_session_byte_identical_to_pre_phase7_baseline` | Run `OnlineOrchestrator._run_session(session_id=1)` against sealed QuestDB fixture; capture signals; assert byte-identical to `tests/fixtures/phase7_live_parity_baseline.json`. |
| `test_b1_default_provider_is_live` | Call `run_data_ingestion(1)` (no kwargs); assert `LiveMarketDataProvider` was instantiated. |
| `test_b6_default_sink_is_redis` | Call `run_signal_output(...)` (no kwargs); assert `RedisSignalPublisher` was used. |

### Exit criteria

- All G-OFF-016 verification tests pass.
- Live-parity baseline captured and stored as a sealed fixture.
- Live `_run_session` produces byte-identical output to pre-Phase-7 baseline.
- G-OFF-016 status: **RESOLVED-in-fact-with-tests**.

### Rollback procedure

1. Test-only batch — delete `tests/test_g_off_016_resolution.py`, `tests/test_phase7_live_parity.py`, fixture.
2. No production code change.

---

## Cross-batch acceptance gate

Phase 7 ships when every batch above is merged AND the following gate passes:

| Gate | Verification |
|---|---|
| All in-batch tests pass | `pytest tests/` green per the standard PYTHONPATH invocation in CLAUDE.md. |
| F-22 closed | `test_pseudotrader_gate_does_not_use_signal_replay_engine` + `test_captain_online_replay_invokes_live_b1` (7.14). |
| F-23 closed | `test_pg09_builds_signal_outcome_pairs` + `test_captain_online_replay_reads_d03_for_outcome` (7.6 + 7.14). |
| F-24 closed | `test_pg10_step1_uses_retroactive_replay` (7.7). |
| F-25 closed | `test_pg10_step3_no_precomputed_pnl_branch` (7.8). |
| F-26 closed | `test_each_candidate_uses_own_oos` (7.10). |
| F-27 closed | `test_pbo_consumes_full_grid` (7.11). |
| F-28 closed | `test_dsr_uses_oos_sharpe` (7.9). |
| F-29 closed | `test_walkforward_uses_5_folds` + `test_walkforward_train_window_distinct_from_validation` (7.9). |
| G-OFF-016 RESOLVED-in-fact | `tests/test_g_off_016_resolution.py` full file green (7.14). |
| Live-parity invariant | `tests/test_phase7_live_parity.py::test_live_session_byte_identical_to_pre_phase7_baseline` green (7.14). |
| `SignalReplayEngine` no longer in Phase 7 modules | `test_phase7_modules_no_longer_import_signal_replay` (7.13). |
| GUI replay still works | `tests/test_replay_engine_refactor.py::test_b11_replay_runner_smoke` green (7.12). |
| Out-of-scope watch item Q-04 status | Documented in PR description; if unresolved, PG-11 batch left for Phase 4. |

---

## Change log of Stage-1 / Stage-1B decisions baked into this plan

| Decision | Source | Effect on plan |
|---|---|---|
| `signal_id STRING` to D03 (Phase 1.5 amend) | Stage 1B §0 D1, Q-15 | Batch 7.0 adds the column + `compact_questdb_tables.py` rerun + legacy backfill. |
| Function-shaped headless driver | Stage 1B §0 D2 | Batch 7.4 builds `replay_session` (function); no daemon/loop. |
| `MarketDataProvider` protocol (default-None for live path) | Stage 1B §0 D3 | Batches 7.1 (protocol) → 7.2 (B1 wires). Live behavior preserved at all existing call sites. |
| Explicit reset hooks; D23 LATEST ON migration parallel | Stage 1B §0 D4 | Batch 7.4 ships `replay_reset` + `_reset_seen` + 4 other hooks (per design §2.2). |
| `SignalSink` protocol; CB CRITICAL alerts captured | Stage 1B §0 D5 | Batch 7.3 wires sink. |
| Phase A → fast-forward OR-tracker → Phase B inline | Stage 1B §0 D6 | Batch 7.4 implements inline Phase B. |
| HMM state = current D26 (limitation) | Stage 1B §0 D7 | Documented in design doc; no test gating; revisit in Phase 10. |
| Single-user replay | Stage 1B §0 D8 | All replay calls thread `user_id`. |
| `SignalReplayEngine` deprecated, deleted in Phase 12 | Stage 1B §0 D9 | Batch 7.13 ships stub; Phase 12 deletes class. |
| `replay_engine.py` refactored in place | Stage 1B §0 D10 | Batch 7.12 rewires `run_replay`/`run_whatif` to `replay_session`. |
| `aim_retroactive_replay` standalone function | Stage 1B §0 D11 | Batch 7.7 adds `shared/aim_retroactive.py`. |
| Legacy D03 backfilled with `LEGACY-` UUIDs | Stage 1B §0 D12 / §5.4 | Batch 7.0 ships backfill script. |
| PBO uses S=8 (Q-16) | Decisions log §2 Resolved-by-spec | Batch 7.6 + 7.11 use S=8. |
| Q-04 (`blend_signal` consumer for PG-11) — out of scope | Stage 1A §6 | Watch item; documented in Out-of-scope dependencies above. |

---

*End of Phase 7 build plan. Cursor Composer 2: execute batches 7.0 → 7.14 in order. Open questions (O1–O9) resolve at the per-batch level; any that surface as architecture-level must escalate to Nomaan rather than be silently decided.*
