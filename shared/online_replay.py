"""Phase 7 — captain_online_replay infrastructure (Layer 1: protocols).

This module hosts the substitution-seam protocols used by ``captain_online``
B1–B6 to swap their live data, sink, and time sources for replay-friendly
implementations. Layer 2 (driver) and Layer 3 (PG-09 entry) are added in
Batch 7.4.

Live behaviour is preserved: B1 / b1_features / B6 default the relevant
kwargs to ``None`` and lazily fall back to the live concrete provider.
Replay paths construct their own provider chain explicitly and pass the
instances in.

See:
- ``docs2/audits/phase-ref-docs/phase-7/2026-04-27_phase7_design_captain_online_replay.md``
- Phase 7 build plan §1.1 / §2.1 / §2.3 / §3.2
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable, Protocol, runtime_checkable


@runtime_checkable
class MarketDataProvider(Protocol):
    """Substitution seam for B1's external market-data reads.

    Live impl wraps ``shared.topstep_client`` + ``topstep_stream.quote_cache``;
    historical impl reads QuestDB historical bar/volume tables.
    """

    def get_bars(
        self, asset_id: str, timeframe: str, start: datetime, end: datetime
    ) -> list[dict]: ...

    def get_current_quote(self, asset_id: str) -> dict | None: ...

    def get_current_session_volume(self, asset_id: str) -> int | None: ...

    def get_avg_session_volume_20d(self, asset_id: str) -> float | None: ...

    def get_prior_close(self, asset_id: str) -> float | None: ...

    def get_intraday_bars(
        self, asset_id: str, lookback_minutes: int
    ) -> list[dict] | None: ...

    def get_historical_session_volumes(
        self, asset_id: str, n_sessions: int
    ) -> list[int] | None: ...

    def get_daily_closes(
        self, asset_id: str, n_days: int
    ) -> list[float] | None: ...


@runtime_checkable
class SignalSink(Protocol):
    """Substitution seam for B6's Redis signal publish.

    Live impl publishes to ``STREAM_SIGNALS``; replay impl captures payloads
    in-memory.
    """

    def publish(self, channel: str, payload: dict) -> bool: ...

    def captured(self) -> list[dict]: ...


@runtime_checkable
class TimeProvider(Protocol):
    """Substitution seam for ``now_et()`` in B1/B6/orchestrator."""

    def now_et(self) -> datetime: ...


# --------------------------------------------------------------------------- #
# Layer 2 — driver (filled in by Batch 7.4).                                  #
# --------------------------------------------------------------------------- #


@dataclass
class ReplayParameters:
    """Parameter overrides applied during a replay session.

    Each field overrides the corresponding live state when set; ``None``
    falls through to whatever B1 loads from QuestDB.
    """

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
    market_data: "MarketDataProvider"
    signal_sink: "SignalSink"
    time_provider: "TimeProvider"
    reset_hooks: list[Callable[[], None]] = field(default_factory=list)
    parameter_overrides: dict[str, Any] = field(default_factory=dict)

    def __enter__(self) -> "OnlineReplayContext":
        replay_reset(self.reset_hooks)
        return self

    def __exit__(self, *exc: object) -> None:
        replay_reset(self.reset_hooks)


def replay_reset(reset_hooks: list[Callable[[], None]]) -> None:
    """Invoke each reset hook in registration order. Safe to call repeatedly."""
    for hook in reset_hooks:
        hook()


def default_reset_hooks() -> list[Callable[[], None]]:
    """The closed list of reset hooks (Stage 1B §2.2 D4).

    New hooks must amend the design doc, not silently extend in code.
    Only B5C's ``_seen`` set is registered for now; remaining hooks
    (aim_compute caches, b1_prefetch executor, orchestrator session state,
    quote_cache snapshot) are added by their owning batches.
    """
    hooks: list[Callable[[], None]] = []
    try:
        from captain_online.blocks.b5c_circuit_breaker import _reset_seen
        hooks.append(_reset_seen)
    except Exception:
        # captain_online package may not be importable in every test env.
        pass
    return hooks


def replay_session(
    session_date: date,
    session_id: int,
    ctx: OnlineReplayContext,
    parameters: ReplayParameters | None = None,
) -> ReplayResult:
    """Execute B1 → B6 chain for one session day under ``ctx``.

    Phase A (B1-B5C) runs once; Phase B (B6) inlines the OR-tracker
    fast-forward and AIM-15 recompute per design doc §0 D6.

    The full implementation is intentionally minimal in Layer 2 — replay
    callers (PG-09, PG-13, GUI replay) wrap this entry point. Per-batch
    rewires of ``run_pseudotrader``, walk-forward, and
    ``shared/replay_engine.py`` finish the mapping in 7.6 / 7.9 / 7.12.
    """
    from captain_online.blocks.b1_data_ingestion import run_data_ingestion
    from captain_online.blocks.b1_features import compute_all_features  # noqa: F401
    from captain_online.blocks.b2_regime_probability import (
        run_regime_probability,
    )
    from captain_online.blocks.b4_kelly_sizing import run_kelly_sizing  # noqa: F401
    from captain_online.blocks.b5_trade_selection import (  # noqa: F401
        run_trade_selection,
    )
    from captain_online.blocks.b5b_quality_gate import run_quality_gate  # noqa: F401
    from captain_online.blocks.b5c_circuit_breaker import (  # noqa: F401
        run_circuit_breaker_screen,
    )
    from captain_online.blocks.b6_signal_output import run_signal_output

    diagnostics: dict[str, Any] = {
        "reset_hooks_invoked": len(ctx.reset_hooks),
    }
    with ctx:
        b1 = run_data_ingestion(session_id, market_data=ctx.market_data)
        if b1 is None:
            return ReplayResult(
                session_date=session_date,
                session_id=session_id,
                signals=[],
                phase_a_outputs={},
                phase_b_outputs={},
                diagnostics={**diagnostics, "reason": "no_active_assets"},
            )

        if parameters is not None:
            b1 = _apply_parameter_overrides(b1, parameters)

        b2 = run_regime_probability(
            b1.get("active_assets", []),
            b1.get("features", {}),
            b1.get("regime_models", {}),
        )

        # Driver implementation continues here in batches 7.4 / 7.6.
        # For the initial Layer-2 stub we surface enough state for
        # tests to exercise the protocol surface. B3-B6 wiring is added
        # by the per-PG batches that consume this driver.
        b6 = run_signal_output(
            recommended_trades=[],
            available_not_recommended=[],
            account_recommendation={},
            account_skip_reason={},
            final_contracts={},
            asset_diagnostics={},
            session_id=session_id,
            signal_sink=ctx.signal_sink,
        )

    return ReplayResult(
        session_date=session_date,
        session_id=session_id,
        signals=ctx.signal_sink.captured(),
        phase_a_outputs={"b1": b1, "b2": b2},
        phase_b_outputs={"b6": b6},
        diagnostics=diagnostics,
    )


def captain_online_replay(
    d: date,
    *,
    using: ReplayParameters,
    user_id: str,
    asset: str | None = None,
    session_id: int | None = None,
) -> list[dict]:
    """Doc 32 PG-09 spec entry. Returns signals for session day ``d``
    under ``using`` parameters."""
    from shared.online_replay_providers import (
        CapturingSignalSink,
        FixedTimeProvider,
        HistoricalMarketDataProvider,
    )

    sid = session_id if session_id is not None else _infer_session_id(asset, d)
    session_open = _session_open_dt(d, sid)
    ctx = OnlineReplayContext(
        market_data=HistoricalMarketDataProvider(as_of=session_open),
        signal_sink=CapturingSignalSink(),
        time_provider=FixedTimeProvider(session_open),
        reset_hooks=default_reset_hooks(),
    )
    result = replay_session(d, sid, ctx, using)
    return result.signals


def _apply_parameter_overrides(b1_state: dict, params: ReplayParameters) -> dict:
    """Layer per-replay parameter overrides on top of B1's loaded state."""
    out = dict(b1_state)
    if params.locked_strategies is not None:
        out["locked_strategies"] = params.locked_strategies
    if params.aim_states is not None:
        out["aim_states"] = params.aim_states
    if params.aim_weights is not None:
        out["aim_weights"] = params.aim_weights
    if params.kelly_params is not None:
        out["kelly_params"] = params.kelly_params
    if params.ewma_states is not None:
        out["ewma_states"] = params.ewma_states
    if params.sizing_overrides is not None:
        out["sizing_overrides"] = params.sizing_overrides
    return out


def _infer_session_id(asset: str | None, d: date) -> int:
    """Default to NY (1) when caller does not specify; PG-09 always pins one."""
    return 1


def _session_open_dt(d: date, session_id: int) -> datetime:
    """Resolve session-open datetime in America/New_York for the given session."""
    from datetime import time as _time
    from zoneinfo import ZoneInfo

    et = ZoneInfo("America/New_York")
    if session_id == 1:
        return datetime.combine(d, _time(9, 30), tzinfo=et)
    if session_id == 2:
        return datetime.combine(d, _time(3, 0), tzinfo=et)
    return datetime.combine(d, _time(20, 0), tzinfo=et)
