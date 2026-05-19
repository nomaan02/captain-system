# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""ON-B7B: NKD trailing-stop ratchet — NKD pivot 2026-05.

Called every 10s from the online orchestrator's ``_run_position_monitor``
AFTER ``monitor_positions`` has resolved any TP_HIT / SL_HIT exits. Walks
the subset of open positions where ``is_nkd_trail == True`` and ratchets
the broker-side STOP order toward entry as the trade earns PnL.

3-phase ratchet:
  Phase A  pnl <  2000           -> stop @ d_init ($1025 for all NKD trades)
  Phase B  pnl <  3000           -> stop @ $1000 behind mark (flat step)
  Phase C  pnl <  4450           -> stop @ $450  behind mark (tight trail)
  TP_HIT   pnl >= 4450           -> no further modify (LIMIT TP fills)

Jitter J (Isaac tower only, INSTANCE_PARITY=="1") is added in dollars
to the SL buffer sent to the broker AND to the TP dollar target at B6
signal placement. Phase boundaries ($2000 / $3000 / $4450) are NOT
jittered — they stay clean for both towers.

Degenerate case: when ``snapped_d_init < 1000`` Phase B buffer is floored
at d_init so the stop never retreats.

Ratchet enforcement: the stop is recomputed STATELESSLY each poll, then
compared against the previously-stored stop. The "more conservative"
stop wins (LONG -> max, SHORT -> min) so the broker order never weakens.

Persistence: every modify attempt (success OR failure) appends a row to
``p3_d34_nkd_trail_state`` via the qexecute pgwire path. Each row is a
full snapshot — there are no partial UPDATEs.

Refs: NKD_PIVOT_AUDIT.md §5.3-5.6, PLAN.md §C7, DEC-3, DEC-4, DEC-8.
"""

import json
import logging
import math
import os
import random
import threading
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Optional

from shared.contract_resolver import resolve_contract_id, tick_snap_outward
from shared.nkd_jitter import sample_isaac_jitter
from shared.redis_client import CH_ALERTS, get_redis_client
from shared.constants import now_et

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants — locked spec values
# ---------------------------------------------------------------------------

_PHASE_A = "A"
_PHASE_B = "B"
_PHASE_C = "C"
_PHASE_TP = "TP_HIT"

_PHASE_B_START_BASE_DOLLARS = Decimal("2000")   # profit level where Phase B starts
_PHASE_C_START_BASE_DOLLARS = Decimal("3000")   # profit level where Phase C starts ($450 trail)
_TP_TARGET_DOLLARS          = Decimal("4450")
_PHASE_B_BUFFER_DOLLARS     = Decimal("1000")   # flat buffer during Phase B
_PHASE_C_BUFFER_DOLLARS     = Decimal("450")    # flat buffer during Phase C and TP zone
_PHASE_A_STEP_DOLLARS       = Decimal("500")    # Phase A modify gate
_EFFECTIVE_BUFFER_FLOOR     = Decimal("100")    # minimum broker SL buffer (floor for extreme J)

_STALE_QUOTE_THRESHOLD_SECONDS = 30.0
_REDIS_KEY_OPEN_POSITIONS = "captain:open_positions"

_NKD_POINT_VALUE = Decimal("5")  # fixed for NKD; we read D00 in the live path

_JITTER_X_MIN = 0.01
_JITTER_X_MAX = 1.00
_JITTER_SCALE = Decimal("20")  # |J| ∈ [0.2, 20.0] per spec


# ---------------------------------------------------------------------------
# Pure functions (no IO; safe to call from unit tests without mocks)
# ---------------------------------------------------------------------------

# sample_isaac_jitter is imported from shared.nkd_jitter (see import above).
# It is re-exported here so existing tests importing it from this module continue
# to work without modification.
# Signature: sample_isaac_jitter(parity_env) -> tuple[Decimal, int, Decimal]
# Returns (X, Y, J): Nomaan tower -> (0, 0, 0); Isaac tower -> J = 20*X*Y.


def compute_nkd_phase(
    pnl_dollars: Decimal,
    d_init: Decimal,
) -> tuple[str, Decimal]:
    """Stateless phase + buffer derivation — 3-step ladder.

    Phase A  pnl < 2000                -> buffer = d_init  (hold initial SL)
    Phase B  2000 <= pnl < 3000        -> buffer = 1000    (trail $1000 behind mark)
    Phase C  3000 <= pnl < 4450        -> buffer = 450     (tight trail)
    TP_HIT   pnl >= 4450               -> buffer = 450     (let LIMIT TP fill)

    Phase boundaries are CLEAN — J does not appear here. Jitter J applies in
    _scan_one_trail: effective_buffer = buffer + J (with floor at $100).

    Degenerate case: when d_init <= 450 the Phase B $1000 step may exceed
    d_init. We floor Phase B's buffer at d_init so the stop never retreats.
    """
    if pnl_dollars < _PHASE_B_START_BASE_DOLLARS:
        return (_PHASE_A, d_init)

    if pnl_dollars < _PHASE_C_START_BASE_DOLLARS:
        # Phase B: $1000 flat, but never wider than d_init
        buffer_b = min(_PHASE_B_BUFFER_DOLLARS, d_init)
        return (_PHASE_B, buffer_b)

    if pnl_dollars < _TP_TARGET_DOLLARS:
        return (_PHASE_C, _PHASE_C_BUFFER_DOLLARS)

    return (_PHASE_TP, _PHASE_C_BUFFER_DOLLARS)


def apply_ratchet(
    current_stop: Optional[Decimal],
    candidate_stop: Decimal,
    direction: int,
) -> Decimal:
    """Return the MORE conservative of the two stops (never retreat).

    Convention:
      * LONG  (direction =  1): stop moves UP   as the market rises -> max
      * SHORT (direction = -1): stop moves DOWN as the market falls -> min

    A ``current_stop`` of ``None`` (first poll after entry, no prior
    broker-side stop captured) is treated as "no floor" — the candidate
    is returned unchanged.
    """
    if current_stop is None:
        return candidate_stop
    if direction == 1:
        return current_stop if current_stop > candidate_stop else candidate_stop
    if direction == -1:
        return current_stop if current_stop < candidate_stop else candidate_stop
    raise ValueError(f"apply_ratchet: direction must be ±1, got {direction!r}")


def compute_stop_price(
    mark: Decimal,
    buffer_dollars: Decimal,
    direction: int,
    point_value: Decimal,
    size: int,
) -> Decimal:
    """Translate a dollar buffer into a raw price (un-snapped to tick grid).

    For LONG: stop = mark - buffer_per_contract_per_point
    For SHORT: stop = mark + buffer_per_contract_per_point

    where buffer_per_point = buffer_dollars / (point_value * max(1, size)).

    The caller is responsible for snapping the result OUTWARD to the
    contract's tick grid via ``tick_snap_outward`` so the stop lands on
    a valid broker price BEYOND the implied dollar threshold.
    """
    if direction not in (1, -1):
        raise ValueError(f"compute_stop_price: direction must be ±1, got {direction!r}")
    if point_value <= 0:
        raise ValueError(f"compute_stop_price: point_value must be positive, got {point_value!r}")
    n = max(1, int(size))
    buffer_points = buffer_dollars / (point_value * Decimal(n))
    if direction == 1:
        return mark - buffer_points
    return mark + buffer_points


def phase_a_should_modify(
    pnl_dollars: Decimal,
    prev_pnl_dollars: Optional[Decimal],
    step_dollars: Decimal = _PHASE_A_STEP_DOLLARS,
) -> bool:
    """Gate Phase A modifies to one per $500 PnL crossing.

    Prevents broker-side modify spam during the linear hold phase where
    the buffer never changes — we only need to re-pin the stop when the
    market has moved by another $500.

    Returns ``True`` when ``floor(pnl/500) != floor(prev_pnl/500)`` (or
    when ``prev_pnl`` is None, i.e. first poll). ``False`` otherwise.
    """
    if prev_pnl_dollars is None:
        return True
    a = (pnl_dollars / step_dollars).to_integral_value(rounding="ROUND_FLOOR")
    b = (prev_pnl_dollars / step_dollars).to_integral_value(rounding="ROUND_FLOOR")
    return a != b


# ---------------------------------------------------------------------------
# Compliance hook — C8 ships compliance_modify_check; C7 calls it defensively
# ---------------------------------------------------------------------------

def _import_compliance_modify_check() -> Callable[[Any, str, str], tuple[bool, Optional[str]]]:
    """Return the C8 wrapper, or a permissive shim if C8 hasn't shipped yet.

    The shim ALWAYS approves so the trail keeps working in a tower where
    C8 has been reverted. The dual-remote sync rule (workspace §1) means
    one tower can briefly be ahead of the other; the shim is the safe
    side of that race.
    """
    try:
        from captain_command.blocks.b12_compliance_gate import (  # type: ignore
            compliance_modify_check,
        )
        return compliance_modify_check
    except ImportError:
        def _allow_all(_account_id, _asset, _execution_mode):
            return (True, None)
        return _allow_all


# ---------------------------------------------------------------------------
# Quote lookup (default — reads from MarketStream's quote_cache)
# ---------------------------------------------------------------------------

def _default_quote_lookup(
    asset: str,
    contract_id: str,
) -> tuple[Optional[Decimal], Optional[float]]:
    """Return ``(last_price, age_seconds_or_None)`` for ``contract_id``.

    ``age_seconds`` is the wall-clock age of the broker-side timestamp.
    ``None`` means we couldn't parse a timestamp from the quote payload
    (treat as fresh — the worst case is one stale-but-recent modify that
    the ratchet still prevents from being harmful).
    """
    try:
        from shared.topstep_stream import quote_cache
    except Exception:  # pragma: no cover — defensive
        return (None, None)
    quote = quote_cache.get(contract_id)
    if not quote:
        return (None, None)
    last_price = quote.get("lastPrice")
    if last_price is None:
        return (None, None)
    try:
        price = Decimal(str(last_price))
    except (ValueError, TypeError):
        return (None, None)
    ts_str = quote.get("timestamp")
    age: Optional[float] = None
    if ts_str:
        try:
            ts = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - ts).total_seconds()
        except (ValueError, TypeError):
            age = None
    return (price, age)


# ---------------------------------------------------------------------------
# D34 persistence (default — writes via QuestDB pgwire / qexecute)
# ---------------------------------------------------------------------------

def _default_persist_d34(row: dict) -> None:
    """Append a full-row snapshot to ``p3_d34_nkd_trail_state``.

    Schema (per C1 M048): all DOUBLE numerics + STRING / SYMBOL / INT /
    LONG / TIMESTAMP. We coerce every numeric to ``float`` here so the
    pgwire adapter doesn't render Decimals as ``cast('<v>' as DECIMAL(p,s))``
    against the actual DOUBLE columns.
    """
    try:
        from shared.questdb_client import get_cursor, qexecute
    except Exception as exc:  # pragma: no cover — defensive
        logger.error("ON-B7B-NKD: questdb_client unavailable for D34 persist: %s", exc)
        return

    def _f(x):
        if x is None:
            return None
        if isinstance(x, Decimal):
            return float(x)
        try:
            return float(x)
        except (ValueError, TypeError):
            return None

    def _i(x):
        if x is None:
            return None
        try:
            return int(x)
        except (ValueError, TypeError):
            return None

    cols = [
        "signal_id", "account_id", "asset", "contract_id",
        "entry_order_id", "sl_order_id", "tp_order_id",
        "direction", "contracts",
        "entry_price", "snapped_d_init", "tp_dollars",
        "jitter_x", "jitter_y", "jitter_j",
        "phase", "current_buffer", "current_stop_price", "current_pnl",
        "modify_seq", "last_modify_status", "last_modify_error",
    ]
    sl_oid_int = _i(row.get("sl_order_id"))
    tp_oid_int = _i(row.get("tp_order_id"))
    params = (
        row.get("signal_id"),
        str(row.get("account_id")) if row.get("account_id") is not None else None,
        row.get("asset"),
        row.get("contract_id"),
        row.get("entry_order_id"),
        sl_oid_int,
        tp_oid_int,
        _i(row.get("direction")),
        _i(row.get("contracts")),
        _f(row.get("entry_price")),
        _f(row.get("snapped_d_init")),
        _f(row.get("tp_dollars")),
        _f(row.get("jitter_x")),
        _i(row.get("jitter_y")),
        _f(row.get("jitter_j")),
        row.get("phase"),
        _f(row.get("current_buffer")),
        _f(row.get("current_stop_price")),
        _f(row.get("current_pnl")),
        _i(row.get("modify_seq")),
        row.get("last_modify_status"),
        row.get("last_modify_error"),
    )
    sql = (
        "INSERT INTO p3_d34_nkd_trail_state "
        "(" + ", ".join(cols) + ", last_updated) "
        "VALUES (" + ", ".join(["%s"] * len(cols)) + ", now())"
    )
    try:
        with get_cursor() as cur:
            qexecute(cur, sql, params, table="p3_d34_nkd_trail_state", columns=cols)
    except Exception as exc:
        logger.error("ON-B7B-NKD: D34 persist failed for signal=%s: %s",
                     row.get("signal_id"), exc)


# ---------------------------------------------------------------------------
# Alerts (CRITICAL — stale quote, modify failure, etc.)
# ---------------------------------------------------------------------------

def _emit_alert(
    redis_client,
    user_id: str,
    priority: str,
    event_type: str,
    message: str,
    extra: Optional[dict] = None,
) -> None:
    """Publish a CRITICAL / HIGH / MEDIUM alert to ``captain:alerts``."""
    if redis_client is None:
        return
    payload = {
        "user_id": user_id or "SYSTEM",
        "priority": priority,
        "event_type": event_type,
        "message": message,
        "source": "ON-B7B-NKD",
        "timestamp": now_et().isoformat(),
    }
    if extra:
        payload.update(extra)
    try:
        redis_client.publish(CH_ALERTS, json.dumps(payload, default=str))
    except Exception as exc:  # pragma: no cover — never block trail on alert IO
        logger.error("ON-B7B-NKD: alert publish failed (%s): %s", event_type, exc)


# ---------------------------------------------------------------------------
# Live PnL helper (mirrors b7_position_monitor's formula byte-for-byte)
# ---------------------------------------------------------------------------

def _compute_live_pnl(
    mark: Decimal,
    entry_price: Decimal,
    direction: int,
    contracts: int,
    point_value: Decimal,
) -> Decimal:
    """``(mark - entry) * direction * contracts * point_value``.

    Matches b7_position_monitor._compute_live_pnl semantics exactly so the
    trail block's phase decision can never disagree with B7's resolution
    decision (same numbers, same arithmetic, same boundary discipline).
    """
    return (mark - entry_price) * Decimal(direction) * Decimal(contracts) * point_value


# ---------------------------------------------------------------------------
# Module-level state (per-process, intentional)
# ---------------------------------------------------------------------------

# Per-position prev_pnl for the Phase A step gate. Keyed by signal_id so we
# don't grow with arbitrary integer order IDs. Position dict is the
# canonical store; this exists for tests that don't bother round-tripping
# through Redis. Trimmed by scan when positions resolve.
_PREV_PNL_BY_SIGNAL: dict[str, Decimal] = {}
_PREV_PNL_LOCK = threading.Lock()


def _get_prev_pnl(pos: dict) -> Optional[Decimal]:
    sig_id = pos.get("signal_id")
    # Position-dict wins over module dict — the dict survives Redis
    # round-trips on container restart.
    stored = pos.get("prev_pnl")
    if stored is not None:
        try:
            return stored if isinstance(stored, Decimal) else Decimal(str(stored))
        except (ValueError, TypeError):
            pass
    if sig_id is None:
        return None
    with _PREV_PNL_LOCK:
        return _PREV_PNL_BY_SIGNAL.get(sig_id)


def _set_prev_pnl(pos: dict, pnl: Decimal) -> None:
    sig_id = pos.get("signal_id")
    pos["prev_pnl"] = pnl
    if sig_id is not None:
        with _PREV_PNL_LOCK:
            _PREV_PNL_BY_SIGNAL[sig_id] = pnl


def _purge_prev_pnl(signal_ids: set[str]) -> None:
    """Drop tracked prev_pnl for signals no longer in the open set."""
    with _PREV_PNL_LOCK:
        for sid in list(_PREV_PNL_BY_SIGNAL.keys()):
            if sid not in signal_ids:
                _PREV_PNL_BY_SIGNAL.pop(sid, None)


def _reset_state_for_tests() -> None:
    """Test-only — clear module-level state between cases."""
    with _PREV_PNL_LOCK:
        _PREV_PNL_BY_SIGNAL.clear()


# ---------------------------------------------------------------------------
# Main scan entry point — called from orchestrator._run_position_monitor
# ---------------------------------------------------------------------------

def scan_nkd_trails(
    open_positions: list[dict],
    client: Any,
    redis_client: Any = None,
    *,
    quote_lookup: Optional[Callable[[str, str], tuple[Optional[Decimal], Optional[float]]]] = None,
    persist_d34: Optional[Callable[[dict], None]] = None,
    compliance_modify_check: Optional[Callable[[Any, str, str], tuple[bool, Optional[str]]]] = None,
    parity_env: Optional[str] = None,
    execution_mode: str = "AUTO",
    open_positions_key: str = _REDIS_KEY_OPEN_POSITIONS,
) -> list[dict]:
    """One scan pass over the trail-flagged subset of ``open_positions``.

    Mutates ``open_positions`` entries in-place (jitter_x/y/j on first poll,
    current_phase / current_buffer / current_stop_price / modify_seq on
    every successful modify) and mirrors the new state to the Redis
    ``captain:open_positions`` hash so the GUI / Command process see fresh
    values within one poll.

    Parameters
    ----------
    open_positions
        The orchestrator's authoritative list of open position dicts. Only
        entries with ``is_nkd_trail == True`` are processed — non-NKD
        positions are skipped silently.
    client
        TopstepX REST client (``shared.topstep_client``). Must expose a
        ``modify_order(account_id, order_id, stop_price=...) -> dict``
        method. Tests pass a MagicMock.
    redis_client
        Redis client for the open-positions hash mirror + alert publish.
        ``None`` is tolerated (purely diagnostic; no state writes).
    quote_lookup
        Optional injectable replacement for ``_default_quote_lookup``. Used
        by tests to feed deterministic marks + ages.
    persist_d34
        Optional injectable replacement for ``_default_persist_d34``.
    compliance_modify_check
        Optional injectable replacement for the C8 wrapper. Defaults to
        ``_import_compliance_modify_check()``.
    parity_env
        ``"0"`` / ``"1"`` / ``""`` — defaults to ``$INSTANCE_PARITY``. Used
        ONLY for jitter sampling.
    execution_mode
        ``"AUTO"`` / ``"MANUAL"`` — forwarded to ``compliance_modify_check``.
        When MANUAL the trail logs + halts modifies (does not flatten).

    Returns
    -------
    list[dict]
        Diagnostic rows ``{signal_id, phase, buffer, stop_price, modify_status,
        skip_reason}`` — one per processed NKD position. Used by callers /
        tests to assert outcomes without re-querying state.
    """
    diagnostics: list[dict] = []
    qlookup = quote_lookup or _default_quote_lookup
    persist = persist_d34 or _default_persist_d34
    compliance = compliance_modify_check or _import_compliance_modify_check()
    if parity_env is None:
        parity_env = os.environ.get("INSTANCE_PARITY", "")

    # Track which signal_ids we touched so we can purge stale prev_pnl
    # entries when a position is no longer in the open set. We need this
    # to run BEFORE the empty-list early-exit so a position that
    # C10: NKD subscription guard — retain MarketStream quote feed during 22h hold.
    # Fast path (no NKD positions) is a single any() call and a None check.
    try:
        from captain_online.main import ensure_nkd_subscribed
        ensure_nkd_subscribed(open_positions or [])
    except Exception:
        pass  # non-fatal — trail logic continues even if guard fails

    # externally closes (UserStream size=0 → orchestrator drops from
    # open_positions) doesn't leak prev_pnl into the module cache forever.
    seen_signal_ids: set[str] = set()

    for pos in (open_positions or []):
        if not pos.get("is_nkd_trail"):
            continue
        sig_id = pos.get("signal_id")
        if sig_id is None:
            logger.warning("ON-B7B-NKD: skipping trail position with no signal_id")
            continue
        seen_signal_ids.add(sig_id)

        diag = _scan_one_trail(
            pos,
            client=client,
            redis_client=redis_client,
            quote_lookup=qlookup,
            persist=persist,
            compliance=compliance,
            parity_env=parity_env,
            execution_mode=execution_mode,
            open_positions_key=open_positions_key,
        )
        if diag is not None:
            diagnostics.append(diag)

    _purge_prev_pnl(seen_signal_ids)
    return diagnostics


def _scan_one_trail(
    pos: dict,
    *,
    client: Any,
    redis_client: Any,
    quote_lookup: Callable[[str, str], tuple[Optional[Decimal], Optional[float]]],
    persist: Callable[[dict], None],
    compliance: Callable[[Any, str, str], tuple[bool, Optional[str]]],
    parity_env: str,
    execution_mode: str,
    open_positions_key: str,
) -> Optional[dict]:
    """Process a single NKD trail position.

    Returns the diagnostic row (``None`` if we early-skipped without
    enough info to even build one).
    """
    sig_id = pos.get("signal_id")
    asset = pos.get("asset") or "NKD"
    user_id = pos.get("user_id", "primary_user")
    account_id_raw = pos.get("account")

    # Order-ID guard: C5 UserStream capture replaces the "BRACKET" sentinel
    # with the real LONG once the broker confirms the SL child order. Until
    # then we cannot issue a /Order/modify call.
    sl_order_id = pos.get("sl_order_id")
    if sl_order_id in (None, "BRACKET", "", "None"):
        return {
            "signal_id": sig_id,
            "phase": None,
            "buffer": None,
            "stop_price": None,
            "modify_status": None,
            "skip_reason": "sl_order_id_unresolved",
        }

    # Quote lookup + stale-quote guard (CRITICAL — > 30 s stale skips this
    # poll and alerts so a quote-feed outage doesn't pin the stop at the
    # last-known mark while the market moves underneath us).
    contract_id = resolve_contract_id(asset) or ""
    mark, age = quote_lookup(asset, contract_id)
    if mark is None:
        _emit_alert(
            redis_client, user_id, "CRITICAL", "NKD_TRAIL_NO_QUOTE",
            f"NKD trail skip: no live quote available for {asset} "
            f"(contract={contract_id}) — modify halted",
            {"signal_id": sig_id, "asset": asset, "contract_id": contract_id},
        )
        return {
            "signal_id": sig_id, "phase": None, "buffer": None,
            "stop_price": None, "modify_status": None,
            "skip_reason": "no_quote",
        }
    if age is not None and age > _STALE_QUOTE_THRESHOLD_SECONDS:
        _emit_alert(
            redis_client, user_id, "CRITICAL", "NKD_TRAIL_STALE_QUOTE",
            f"NKD trail skip: quote age {age:.1f}s > "
            f"{_STALE_QUOTE_THRESHOLD_SECONDS:.0f}s threshold — modify halted "
            f"to avoid stop pinned at stale mark",
            {"signal_id": sig_id, "asset": asset, "age_seconds": age},
        )
        return {
            "signal_id": sig_id, "phase": None, "buffer": None,
            "stop_price": None, "modify_status": None,
            "skip_reason": "stale_quote",
        }

    # Direction / contracts / entry_price / snapped_d_init — all required.
    try:
        direction = int(pos.get("direction", 1) or 1)
        if direction not in (1, -1):
            raise ValueError(f"unexpected direction {direction}")
        contracts = int(pos.get("contracts", 0) or 0)
        if contracts <= 0:
            raise ValueError(f"contracts must be > 0, got {contracts}")
        entry_price_raw = pos.get("entry_price")
        if entry_price_raw is None:
            raise ValueError("entry_price is None")
        entry_price = entry_price_raw if isinstance(entry_price_raw, Decimal) \
            else Decimal(str(entry_price_raw))
        snapped_d_init_raw = pos.get("snapped_d_init")
        if snapped_d_init_raw is None:
            raise ValueError("snapped_d_init is None")
        snapped_d_init = snapped_d_init_raw if isinstance(snapped_d_init_raw, Decimal) \
            else Decimal(str(snapped_d_init_raw))
    except (ValueError, TypeError) as exc:
        logger.error("ON-B7B-NKD: position state invalid for %s: %s", sig_id, exc)
        return {
            "signal_id": sig_id, "phase": None, "buffer": None,
            "stop_price": None, "modify_status": None,
            "skip_reason": f"invalid_state:{exc}",
        }

    point_value = _NKD_POINT_VALUE  # NKD is the only trail-enabled asset

    # First-poll jitter sampling. Once sampled, persists for the lifetime
    # of the trade — we re-load from the position dict on every subsequent
    # poll so jitter is deterministic per trade even if the orchestrator
    # rebuilds the dict from Redis.
    jitter_j_raw = pos.get("jitter_j")
    first_poll = jitter_j_raw is None
    if first_poll:
        x, y, j = sample_isaac_jitter(parity_env)
        pos["jitter_x"] = x
        pos["jitter_y"] = y
        pos["jitter_j"] = j
        jitter_j = j
        logger.info(
            "ON-B7B-NKD: jitter sampled signal=%s parity=%s X=%s Y=%d J=%s",
            sig_id, parity_env or "0", x, y, j,
        )
    else:
        try:
            jitter_j = jitter_j_raw if isinstance(jitter_j_raw, Decimal) \
                else Decimal(str(jitter_j_raw))
        except (ValueError, TypeError):
            jitter_j = Decimal("0")

    # Live PnL — same byte-for-byte formula as b7_position_monitor.
    pnl = _compute_live_pnl(mark, entry_price, direction, contracts, point_value)

    phase, buffer = compute_nkd_phase(pnl, snapped_d_init)

    # Apply Isaac-tower jitter to broker SL dollar buffer.
    # J is a signed dollar offset; floor at _EFFECTIVE_BUFFER_FLOOR so an
    # extreme negative J cannot produce an absurdly tight stop.
    effective_buffer = max(buffer + jitter_j, _EFFECTIVE_BUFFER_FLOOR)

    # TP_HIT: no further modify. Broker LIMIT @ 4450 owns the exit.
    if phase == _PHASE_TP:
        # Persist a snapshot row so D34 captures the TP_HIT phase, but
        # never call broker.
        _persist_state_row(
            pos, persist, sig_id=sig_id, asset=asset, contract_id=contract_id,
            account_id=account_id_raw, direction=direction, contracts=contracts,
            entry_price=entry_price, snapped_d_init=snapped_d_init,
            phase=phase, buffer=buffer, stop_price=pos.get("current_stop_price"),
            pnl=pnl, modify_seq=int(pos.get("modify_seq") or 0),
            modify_status="TP_HIT_NO_MODIFY", modify_error=None,
        )
        # Don't refresh prev_pnl on TP_HIT — keeps Phase A gate logic clean
        # if we ever oscillate back to phase B (shouldn't happen, but safe).
        return {
            "signal_id": sig_id, "phase": phase, "buffer": float(buffer),
            "stop_price": pos.get("current_stop_price"),
            "modify_status": "TP_HIT_NO_MODIFY", "skip_reason": None,
        }

    # Compute candidate stop price using the broker-effective buffer (buffer + J).
    stop_raw = compute_stop_price(mark, effective_buffer, direction, point_value, contracts)
    stop_snapped = Decimal(str(tick_snap_outward(float(stop_raw), asset, direction)))

    # Ratchet — refuse to weaken the broker-side stop.
    current_stop_raw = pos.get("current_stop_price")
    current_stop: Optional[Decimal] = None
    if current_stop_raw is not None:
        try:
            current_stop = current_stop_raw if isinstance(current_stop_raw, Decimal) \
                else Decimal(str(current_stop_raw))
        except (ValueError, TypeError):
            current_stop = None
    stop_new = apply_ratchet(current_stop, stop_snapped, direction)

    # Phase A step gate: only modify when we've crossed a new $500 boundary.
    prev_pnl = _get_prev_pnl(pos)
    if phase == _PHASE_A and current_stop is not None and stop_new == current_stop:
        # Stop didn't move; nothing to do. Refresh prev_pnl so we don't
        # ratchet on the next poll either if we haven't moved.
        _set_prev_pnl(pos, pnl)
        return {
            "signal_id": sig_id, "phase": phase, "buffer": float(buffer),
            "stop_price": float(current_stop), "modify_status": "UNCHANGED",
            "skip_reason": "stop_unchanged",
        }
    if phase == _PHASE_A and current_stop is not None:
        # Phase A specifically: even if the ratchet WOULD allow a tighter
        # stop (mark crept up by a few ticks), only execute on $500 PnL
        # boundary crossings to avoid modify spam during the linear hold.
        if not phase_a_should_modify(pnl, prev_pnl):
            return {
                "signal_id": sig_id, "phase": phase, "buffer": float(buffer),
                "stop_price": float(current_stop), "modify_status": "GATED",
                "skip_reason": "phase_a_step_gate",
            }

    # No change at all (Phase B/C with current == new) — skip modify but
    # still refresh prev_pnl.
    if current_stop is not None and stop_new == current_stop:
        _set_prev_pnl(pos, pnl)
        return {
            "signal_id": sig_id, "phase": phase, "buffer": float(buffer),
            "stop_price": float(current_stop), "modify_status": "UNCHANGED",
            "skip_reason": "stop_unchanged",
        }

    # Compliance check — MANUAL mode halts the trail (does NOT flatten).
    approved, comp_reason = compliance(account_id_raw, asset, execution_mode)
    if not approved:
        logger.warning(
            "ON-B7B-NKD: compliance halted trail modify for signal=%s asset=%s: %s",
            sig_id, asset, comp_reason,
        )
        # Persist the halted-state row so D34 captures the event.
        _persist_state_row(
            pos, persist, sig_id=sig_id, asset=asset, contract_id=contract_id,
            account_id=account_id_raw, direction=direction, contracts=contracts,
            entry_price=entry_price, snapped_d_init=snapped_d_init,
            phase=phase, buffer=effective_buffer, stop_price=current_stop, pnl=pnl,
            modify_seq=int(pos.get("modify_seq") or 0),
            modify_status="COMPLIANCE_HALT",
            modify_error=comp_reason or "compliance_modify_check returned False",
        )
        return {
            "signal_id": sig_id, "phase": phase, "buffer": float(effective_buffer),
            "stop_price": float(current_stop) if current_stop is not None else None,
            "modify_status": "COMPLIANCE_HALT", "skip_reason": comp_reason,
        }

    # Issue the /Order/modify — float arg matches the broker API.
    try:
        sl_oid_int = int(sl_order_id)
    except (ValueError, TypeError) as exc:
        logger.error(
            "ON-B7B-NKD: sl_order_id not coercible to int for signal=%s "
            "(value=%r): %s", sig_id, sl_order_id, exc,
        )
        return {
            "signal_id": sig_id, "phase": phase, "buffer": float(buffer),
            "stop_price": float(stop_new), "modify_status": "MODIFY_ERROR",
            "skip_reason": f"bad_sl_order_id:{sl_order_id!r}",
        }

    try:
        acct_arg = int(account_id_raw) if account_id_raw is not None else None
    except (ValueError, TypeError):
        acct_arg = account_id_raw  # let broker reject if not an int

    modify_status = "OK"
    modify_error: Optional[str] = None
    try:
        result = client.modify_order(
            account_id=acct_arg,
            order_id=sl_oid_int,
            stop_price=float(stop_new),
        )
        success = bool(result and result.get("success"))
        if not success:
            modify_status = "REJECTED"
            modify_error = (result or {}).get("errorMessage") or "modify rejected by broker"
            _emit_alert(
                redis_client, user_id, "CRITICAL",
                "NKD_TRAIL_MODIFY_REJECTED",
                f"NKD trail /Order/modify REJECTED for {asset} "
                f"order={sl_oid_int}: {modify_error}. Stop unchanged; "
                f"next poll will re-attempt with refreshed mark.",
                {"signal_id": sig_id, "order_id": sl_oid_int,
                 "phase": phase, "stop_price": float(stop_new)},
            )
    except Exception as exc:
        modify_status = "MODIFY_EXCEPTION"
        modify_error = str(exc)
        _emit_alert(
            redis_client, user_id, "CRITICAL",
            "NKD_TRAIL_MODIFY_EXCEPTION",
            f"NKD trail /Order/modify raised for {asset} order={sl_oid_int}: "
            f"{exc}. Stop unchanged; next poll will re-attempt.",
            {"signal_id": sig_id, "order_id": sl_oid_int,
             "phase": phase, "stop_price": float(stop_new)},
        )
        logger.error(
            "ON-B7B-NKD: modify_order exception signal=%s order=%s: %s",
            sig_id, sl_oid_int, exc,
        )

    new_modify_seq = int(pos.get("modify_seq") or 0)
    if modify_status == "OK":
        new_modify_seq += 1
        # Only commit ratchet + stop_price on a successful modify so a
        # broker reject doesn't lock us out of retrying with a fresh mark.
        pos["current_stop_price"] = stop_new
        pos["current_phase"] = phase
        pos["current_buffer"] = effective_buffer  # broker-applied buffer (buffer + J)
        pos["modify_seq"] = new_modify_seq
        logger.info(
            "ON-B7B-NKD: modify OK signal=%s phase=%s effective_buffer=$%.2f "
            "stop=%.2f pnl=$%.2f seq=%d",
            sig_id, phase, float(effective_buffer), float(stop_new),
            float(pnl), new_modify_seq,
        )

    # Persist row regardless of outcome (full snapshot, includes status).
    # buffer= receives the broker-applied effective_buffer so D34 reflects
    # what was actually sent (effective_buffer = phase_buffer + J).
    _persist_state_row(
        pos, persist, sig_id=sig_id, asset=asset, contract_id=contract_id,
        account_id=account_id_raw, direction=direction, contracts=contracts,
        entry_price=entry_price, snapped_d_init=snapped_d_init,
        phase=phase, buffer=effective_buffer,
        stop_price=stop_new if modify_status == "OK" else current_stop,
        pnl=pnl, modify_seq=new_modify_seq,
        modify_status=modify_status, modify_error=modify_error,
    )

    # Mirror updated position dict to Redis (open positions hash).
    if modify_status == "OK":
        _mirror_position_to_redis(pos, redis_client, open_positions_key)

    # Always refresh prev_pnl AFTER processing — even on REJECT, the
    # broker has seen the attempt and the next poll should re-attempt
    # from the current mark, not the pre-attempt mark.
    _set_prev_pnl(pos, pnl)

    return {
        "signal_id": sig_id, "phase": phase, "buffer": float(effective_buffer),
        "stop_price": float(stop_new),
        "modify_status": modify_status, "skip_reason": modify_error,
    }


def _persist_state_row(
    pos: dict,
    persist: Callable[[dict], None],
    *,
    sig_id: str, asset: str, contract_id: str, account_id: Any,
    direction: int, contracts: int,
    entry_price: Decimal, snapped_d_init: Decimal,
    phase: str, buffer: Decimal, stop_price: Optional[Decimal],
    pnl: Decimal, modify_seq: int,
    modify_status: str, modify_error: Optional[str],
) -> None:
    """Build the full-row snapshot dict and delegate to ``persist``."""
    row = {
        "signal_id": sig_id,
        "account_id": account_id,
        "asset": asset,
        "contract_id": contract_id,
        "entry_order_id": pos.get("entry_order_id"),
        "sl_order_id": pos.get("sl_order_id"),
        "tp_order_id": pos.get("tp_order_id"),
        "direction": direction,
        "contracts": contracts,
        "entry_price": entry_price,
        "snapped_d_init": snapped_d_init,
        "tp_dollars": pos.get("tp_dollars"),
        "jitter_x": pos.get("jitter_x"),
        "jitter_y": pos.get("jitter_y"),
        "jitter_j": pos.get("jitter_j"),
        "phase": phase,
        "current_buffer": buffer,
        "current_stop_price": stop_price,
        "current_pnl": pnl,
        "modify_seq": modify_seq,
        "last_modify_status": modify_status,
        "last_modify_error": modify_error,
    }
    try:
        persist(row)
    except Exception as exc:
        logger.error("ON-B7B-NKD: persist callback raised: %s", exc)


def _mirror_position_to_redis(
    pos: dict,
    redis_client: Any,
    open_positions_key: str,
) -> None:
    """Write updated trail-state fields back to ``captain:open_positions``."""
    if redis_client is None:
        return
    sig_id = pos.get("signal_id")
    if not sig_id:
        return
    try:
        from shared.decimal_json import dumps_decimal
    except ImportError:
        # Fallback — best-effort default=str shouldn't lose accuracy for
        # our Decimal fields in practice.
        def dumps_decimal(d):  # type: ignore
            return json.dumps(d, default=str)
    try:
        existing_raw = redis_client.hget(open_positions_key, sig_id)
    except Exception as exc:
        logger.warning("ON-B7B-NKD: Redis hget failed for %s: %s", sig_id, exc)
        return
    if existing_raw is None:
        # Position was removed (race with resolution); skip mirror.
        return
    try:
        existing = json.loads(existing_raw if isinstance(existing_raw, str)
                              else existing_raw.decode())
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("ON-B7B-NKD: Redis open_positions for %s corrupt: %s",
                       sig_id, exc)
        return
    # Only touch the trail-state fields — leave entry_price, contracts,
    # etc. as the orchestrator wrote them.
    existing["current_phase"] = pos.get("current_phase")
    existing["current_buffer"] = pos.get("current_buffer")
    existing["current_stop_price"] = pos.get("current_stop_price")
    existing["modify_seq"] = pos.get("modify_seq")
    existing["jitter_x"] = pos.get("jitter_x")
    existing["jitter_y"] = pos.get("jitter_y")
    existing["jitter_j"] = pos.get("jitter_j")
    existing["sl_order_id"] = pos.get("sl_order_id")
    try:
        redis_client.hset(open_positions_key, sig_id, dumps_decimal(existing))
    except Exception as exc:
        logger.warning("ON-B7B-NKD: Redis hset failed for %s: %s", sig_id, exc)
