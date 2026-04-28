---
title: Phase 7 Design — `captain_online_replay`
date: 2026-04-27
phase: 7
stage: 1B
status: PROPOSED — awaiting "design approved" before Pass 2 (implementation plan)
companion_to:
  - phase-ref-docs/phase-7/2026-04-27_phase7_stage1a_audit_pass.md
  - 2026-04-22_offline_spec_vs_code_audit copy.md
  - phase-ref-docs/phase-2/captain_offline_audit_decisions_2026-04-27.md
governs:
  - F-22, F-23, F-24, F-25, F-26, F-28, F-29 (Phase 7 fix targets)
  - G-OFF-016 (RESOLVED-in-fact, currently RESOLVED-on-paper-only)
purpose: Architectural design for the PG-09 / PG-10 / PG-13 pseudotrader chain rebuild around a real `captain_online_replay` driven by live online B1–B6 modules. This document is binding on the Pass 2 implementation plan; Pass 2 batches must conform.
---

# Phase 7 Design — `captain_online_replay`

This is the design pass for Phase 7 of the Captain Offline audit fix campaign. Once approved, every batch in `2026-04-27_phase7_pseudotrader_chain_build_plan.md` (Pass 2) must conform to this document. The Stage 1A audit pass identified twelve open design questions; this document closes them all.

---

## 0. Decisions baked in from Stage 1A approval

The user's Stage 1B clarifications, plus the §8.3 call I'm committing to here, form the constraint set this design satisfies.

| Stage 1A § | Topic | Decision |
|---|---|---|
| §8.1 | D03 ↔ signal_id | **`signal_id STRING` added to `p3_d03_trade_outcome_log`.** Implemented as a Phase 1.5 amendment, executed as Pass 2 Batch 0. Must land before any PG-09 metric work. |
| §8.2 | Driver shape | **Function-shaped headless driver.** No daemon `_command_listener`, no 1s `_session_loop`. Layered as: `OnlineReplayContext` (dataclass, isolation) → `replay_session(...)` (function, runs B1–B6) → `captain_online_replay(d, *, using=params)` (spec-named thin wrapper, signal-only return). |
| §8.3 | B1 substitution seam | **Abstract data provider protocol.** `MarketDataProvider` protocol with `LiveMarketDataProvider` (default; wraps `topstep_client` + `quote_cache`) and `HistoricalMarketDataProvider` (replay; QuestDB historical bar storage + synthesized session-open quotes). B1 + `b1_features` accept provider as parameter, default to live so all existing call sites keep working. **Rejected alternatives:** monkey-patching (test-only, can't satisfy GUI replay flow); `replay_mode=True` flag on `run_data_ingestion` (pollutes production code with branches, harder to test). |
| §8.4 | Reset policy | **Explicit reset hooks per replay run.** A `replay_reset()` function enumerates every module-level cache / dedup state and clears it at session start. The independent D23 LATEST ON migration (audit hygiene work) may shrink the contamination surface but does not replace this policy — replay must work even with `_seen` still in place. |
| §8.5 | B6 publish | No-op publish: replay context provides a `SignalSink` (capture-only) substituted for the live Redis publish path. No conditional branch in B6's code. |
| §8.6 | Phase A/B collapse | Replay invokes Phase A → fast-forwards OR-tracker bar evolution to OR-close using historical bars → invokes Phase B inline. No 1s polling. AIM-15 post-OR recompute is included. |
| §8.7 | HMM state at `d` | Use **current** D26 state for replay. Documented as a known limitation. Phase 10 (HMM) introduces D26 snapshots; until then, PG-09 retests of non-HMM-affecting parameters are unaffected. |
| §8.8 | Multi-user fan-out | **Single-user replay.** PG-09 retests run for the user whose strategy/AIM is being changed. PG-13 is per-asset (decayed_asset is global) and runs once per asset; downstream PG-10 invocation also runs single-user. |
| §8.9 | `SignalReplayEngine` | **Deprecation stub for one phase.** Phase 7 migrates `b3_pseudotrader.py` and `b6_auto_expansion.py` callers; `b5_sensitivity.py` caller is out of Phase 7 scope and is flagged for Phase 12 hygiene. The class is reduced to a `DeprecationWarning`-emitting stub at end of Phase 7 and deleted in Phase 12. |
| §8.10 | `replay_engine.py` refactor | **Refactor in place.** `run_replay` and `run_whatif` keep their public API; their internals are replaced by a thin orchestration over `replay_session`. The GUI replay (`captain-command/.../b11_replay_runner.py`) keeps using `run_replay` and inherits live-block parity automatically. |
| §8.11 | `aim_retroactive_replay` | **Standalone function in `shared/aim_retroactive.py` (new file).** Reuses `shared/aim_compute.py` for per-day modifier computation. Independent of `replay_session`; PG-10 calls it directly. Signature in Appendix A. |
| §8.12 | D11 / D06 schema | Phase 7 verifies `p3_d11_pseudotrader_results` (canonical_schemas.py L479) and `p3_d06_injection_decisions` columns cover Sharpe/PBO/DSR + per-day signal-level diff per Q-15. Any column additions land alongside the signal_id migration in Pass 2 Batch 0 (Phase 1.5 amendment). |

---

## 1. Architecture

### 1.1 Layering

The replay system is a three-layer stack. The names are precise; Pass 2 must use these literal identifiers.

```
┌────────────────────────────────────────────────────────────────────┐
│ Layer 3: SPEC-NAMED ENTRY                                          │
│   captain_online_replay(d, *, using=parameters) -> SignalSet       │
│     • Matches doc 32 PG-09 line 343/352 verbatim                   │
│     • Thin wrapper; constructs default historical context          │
│     • Returns signals only (matches spec's `signal = ...` shape)   │
└────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────────┐
│ Layer 2: DRIVER                                                    │
│   replay_session(                                                  │
│       session_date: date,                                          │
│       session_id: int,                                             │
│       ctx: OnlineReplayContext,                                    │
│       parameters: ReplayParameters,                                │
│   ) -> ReplayResult                                                │
│     • Executes B1 → B2 → B3 → B4 → B5 → B5B → B5C → B6             │
│     • Drives Phase A and inlined Phase B                           │
│     • Calls live block entry points unmodified                     │
└────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────────┐
│ Layer 1: CONTEXT                                                   │
│   @dataclass OnlineReplayContext                                   │
│     market_data: MarketDataProvider                                │
│     signal_sink: SignalSink                                        │
│     time_provider: TimeProvider                                    │
│     reset_hooks: list[Callable[[], None]]                          │
│     parameter_overrides: dict[str, Any]                            │
│     • Substitutes external I/O surfaces                            │
│     • Holds reset hook list applied at session start               │
└────────────────────────────────────────────────────────────────────┘
```

**Why three layers, not two:**
- Layer 3 is the spec name; PG-09/10/13 callers stay readable and traceable to spec.
- Layer 2 is the explicit driver; tests, debuggers, and the GUI replay use this.
- Layer 1 is the substitution surface; the *only* place external I/O is configured.

### 1.2 Live path isolation guarantees

Three invariants hold by construction. Pass 2 must include test assertions for each.

| Invariant | Mechanism | Test assertion |
|---|---|---|
| **Live B1–B6 entry points are unmodified semantically.** | The only changes to live block files are: (a) accepting new optional kwargs (`market_data`, `signal_sink`, `time_provider`) with `None` defaults that fall back to current behavior; (b) routing previously hardcoded I/O through these kwargs when supplied. No control-flow branches on `replay_mode` flags. | A "live parity" test seeds a controlled QuestDB snapshot, runs `_run_session(session_id=1)` via the live orchestrator with the new kwargs at default, captures published signals from a stub Redis publisher, and asserts byte-identical output to a baseline captured before Phase 7 begins. |
| **No replay run touches Redis, the live `quote_cache`, or TopstepX REST.** | `OnlineReplayContext` injects `HistoricalMarketDataProvider`, a capture-only `SignalSink`, and a fixed-time `TimeProvider`. The live providers are not even imported in the replay path. | A test runs `replay_session(...)` with a context whose providers' methods raise `RuntimeError` if called with parameters that would route to live infrastructure (e.g., `LiveMarketDataProvider` injected into `HistoricalMarketDataProvider`'s position). |
| **Replay state cannot leak into the live process.** | All module-level mutable state is enumerated in `replay_reset()`. Reset is invoked at the *start* of each replay session and at the *end* of replay, with the live process's state restored from a captured snapshot. | A test runs replay between two live `_run_session` calls and asserts `_session_evaluated_today`, B5C's `_seen`, any other tracked state are bit-identical before and after replay. |

### 1.3 What lives where

| File | Status | Role |
|---|---|---|
| `shared/online_replay.py` | **NEW** | Layer 1 + Layer 2: `OnlineReplayContext`, `MarketDataProvider`, `SignalSink`, `TimeProvider`, `replay_session`, `replay_reset`. |
| `shared/online_replay_providers.py` | **NEW** | Concrete provider implementations: `LiveMarketDataProvider`, `HistoricalMarketDataProvider`, `RedisSignalPublisher`, `CapturingSignalSink`, `LiveTimeProvider`, `FixedTimeProvider`. Split from the protocol module so live and historical implementations don't import each other. |
| `shared/aim_retroactive.py` | **NEW** | `aim_retroactive_replay(...)` for PG-10 Step 1. |
| `captain-offline/.../b3_pseudotrader.py` | **MODIFIED** | `captain_online_replay(d, *, using=parameters)` rewritten as Layer 3 wrapper. `run_signal_replay_comparison` retired; `run_pseudotrader` uses Layer 3. Metrics rebuilt from D03 realised P&L. |
| `captain-offline/.../b4_injection.py` | **MODIFIED** | `_compute_aim_adjusted_edge` calls `aim_retroactive_replay`. Step 3 calls `pseudotrader_compare` which internally invokes `replay_session` for both candidate and baseline. |
| `captain-offline/.../b6_auto_expansion.py` | **MODIFIED** | GA fitness via `replay_session` (not `SignalReplayEngine`). DSR computed from holdout `oos_result.sharpe`. Walk-forward train + validate windows used. Per-candidate `oos` returns passed to PG-10. |
| `captain-online/.../b1_data_ingestion.py` | **MODIFIED** | Accepts `market_data: MarketDataProvider | None = None`. Default `None` instantiates `LiveMarketDataProvider` internally — preserves current behavior at every existing call site. |
| `captain-online/.../b1_features.py` | **MODIFIED** | All `topstep_client.get_bars()`, `quote_cache[...]`, `_get_intraday_bars()` calls routed through the provider when supplied. |
| `captain-online/.../b6_signal_output.py` | **MODIFIED** | Accepts `signal_sink: SignalSink | None = None`. Default behavior (Redis publish) unchanged when `None`. |
| `captain-online/.../b5c_circuit_breaker.py` | **MODIFIED** | Module-level `_seen` set wrapped in a `_get_seen()` accessor that the reset hook can clear cleanly. |
| `shared/replay_engine.py` | **MODIFIED** | `run_replay` and `run_whatif` reduced to thin wrappers over `replay_session`. Parallel B-block logic deleted. ~600 lines deleted. |
| `shared/signal_replay.py` | **MODIFIED** | `SignalReplayEngine.sizing_replay` and `strategy_replay` reduced to deprecation stubs that call `replay_session` and emit `DeprecationWarning`. Class slated for deletion in Phase 12. |
| `shared/canonical_schemas.py` | **MODIFIED** | `signal_id STRING` added to `p3_d03_trade_outcome_log`. D11 / D06 columns reviewed and amended if needed. |
| `captain-online/.../b7_position_monitor.py` | **MODIFIED** | `_write_trade_outcome` accepts and persists `signal_id`. |
| `captain-command/.../blocks/b1_core_routing.py` (or `_handle_taken_skipped` site) | **MODIFIED** | Persists `signal_id` from incoming signal envelope into the open-position dict. |
| `scripts/paper_trader.py` | **MODIFIED** | `_log_trade_open` / `_log_trade_close` accept and persist `signal_id`. |
| `shared/trade_source.py` | **MODIFIED** | Synthetic seeder generates a UUID for `signal_id` per row (or accepts one if the source data has it). |

---

## 2. Replay harness shape

### 2.1 Public API

```python
# shared/online_replay.py

from datetime import date, datetime
from typing import Protocol, Callable, Any
from dataclasses import dataclass, field

# ────────────────────────────────────────────────────────────────────
# Layer 1: protocols and context
# ────────────────────────────────────────────────────────────────────

class MarketDataProvider(Protocol):
    """Substitution seam for B1's external market data reads.

    Live implementation wraps shared.topstep_client + topstep_stream.quote_cache.
    Historical implementation reads from QuestDB historical bar storage and
    synthesizes session-open quotes from the bars.
    """
    def get_bars(
        self,
        asset_id: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[dict]: ...

    def get_current_quote(self, asset_id: str) -> dict | None: ...

    def get_current_session_volume(self, asset_id: str) -> int | None: ...

    def get_avg_session_volume_20d(self, asset_id: str) -> float | None: ...

    def get_prior_close(self, asset_id: str) -> float | None: ...

    # …any other read surface that B1 / b1_features touch today.
    # The exhaustive list is enumerated in §3.2.

class SignalSink(Protocol):
    """Substitution seam for B6's Redis signal publish."""
    def publish(self, channel: str, payload: dict) -> bool: ...
    def captured(self) -> list[dict]: ...  # for replay; returns [] for live

class TimeProvider(Protocol):
    """Substitution seam for now_et() and datetime.now(...) in B1/B6/orchestrator."""
    def now_et(self) -> datetime: ...

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
        replay_reset(self.reset_hooks)  # symmetric reset on exit


# ────────────────────────────────────────────────────────────────────
# Layer 2: driver
# ────────────────────────────────────────────────────────────────────

@dataclass
class ReplayParameters:
    """Strategy / AIM parameters under test. Replaces the live D00/D01/D02
    columns when applied. None values preserve live values."""
    locked_strategies: dict[str, dict] | None = None  # asset → strategy
    aim_states: dict | None = None
    aim_weights: dict | None = None
    kelly_params: dict | None = None
    ewma_states: dict | None = None
    sizing_overrides: dict[str, float] | None = None
    # …closed set; matches the dict B1 returns.

@dataclass
class ReplayResult:
    session_date: date
    session_id: int
    signals: list[dict]                # captured from signal_sink
    phase_a_outputs: dict              # B1 → B5C dict snapshots
    phase_b_outputs: dict              # post-OR B6 outputs
    diagnostics: dict                  # timings, reset evidence, errors

def replay_session(
    session_date: date,
    session_id: int,
    ctx: OnlineReplayContext,
    parameters: ReplayParameters | None = None,
) -> ReplayResult:
    """Run the live B1→B6 chain for one session day under `ctx`.
    
    No daemon, no polling. Phase A and Phase B execute synchronously.
    """

def replay_reset(reset_hooks: list[Callable[[], None]]) -> None:
    """Invoke each reset hook. Safe to call repeatedly."""


# ────────────────────────────────────────────────────────────────────
# Layer 3: spec-named entry
# ────────────────────────────────────────────────────────────────────

def captain_online_replay(
    d: date,
    *,
    using: ReplayParameters,
    user_id: str,
    asset: str | None = None,
    session_id: int | None = None,
) -> list[dict]:
    """PG-09 spec entry. Returns signals for session day `d` under `using` params.
    
    Constructs a default historical OnlineReplayContext, calls replay_session,
    returns the signals slice of the result. Single-user (per §8.8).
    """
```

### 2.2 Reset hooks — the explicit list

`replay_reset` invokes each registered hook in registration order. The minimum hook set, derived from Stage 1A §2:

| Hook | Targets | Justification |
|---|---|---|
| `_reset_b5c_seen()` | `b5c_circuit_breaker._seen` (L2017) | Module-level dedup set; carries D23-write tracking across sessions. |
| `_reset_aim_compute_caches()` | Any LRU caches in `shared/aim_compute.py` | Audit-driven enumeration in Pass 2 — no current evidence of caches but defense-in-depth. |
| `_reset_b1_prefetch_executor()` | `b1_data_ingestion._prefetch_market_data` ThreadPoolExecutor pool | Threads in pools survive across calls; safer to drain in replay. |
| `_reset_orchestrator_session_state()` | `_session_evaluated_today`, `_pending_sessions` | Replay must not leave evidence that "session X was already run today" when live process resumes. |
| `_reset_quote_cache_snapshot()` | `topstep_stream.quote_cache` | Replay snapshots and restores; never mutates the live cache, but the historical provider may set its own internal cache that needs clearing between sessions. |

The hook list is final at design time. New hooks added during Pass 2 implementation must be registered here in this design doc via amendment, not silently in code.

### 2.3 Bar / quote substitution

`HistoricalMarketDataProvider` reads from existing QuestDB tables. No new tables introduced.

| Method | Backing source |
|---|---|
| `get_bars(asset_id, "1m", start, end)` | `p3_d29_session_bars` (or whichever 1-min bar table exists today; verified during Pass 2 Batch 0). Falls back to `bar_cache.py` SQLite for cached fetches. |
| `get_bars(asset_id, "1d", start, end)` | `p3_d30_daily_ohlcv`. |
| `get_current_quote(asset_id)` | Synthesized from the most recent 1-min bar before `time_provider.now_et()`: `{bid: bar.open, ask: bar.open, bid_size: 1, ask_size: 1, ts: bar.ts}`. |
| `get_current_session_volume(asset_id)` | Sum of 1-min bar volumes within current session window up to `time_provider.now_et()`. |
| `get_avg_session_volume_20d(asset_id)` | `p3_d29_session_bars` aggregate over prior 20 sessions. |
| `get_prior_close(asset_id)` | `p3_d30_daily_ohlcv` close on `session_date - 1`. |

The exhaustive method list and exact backing tables are confirmed in Pass 2 Batch 1 (provider implementation). Anything that turns out to require a table that doesn't exist gets flagged then; this design assumes the existing online flow's reads are all on D29/D30/D31/D33 (which the Stage 1A audit confirmed).

### 2.4 Signal capture sink

```python
class CapturingSignalSink:
    def __init__(self):
        self._captured: list[tuple[str, dict]] = []
    def publish(self, channel: str, payload: dict) -> bool:
        self._captured.append((channel, payload))
        return True
    def captured(self) -> list[dict]:
        return [p for _, p in self._captured]
```

The replay context owns one `CapturingSignalSink` per session run. `ReplayResult.signals` is `sink.captured()`. The CB-Layer-failure CRITICAL alert publish (`b6_signal_output.py:180–193`) is also intercepted here; replay does not page operators.

---

## 3. Per-session reconstructible state

This section answers: "before `replay_session(d, session_id, ctx, parameters)` runs B1, what state must be in place, and where does it come from?"

### 3.1 State categories

| Category | Source for replay | Notes |
|---|---|---|
| **Asset universe** (D00) | Live D00 (current) | We don't have point-in-time D00 snapshots. Acceptable because PG-09 retests are short-window; asset universe rarely flips inside a retest window. **Limitation logged.** |
| **AIM states / weights** (D01, D02) | `parameters.aim_states`, `parameters.aim_weights` if provided; else live D01/D02 | The whole *point* of PG-09 is to replay under proposed params — those come from `parameters`. |
| **Kelly params / EWMA** (D12, D05) | `parameters.kelly_params`, `parameters.ewma_states` if provided; else live | Same as above. |
| **Locked strategies** (D00 JSON, D17) | `parameters.locked_strategies` if provided; else live | PG-10 candidate strategies replace live values for "candidate" replays. |
| **Sizing overrides** (D12) | `parameters.sizing_overrides` if provided; else live | Live values default in PG-09 retests. |
| **TSM state** (D08) | Live D08 | TSM state is account-shape; per-day reconstruction would require D08 history which doesn't exist in tabular form. Frozen to live for replay. |
| **Capital silo** (D16) | Live D16 | Same rationale as TSM. Replay tests are insensitive to silo state for short windows. |
| **Regime models** (D00 JSON) | Live D00 | Stable across sessions. |
| **HMM state** (D26) | Live D26 (per §8.7) | Documented limitation. Phase 10 will add D26 snapshots. |
| **Open positions** | **Empty list.** | Replay starts each session with no positions. PG-09's `outcome = actual_trade_outcome(d)` reads D03 directly; replay does not simulate position lifecycle. |
| **Bars (1m, 1d)** | `MarketDataProvider` (HistoricalMarketDataProvider → D29, D30) | Per §2.3. |
| **Quote snapshot at session-open** | `MarketDataProvider.get_current_quote(...)` synthesized from 1-min bars | Per §2.3. |
| **Time** | `FixedTimeProvider(session_date + session_open_hours)` | `now_et()` returns a fixed timestamp at the session-open boundary. Tick advancement during Phase B (§4) advances `FixedTimeProvider`'s internal pointer. |

### 3.2 The exhaustive read surface that the provider must cover

Pass 2 Batch 1 will build `HistoricalMarketDataProvider`. The full method list is derived from grepping every `topstep_client.*`, `quote_cache[...]`, `_get_intraday_bars(...)`, `_get_daily_closes(...)`, `_get_recent_5min_vol(...)`, `_get_session_volume(...)`, `_get_historical_session_volumes(...)` site in `b1_data_ingestion.py` and `b1_features.py`. The Stage 1A audit summary listed these; the Pass 2 batch will turn each into a `MarketDataProvider` method.

**Forbidden in `MarketDataProvider`:** anything that mutates state, anything that publishes (alerts, signals), anything that writes to QuestDB. The provider is read-only by contract.

### 3.3 What the parameter object overrides

`ReplayParameters` is a closed set: it's exactly the dict shape `b1_data_ingestion.run_data_ingestion(...)` returns. The replay driver applies overrides like this:

```python
def replay_session(session_date, session_id, ctx, parameters):
    with ctx:
        live_state = run_data_ingestion(session_id, market_data=ctx.market_data)
        if parameters is not None:
            live_state = _apply_overrides(live_state, parameters)
        # … chain into B2 with live_state
```

This means PG-09's "current vs proposed" comparison runs `replay_session` twice for each `d`: once with `parameters=None` (current), once with `parameters=PROPOSED` (proposed).

---

## 4. G-OFF-016 RESOLVED mapping

Stage 1A flagged that doc 32 line 795 marks G-OFF-016 `CRITICAL RESOLVED` but the underlying code (F-22) does not satisfy the spec. Phase 7 turns the on-paper resolution into an in-fact resolution. This section spells out the mapping from the spec's RESOLVED claim to the Pass 2 batches that satisfy it.

### 4.1 What the spec claims

> `[[G-OFF-016_pseudotrader_no_replay|G-OFF-016 — No Pipeline Replay in Pseudotrader]] (PG-09 §1-2) — CRITICAL RESOLVED`
> — `docs2/spec-docs-02/offline/32_P3_Offline_Full_Pseudocode.md:795`

PG-09 §1-2:

> ```
> -- Phase 1: Replay WITHOUT update
> baseline_results = []
> FOR EACH day d IN historical_window:
>     signal = captain_online_replay(d, using=CURRENT_parameters)
>     outcome = actual_trade_outcome(d)
>     baseline_results.append({signal, outcome})
> 
> -- Phase 2: Replay WITH update
> updated_results = []
> FOR EACH day d IN historical_window:
>     signal = captain_online_replay(d, using=PROPOSED_parameters)
>     outcome = actual_trade_outcome(d)
>     updated_results.append({signal, outcome})
> ```
> — `docs2/spec-docs-02/offline/32_P3_Offline_Full_Pseudocode.md:343–354`

Two requirements:
1. `captain_online_replay(d, using=parameters)` exists and runs the *real* online B1–B6 against historical bars.
2. `actual_trade_outcome(d)` exists and returns strict realised P&L from D03 paired with the originating signal.

### 4.2 Pass 2 batch ↔ requirement mapping

| Spec requirement | Pass 2 batch | Verification |
|---|---|---|
| `captain_online_replay` exists as a function | Batch 4 | Batch 4 introduces `shared/online_replay.py` with `captain_online_replay`, `replay_session`, `OnlineReplayContext`. |
| `captain_online_replay` runs *real* online B1–B6 | Batches 2, 3, 4 | Batch 2 introduces `MarketDataProvider` and modifies B1 + b1_features to accept it. Batch 3 wires `SignalSink` into B6. Batch 4 chains B1→B6 in `replay_session` calling the live entry points (`run_data_ingestion`, `run_regime_probability`, `run_aim_aggregation`, `run_kelly_sizing`, `run_trade_selection`, `run_quality_gate`, `run_circuit_breaker_screen`, `run_signal_output`). |
| `captain_online_replay` runs against historical bars | Batch 2 | `HistoricalMarketDataProvider` reads from D29 / D30 / D31 / D33. |
| `actual_trade_outcome(d)` returns realised P&L from D03 | Batch 5 | New helper in `shared/trade_source.py` (or `b3_pseudotrader.py`); reads D03 by `(user_id, asset, entry_time within session_date)` and returns realised P&L paired with `signal_id`. |
| `{signal, outcome}` pairs construct correctly | Batch 0 + Batch 5 | Batch 0 adds `signal_id` to D03. Batch 5 builds the join: replay produces signals with `signal_id`; D03 readers join on `signal_id`. If a signal has no D03 row (skipped, missed fill), `outcome=None` and that row is excluded from metrics. |
| PG-09 metrics computed from the {signal, outcome} pairs | Batch 6 | Sharpe, PBO (S=8), DSR rebuilt in `b3_pseudotrader.py` using the joined pair series. F-23 closed. |
| The pseudotrader gate uses `captain_online_replay` end-to-end | Batch 7 | `run_signal_replay_comparison` retired; orchestrator wires the gate to `run_pseudotrader` which calls `captain_online_replay`. F-22 closed. |

### 4.3 Verification test that pins G-OFF-016 RESOLVED-in-fact

Pass 2 must include a test, naming convention `tests/test_g_off_016_resolution.py`, with at minimum:

- **`test_captain_online_replay_invokes_live_b1`** — patch `b1_data_ingestion.run_data_ingestion` with a tracking spy, call `captain_online_replay(d, using=...)`, assert the spy was called with `market_data=` set to a `HistoricalMarketDataProvider`.
- **`test_captain_online_replay_invokes_live_b6`** — same pattern, `b6_signal_output.run_signal_output` spy, assert it was called with `signal_sink=` set to `CapturingSignalSink`.
- **`test_captain_online_replay_reads_d03_for_outcome`** — assert the resulting `{signal, outcome}` pairs have `outcome.gross_pnl` and `outcome.pnl` reading from D03 by `signal_id` (mock D03 with two rows; one signal has a D03 row with known P&L, one does not; assert the matched outcome reflects the seeded P&L and the unmatched signal's outcome is `None`).
- **`test_pseudotrader_gate_does_not_use_signal_replay_engine`** — import `b3_pseudotrader`; assert no reference to `SignalReplayEngine` exists in the gate's call graph (static check on the module's imports is sufficient).
- **`test_live_path_unchanged_after_phase7`** — run a baseline live `_run_session` capture, install all Phase 7 changes, run again, assert byte-identical output. (Live parity guard.)

Together these convert G-OFF-016 from "marked RESOLVED on paper" to "RESOLVED with regression coverage".

---

## 5. P&L source per Q-15

### 5.1 The contract

Q-15 (decisions log §2 Group C, line 59):

> `actual_trade_outcome(d)` = strict realised P&L from `p3_d03_trade_outcome_log` for that session day. Theoretical replay P&L is not acceptable.

This forces three things:
1. D03 rows must be findable by `(user_id, asset, session_date)` — already true.
2. D03 rows must be matchable to the signals that produced them — **not currently true** (Stage 1A §4.3).
3. The matching must be unambiguous when multiple signals produce trades on the same day.

### 5.2 The signal_id flow

```
B6 signal output                     Command (B1 routing)               B7 position monitor
  ─────────────                       ──────────────────                 ──────────────────
  signal_id = uuid4()                 receive signal envelope            on TP/SL hit:
  payload = {                         persist to open_positions[acct]:    write D03 row with:
    signal_id: signal_id,               { …, signal_id: payload.signal_id, …}    signal_id =
    asset, direction, …               on TAKEN: copy to broker order        position.signal_id
  }                                   on FILL: position.signal_id stays
  signal_sink.publish(...)
```

Three writers, three changes:

| File:func | Change |
|---|---|
| `b6_signal_output.py:_build_signal` (~L84) | Already generates UUID; persist as `signal_id` in payload (currently embedded as `signal_id` in the live signal — verify in Pass 2 Batch 0). |
| `captain-command/.../b1_core_routing.py` (`_handle_taken_skipped` site, orchestrator L872–920 in online; equivalent site in command) | Persist `signal_id` from incoming envelope into the open-position dict before broker order goes out. |
| `captain-online/.../b7_position_monitor.py:_write_trade_outcome` (L303–316) | Read `signal_id` from the position; write to D03. |
| `scripts/paper_trader.py:_log_trade_open` (L393), `_log_trade_close` (L416) | Accept and persist `signal_id`. Paper trader owns its own signal generator; if generator doesn't emit IDs, fabricate UUIDs at open time. |
| `shared/trade_source.py:seed_d03_from_synthetic` (L295) | Generate UUID per row; or accept caller-supplied IDs. |

### 5.3 `actual_trade_outcome(d)` shape

```python
def actual_trade_outcome(
    d: date,
    *,
    user_id: str,
    asset: str | None = None,
    signal_id: str | None = None,
) -> RealisedOutcome | None:
    """Return strict realised P&L from D03 for session day `d`.
    
    If `signal_id` is provided, return the outcome for that specific signal
    (or None if not found). Otherwise return the aggregate outcome for
    (user_id, asset) on day `d`.
    
    Realised P&L = D03.pnl (net of commission). Caller can also access
    .gross_pnl and .commission from the returned struct.
    """

@dataclass
class RealisedOutcome:
    signal_id: str
    trade_id: str
    pnl: float            # D03.pnl  (realised, net of commission)
    gross_pnl: float      # D03.gross_pnl  (realised, pre-commission)
    commission: float
    contracts: int
    entry_price: float
    exit_price: float
    entry_time: datetime
    exit_time: datetime
    direction: int
    regime_at_entry: str
```

Lives in `shared/trade_source.py` (alongside the existing trade-source helpers) or in a new `shared/d03_reader.py`. Pass 2 Batch 5 picks one; preference is `shared/trade_source.py` since it already has D03-write helpers.

### 5.4 Pair construction in PG-09

The `{signal, outcome}` pair construction in `b3_pseudotrader.run_pseudotrader` (Pass 2 Batch 6 rewrites this site):

```python
def _build_pair_series(
    historical_window: tuple[date, date],
    parameters: ReplayParameters | None,
    user_id: str,
) -> list[dict]:
    """For each session day in window, replay → signals → D03 outcome lookup → pair."""
    pairs = []
    start, end = historical_window
    for d in iter_session_days(start, end):
        signals = captain_online_replay(d, using=parameters or _live_parameters(),
                                        user_id=user_id)
        for signal in signals:
            outcome = actual_trade_outcome(
                d, user_id=user_id,
                asset=signal["asset"],
                signal_id=signal["signal_id"],
            )
            pairs.append({"signal": signal, "outcome": outcome})
    return pairs
```

**Edge cases:**
- Signal without D03 row (CB rejected, skipped by user, broker rejection): `outcome=None`. Excluded from Sharpe/PBO/DSR (signal didn't trade — counting it would conflate signal quality with execution quality).
- D03 row without matching signal_id (legacy data, paper trader without IDs): the signal and outcome don't pair; the row is invisible to PG-09. **Backfill consideration:** during Pass 2 Batch 0, write a one-shot script that generates synthetic UUIDs for legacy D03 rows (`signal_id IS NULL`) so the join doesn't break PG-09 backwards-window retests. Synthetic IDs are tagged with a `LEGACY-` prefix so Pass 2 Batch 5 can distinguish.

### 5.5 Metric computation

Sharpe / PBO (S=8 per Q-16) / DSR all consume the `{signal, outcome}` pair series:

- **Sharpe**: realised returns series = `[outcome.pnl / outcome.contracts for pair in pairs if pair.outcome is not None]`. Time index = `entry_time`.
- **PBO (S=8)**: requires multi-config returns — the proposed-vs-current pair sets feed in as the two columns of a CSCV grid widened by Pass 2's grid-construction logic (out of scope for this design — Batch 6 spells it out).
- **DSR**: computed from the realised Sharpe + skew/kurtosis of the realised return series + `N_trials`.

No metric reads anything except D03 realised P&L and the captured signal envelope. F-23 closed by construction.

---

## 6. Open design questions for Pass 2

The questions Stage 1B closed are listed in §0. The questions remaining open — for Pass 2 to resolve at the per-batch level, not at the architecture level — are:

1. **D11 / D06 column completeness.** Pass 2 Batch 0 verifies `p3_d11_pseudotrader_results` has columns for `sharpe_baseline`, `sharpe_updated`, `sharpe_improvement`, `pbo`, `dsr`, `recommendation`, plus a JSON column for the per-day pair series (or a separate `p3_d11a_pseudotrader_pairs` companion table). If columns missing, Batch 0 adds them.
2. **Backfill policy for legacy D03 rows.** §5.4 sketches a `LEGACY-` UUID backfill. Pass 2 Batch 0 confirms this is acceptable to Nomaan, or escalates if real-trade compliance requires a different approach.
3. **Bar table identity.** §2.3 names `p3_d29_session_bars` and `p3_d30_daily_ohlcv`. Pass 2 Batch 1 confirms exact names against `canonical_schemas.py` and grep — Stage 1A audit referenced these but did not pin the exact identifier.
4. **`p3_d29_session_bars` historical depth.** PG-09 retests use `historical_window` typically 30–252 days. If D29 doesn't go back that far, Batch 1 adds a backfill from TopstepX (one-shot script) or marks the limitation.
5. **`replay_engine.run_replay`'s public callers.** Stage 1A confirmed `b11_replay_runner.py` consumes `run_replay`. Pass 2 Batch 8 (replay_engine.py refactor) verifies no other callers exist that would break under the in-place refactor; if they exist, the refactor is staged.
6. **PG-13 rolling-fold parameters.** F-29 requires "rolling folds" but doc 32 doesn't pin the fold count or step. Pass 2 Batch 9 (PG-13 walk-forward fix) picks reasonable defaults (e.g., 5 folds, expanding window) and documents them; Isaac can correct in a follow-up amendment if wrong.
7. **`aim_retroactive_replay` historical feature loader.** Appendix A names `shared/aim_compute.py` as the dependency; Pass 2 Batch 10 (PG-10 Step 1 fix) verifies the historical feature loader can replay AIM modifiers without B1's full setup. If it can't, the function loads features via `replay_session` and discards everything but the AIM modifier — still cheaper than full B1–B6.
8. **D03 `signal_id` index.** Pass 2 Batch 0 decides whether to add a SYMBOL index on `signal_id` (frequent join column) or rely on QuestDB's default partition behavior. QuestDB pattern is to make join keys SYMBOL when cardinality is low; `signal_id` is high-cardinality (UUID per signal), so STRING is correct, but the `actual_trade_outcome` lookup needs to be efficient — possibly add a secondary index or accept `(user_id, entry_time)` scan.
9. **PG-11 `blend_signal` consumer (Q-04 watch item).** Stage 1A flagged this as a Phase 4 concern not blocking Phase 7. Pass 2 documents the dependency: PG-10 emits ADOPT decisions; PG-11 acts on them. If Q-04 is unresolved when Pass 2 ships, PG-11 batch is blocked but PG-10 batches stay green.

---

## Appendix A — `aim_retroactive_replay` signature

```python
# shared/aim_retroactive.py

def aim_retroactive_replay(
    aim_id: int,                            # 1..16; 7 returns disabled per Q-24
    candidate_strategy: dict,               # the strategy under consideration
    historical_window: tuple[date, date],
    *,
    user_id: str,
    asset: str,
) -> list[tuple[date, float]]:
    """Per-day modifier series for AIM `aim_id` against `candidate_strategy`'s
    feature inputs over `historical_window`.
    
    For each session day `d` in the window:
      1. Load historical features for `asset` on `d` from QuestDB (D29/D30/D31/D33).
      2. Compute AIM `aim_id`'s modifier using `candidate_strategy`'s thresholds
         and regime classifier. Reuses shared/aim_compute.py per-AIM modifier
         functions (e.g., compute_aim01_vrp, compute_aim03_gex, ...).
      3. Return (d, modifier).
    
    Returns the series. PG-10 Step 1 aggregates these into
    `retroactive_modifiers[aim_id]` and feeds Step 2's expected-edge calc.
    """
```

This function is intentionally independent of `replay_session` — it does not run B1–B6. It only computes the AIM modifier for historical feature snapshots, which is cheap.

---

## Appendix B — Schema impact summary

Phase 1.5 amendment (Pass 2 Batch 0):

```sql
-- canonical_schemas.py p3_d03_trade_outcome_log: add column
ALTER TABLE p3_d03_trade_outcome_log
  ADD COLUMN signal_id STRING;

-- (deferred to Batch 0 if needed) p3_d11_pseudotrader_results column adds
ALTER TABLE p3_d11_pseudotrader_results
  ADD COLUMN sharpe_baseline DOUBLE,
  ADD COLUMN sharpe_updated  DOUBLE,
  ADD COLUMN dsr_value       DOUBLE;
-- (only if columns missing — verify in Batch 0)

-- (deferred to Batch 0 if needed) p3_d06_injection_decisions
-- (verify schema covers expected_new, expected_current, recommendation,
--  pbo, dsr, transition_days, tracking_days)
```

**Migration tactic:** QuestDB does not support ALTER TABLE on partitioned tables in a way that's safe under load. The Phase 1 plan documented `compact_questdb_tables.py` as the migration mechanism (per memory observation 2838). Batch 0 follows that pattern — **does not** introduce new ALTER TABLE infrastructure (per memory 3007).

---

## Appendix C — `SignalReplayEngine` deprecation timeline

| Phase | Action |
|---|---|
| Phase 7 (this phase) | `b3_pseudotrader.py` and `b6_auto_expansion.py` migrated to `replay_session`. `SignalReplayEngine.sizing_replay` and `strategy_replay` reduced to deprecation stubs that call `replay_session` and emit `DeprecationWarning`. |
| Phase 12 (hygiene) | `b5_sensitivity.py` migrated. `SignalReplayEngine` class deleted. `shared/signal_replay.py` either deleted or reduced to a one-line shim that raises `ImportError` with migration guidance. |

Out-of-scope migrations (any caller not in the above list) must be documented in Pass 2 Batch 1 with a "still calls deprecated `SignalReplayEngine`" note for Phase 12 to pick up.

---

## Cross-references

- Stage 1A audit pass: `phase-ref-docs/phase-7/2026-04-27_phase7_stage1a_audit_pass.md`
- Audit findings: `2026-04-22_offline_spec_vs_code_audit copy.md` F-22…F-29
- Decisions log: `phase-ref-docs/phase-2/captain_offline_audit_decisions_2026-04-27.md` §2 Group C, §3.2, §5 Phase 7
- Spec authority: `docs2/spec-docs-02/offline/32_P3_Offline_Full_Pseudocode.md` PG-09 (L337–378), PG-10 (L385–413), PG-11 (L416–442), PG-13 (L498–541), Audit Resolutions (L794–795)
- Online spec: `docs2/spec-docs-02/online/33_P3_Online_Full_Pseudocode 1.md` PG-21…PG-26
- D03 schema: `shared/canonical_schemas.py:398–427`
- D11 schema: `shared/canonical_schemas.py:479…`

---

*End of design doc. Awaiting "design approved" before generating Pass 2 implementation plan.*
