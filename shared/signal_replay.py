# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass  # Running outside QuantConnect environment
# endregion
"""Signal Replay Engine — captain_online_replay() implementation.

Replays the Captain Online signal pipeline (B2->B5) with configurable
parameters against historical data. Used by:
  - B3 Pseudotrader: CURRENT vs PROPOSED parameter comparison (P3-PG-09)
  - B5 Sensitivity: strategy parameter perturbation (P3-PG-12)
  - B6 Auto-Expansion: GA candidate evaluation (P3-PG-13)

Two replay levels:
  sizing_replay:   Same trades, different AIM/Kelly -> different contract sizes
  strategy_replay: Different SL/TP/threshold -> different trade outcomes + sizing

Architecture constraints:
  - Does NOT import or call B1 data ingestion (requires live market data)
  - Does NOT write to Redis or QuestDB during replay
  - Accepts pre-loaded historical data as parameters
  - Returns trade lists in canonical format: {day, pnl, contracts, direction, regime}
"""

import json
import logging
import math
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Asset constants
# ---------------------------------------------------------------------------

# Average opening range in points (r_mi is in OR-range multiples)
DEFAULT_OR_RANGES = {
    "ES": 4.0, "MES": 4.0,
    "NQ": 15.0, "MNQ": 15.0,
    "M2K": 8.0, "MYM": 100.0,
    "NKD": 100.0, "MGC": 5.0,
    "ZB": 0.25, "ZN": 0.125, "ZT": 0.0625,
}

# Dollars per point for each contract
POINT_VALUES = {
    "ES": 50.0, "MES": 5.0,
    "NQ": 20.0, "MNQ": 2.0,
    "M2K": 5.0, "MYM": 0.5,
    "NKD": 5.0, "MGC": 10.0,
    "ZB": 1000.0, "ZN": 1000.0, "ZT": 2000.0,
}

# P2 d02 regime label -> canonical regime name.
# P2 outputs "LOW" and "HIGH"; Captain uses "LOW_VOL" and "HIGH_VOL".
_REGIME_MAP = {
    "LOW": "LOW_VOL",
    "MEDIUM": "LOW_VOL",   # treat MEDIUM as LOW_VOL (conservative)
    "HIGH": "HIGH_VOL",
}

# Default data directory (relative to captain-system root)
_DATA_DIR = Path(__file__).parent.parent / "data"


class SignalReplayEngine:
    """Replays the Captain Online signal pipeline with configurable parameters.

    Pure computation -- no side effects on Redis, QuestDB, or any external
    state. All inputs are passed explicitly; all outputs are returned.
    """

    def __init__(self, asset: str = "ES"):
        self.asset = asset.upper()
        self.or_range = DEFAULT_OR_RANGES.get(self.asset, 4.0)
        self.point_value = POINT_VALUES.get(self.asset, 50.0)

    # ------------------------------------------------------------------
    # Level 1: sizing_replay — same trades, different AIM/Kelly sizing
    # ------------------------------------------------------------------

    def sizing_replay(
        self,
        trades: list[dict] | None = None,
        regime_labels: dict[str, str] | None = None,
        aim_weights: dict[str, float] | None = None,
        kelly_params: dict[str, dict] | None = None,
        account_capital: float = 150_000.0,
        risk_per_contract: float | None = None,
        tsm_max_contracts: int = 15,
        shrinkage_factor: float = 0.5,
        # Alternate calling convention (used by B3 pseudotrader et al.)
        asset_id: str | None = None,
        ewma_states: dict | None = None,
        account_config: dict | None = None,
    ) -> list[dict]:
        """Level 1 replay: re-size historical trades under proposed parameters.

        The actual per-contract return is preserved from the historical trade.
        Only the number of contracts changes based on the new AIM/Kelly state.

        Supports two calling conventions:
          1. Direct: sizing_replay(trades=..., regime_labels=..., ...)
          2. Config-dict: sizing_replay(trades=..., account_config={...}, ...)
             where account_config has "starting_balance" and "max_contracts".

        Args:
            trades: Historical trades from trade_source.load_trades().
                Each must have: day, pnl, contracts, direction, raw_r_mi.
            regime_labels: {date_str: "LOW"|"HIGH"} from P2 d02.
            aim_weights: {aim_name: weight} for DMA-weighted AIM average.
                Example: {"dma_slow": 0.6, "dma_fast": 0.4}
                Values are the per-AIM modifiers (0.0-2.0 range), NOT raw
                weights. The combined modifier is their weighted average.
            kelly_params: {asset: {regime: {"kelly_full": float, "prob": float}}}.
                Example: {"ES": {"LOW_VOL": {"kelly_full": 0.12, "prob": 0.68},
                                  "HIGH_VOL": {"kelly_full": 0.05, "prob": 0.32}}}
            account_capital: Current account balance in dollars.
            risk_per_contract: Dollar risk per contract. If None, computed as
                sl_distance * point_value (defaults to or_range * point_value).
            tsm_max_contracts: TSM position-size cap.
            shrinkage_factor: Kelly shrinkage (half-Kelly = 0.5).
            asset_id: Optional asset override (ignored; uses self.asset).
            ewma_states: Optional EWMA state dict (reserved for future use).
            account_config: Optional dict with "starting_balance" and
                "max_contracts" keys (overrides account_capital and
                tsm_max_contracts when provided).

        Returns:
            List of canonical trade dicts:
                {day, pnl, contracts, direction, regime}
        """
        # Normalise alternate calling convention
        if trades is None:
            trades = []
        if regime_labels is None:
            regime_labels = {}
        if aim_weights is None:
            aim_weights = {}
        if kelly_params is None:
            kelly_params = {}
        if account_config is not None:
            account_capital = account_config.get("starting_balance", account_capital)
            tsm_max_contracts = account_config.get("max_contracts", tsm_max_contracts)

        if risk_per_contract is None:
            risk_per_contract = self.or_range * self.point_value

        asset_kelly = kelly_params.get(self.asset, kelly_params)

        results = []
        for trade in trades:
            day = trade["day"]
            direction = trade.get("direction", 1)
            raw_r_mi = trade.get("raw_r_mi")
            original_contracts = trade.get("contracts", 1)
            original_pnl = trade.get("pnl", 0.0)

            # 1. Look up regime
            raw_regime = regime_labels.get(day, "LOW")
            regime = _REGIME_MAP.get(raw_regime, "LOW_VOL")

            # 2. Compute AIM combined modifier (DMA-weighted average, clamped)
            combined_modifier = self._compute_aim_modifier(aim_weights)

            # 3. Compute blended Kelly across regimes
            blended_kelly = self._compute_blended_kelly(asset_kelly)

            # 4. Apply shrinkage
            adjusted_kelly = blended_kelly * shrinkage_factor

            # 5. Apply AIM modifier
            kelly_with_aim = adjusted_kelly * combined_modifier

            # 6. Compute contracts
            if risk_per_contract > 0:
                raw_contracts = kelly_with_aim * account_capital / risk_per_contract
            else:
                raw_contracts = 1.0
            contracts = max(1, math.floor(raw_contracts))

            # 7. Apply TSM cap
            contracts = min(contracts, tsm_max_contracts)

            # 8. Compute P&L using actual per-contract return
            if raw_r_mi is not None and original_contracts > 0:
                # Per-contract P&L from the original trade
                pnl_per_contract = raw_r_mi * self.or_range * self.point_value
                pnl = round(pnl_per_contract * contracts, 2)
            elif original_contracts > 0:
                # Fallback: scale from original P&L
                pnl_per_contract = original_pnl / original_contracts
                pnl = round(pnl_per_contract * contracts, 2)
            else:
                pnl = 0.0

            results.append({
                "day": day,
                "pnl": pnl,
                "contracts": contracts,
                "direction": direction,
                "regime": regime,
            })

        return results

    # ------------------------------------------------------------------
    # Level 2: strategy_replay — different SL/TP/threshold + sizing
    # ------------------------------------------------------------------

    def strategy_replay(
        self,
        trades: list[dict] | None = None,
        regime_labels: dict[str, str] | None = None,
        aim_weights: dict[str, float] | None = None,
        kelly_params: dict[str, dict] | None = None,
        sl_mult: float = 1.0,
        tp_mult: float = 2.0,
        threshold: float | None = None,
        account_capital: float = 150_000.0,
        risk_per_contract: float | None = None,
        tsm_max_contracts: int = 15,
        shrinkage_factor: float = 0.5,
        or_range_override: float | None = None,
        # Alternate calling convention (used by B3 pseudotrader et al.)
        asset_id: str | None = None,
        raw_trades: list[dict] | None = None,
        strategy_params: dict | None = None,
        ewma_states: dict | None = None,
        account_config: dict | None = None,
    ) -> list[dict]:
        """Level 2 replay: re-simulate trade outcomes under perturbed SL/TP.

        For each historical trade with raw_r_mi (return in OR-range multiples):
        1. Simulate exit under new SL/TP multiples
        2. Apply sizing_replay logic for contract count
        3. Final P&L = per_contract_pnl * contracts

        Supports two calling conventions:
          1. Direct: strategy_replay(trades=..., sl_mult=0.35, tp_mult=1.0, ...)
          2. Config-dict: strategy_replay(raw_trades=...,
                 strategy_params={"sl_multiplier": 0.35, "tp_multiplier": 1.0},
                 account_config={"starting_balance": 150000, "max_contracts": 15})

        Args:
            trades: Historical trades. Each must have: day, direction, raw_r_mi.
                Alias: raw_trades.
            regime_labels: {date_str: "LOW"|"HIGH"} from P2 d02.
            aim_weights: AIM modifier weights (same as sizing_replay).
            kelly_params: Kelly parameters (same as sizing_replay).
            sl_mult: Stop-loss in OR-range multiples (e.g. 1.0 = 1x OR range).
            tp_mult: Take-profit in OR-range multiples (e.g. 2.0 = 2x OR range).
            threshold: Signal threshold for trade entry. If provided, trades
                whose abs(raw_r_mi) < abs(threshold) equivalent are skipped.
                This is the x_mik threshold from the locked strategy.
            account_capital: Current account balance in dollars.
            risk_per_contract: Dollar risk per contract. Defaults to
                sl_mult * or_range * point_value under the new SL.
            tsm_max_contracts: TSM position-size cap.
            shrinkage_factor: Kelly shrinkage (half-Kelly = 0.5).
            or_range_override: Override the default OR range for the asset.
            asset_id: Optional asset override (ignored; uses self.asset).
            raw_trades: Alias for trades (alternate calling convention).
            strategy_params: Optional dict with "sl_multiplier" and
                "tp_multiplier" keys (overrides sl_mult/tp_mult).
            ewma_states: Optional EWMA state dict (reserved for future use).
            account_config: Optional dict with "starting_balance" and
                "max_contracts" keys (overrides account_capital and
                tsm_max_contracts when provided).

        Returns:
            List of canonical trade dicts:
                {day, pnl, contracts, direction, regime}
        """
        # Normalise alternate calling convention
        if trades is None and raw_trades is not None:
            trades = raw_trades
        if trades is None:
            trades = []
        if regime_labels is None:
            regime_labels = {}
        if aim_weights is None:
            aim_weights = {}
        if kelly_params is None:
            kelly_params = {}
        if strategy_params is not None:
            sl_mult = strategy_params.get("sl_multiplier", sl_mult)
            tp_mult = strategy_params.get("tp_multiplier", tp_mult)
        if account_config is not None:
            account_capital = account_config.get("starting_balance", account_capital)
            tsm_max_contracts = account_config.get("max_contracts", tsm_max_contracts)

        or_range = or_range_override if or_range_override is not None else self.or_range

        # Risk per contract uses the NEW SL, not the old one
        if risk_per_contract is None:
            risk_per_contract = sl_mult * or_range * self.point_value

        asset_kelly = kelly_params.get(self.asset, kelly_params)

        results = []
        for trade in trades:
            day = trade["day"]
            direction = trade.get("direction", 1)
            raw_r_mi = trade.get("raw_r_mi")

            if raw_r_mi is None:
                logger.warning("Trade on %s missing raw_r_mi, skipping", day)
                continue

            # Optional threshold filter: skip trades that would not trigger
            # under the proposed threshold. The threshold applies to the
            # signal strength (x_mik), not r_mi directly, but for replay
            # purposes we can use it as a minimum-conviction filter on the
            # feature value if provided in the trade dict.
            if threshold is not None:
                x_mik = trade.get("x_mik", trade.get("feature_value"))
                if x_mik is not None and abs(x_mik) < abs(threshold):
                    continue

            # 1. Simulate exit under new SL/TP
            #    raw_r_mi is the actual return expressed in OR-range multiples.
            #    Positive = profitable for the direction taken.
            if raw_r_mi <= -sl_mult:
                # SL hit: capped loss at sl_mult OR-range multiples
                per_contract_pnl = -sl_mult * or_range * self.point_value
            elif raw_r_mi >= tp_mult:
                # TP hit: capped profit at tp_mult OR-range multiples
                per_contract_pnl = tp_mult * or_range * self.point_value
            else:
                # EOD exit: actual return (no stop triggered)
                per_contract_pnl = raw_r_mi * or_range * self.point_value

            # 2. Look up regime
            raw_regime = regime_labels.get(day, "LOW")
            regime = _REGIME_MAP.get(raw_regime, "LOW_VOL")

            # 3. Compute sizing (same logic as sizing_replay)
            combined_modifier = self._compute_aim_modifier(aim_weights)
            blended_kelly = self._compute_blended_kelly(asset_kelly)
            adjusted_kelly = blended_kelly * shrinkage_factor
            kelly_with_aim = adjusted_kelly * combined_modifier

            if risk_per_contract > 0:
                raw_contracts = kelly_with_aim * account_capital / risk_per_contract
            else:
                raw_contracts = 1.0
            contracts = max(1, math.floor(raw_contracts))
            contracts = min(contracts, tsm_max_contracts)

            # 4. Final P&L
            pnl = round(per_contract_pnl * contracts, 2)

            results.append({
                "day": day,
                "pnl": pnl,
                "contracts": contracts,
                "direction": direction,
                "regime": regime,
            })

        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_aim_modifier(aim_weights: dict[str, float]) -> float:
        """Compute combined AIM modifier from DMA-weighted average.

        aim_weights maps AIM component names to their current modifier
        values (already weighted by DMA). The combined modifier is their
        average, clamped to [0.5, 1.5].

        If aim_weights is empty or all zero, returns 1.0 (neutral).
        """
        if not aim_weights:
            return 1.0

        values = [v for v in aim_weights.values() if v is not None]
        if not values:
            return 1.0

        raw = sum(values) / len(values)
        return max(0.5, min(1.5, raw))

    @staticmethod
    def _compute_blended_kelly(
        asset_kelly: dict[str, dict],
    ) -> float:
        """Compute blended Kelly fraction across regimes.

        asset_kelly: {regime: {"kelly_full": float, "prob": float}}
        Blended = sum(prob_r * kelly_full_r for each regime).

        If regime probabilities are missing, falls back to equal weighting.
        """
        if not asset_kelly:
            return 0.0

        total_prob = 0.0
        blended = 0.0

        for regime_key, params in asset_kelly.items():
            if not isinstance(params, dict):
                continue
            kelly_full = params.get("kelly_full", 0.0)
            prob = params.get("prob", 0.0)
            blended += prob * kelly_full
            total_prob += prob

        # If probabilities don't sum to ~1, fall back to equal weighting
        if total_prob < 0.01:
            kelly_values = []
            for params in asset_kelly.values():
                if isinstance(params, dict):
                    kf = params.get("kelly_full", 0.0)
                    if kf > 0:
                        kelly_values.append(kf)
            if kelly_values:
                return sum(kelly_values) / len(kelly_values)
            return 0.0

        return blended

    # ------------------------------------------------------------------
    # Static loader: assemble replay context from on-disk data
    # ------------------------------------------------------------------

    @staticmethod
    def load_replay_context(
        asset: str = "ES",
        data_dir: str | None = None,
        trade_source_mode: str = "synthetic",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict:
        """Load all data needed for a replay run.

        Returns a dict with:
            trades: list[dict]         — from trade_source.load_trades()
            regime_labels: dict        — from P2 d02 JSON
            locked_strategy: dict      — from P2 d06 JSON
            kelly_params: dict         — default placeholder (override with live)
            aim_weights: dict          — default placeholder (override with live)
            or_range: float            — asset's default OR range
            point_value: float         — asset's point value

        This is a convenience helper. Callers can also assemble these
        dicts manually from any source and pass them to sizing_replay()
        or strategy_replay() directly.
        """
        from shared.trade_source import load_trades

        asset_upper = asset.upper()
        base_dir = Path(data_dir) if data_dir else _DATA_DIR

        # 1. Load trades
        trades = load_trades(
            source=trade_source_mode,
            asset=asset_upper,
            start_date=start_date,
            end_date=end_date,
            data_dir=str(base_dir / "p1_outputs") if data_dir else None,
        )
        logger.info("Loaded %d trades for %s via %s",
                     len(trades), asset_upper, trade_source_mode)

        # 2. Load regime labels (P2 d02)
        regime_labels = {}
        d02_path = base_dir / "p2_outputs" / asset_upper / "p2_d02_regime_labels.json"
        if d02_path.exists():
            with open(d02_path) as f:
                regime_labels = json.load(f)
            logger.info("Loaded %d regime labels from %s",
                         len(regime_labels), d02_path)
        else:
            logger.warning("P2 d02 regime labels not found at %s", d02_path)

        # 3. Load locked strategy (P2 d06)
        locked_strategy = {}
        d06_path = base_dir / "p2_outputs" / asset_upper / "p2_d06_locked_strategy.json"
        if d06_path.exists():
            with open(d06_path) as f:
                locked_strategy = json.load(f)
            logger.info("Loaded locked strategy from %s: m=%s, k=%s, threshold=%s",
                         d06_path,
                         locked_strategy.get("m"),
                         locked_strategy.get("k"),
                         locked_strategy.get("threshold"))
        else:
            logger.warning("P2 d06 locked strategy not found at %s", d06_path)

        # 4. Default Kelly params (placeholder — override with live EWMA/Kelly)
        #    Using conservative defaults that produce ~1 contract at $150K.
        kelly_params = {
            asset_upper: {
                "LOW_VOL": {"kelly_full": 0.10, "prob": 0.68},
                "HIGH_VOL": {"kelly_full": 0.04, "prob": 0.32},
            }
        }

        # 5. Default AIM weights (neutral = 1.0)
        aim_weights = {"neutral": 1.0}

        return {
            "trades": trades,
            "regime_labels": regime_labels,
            "locked_strategy": locked_strategy,
            "kelly_params": kelly_params,
            "aim_weights": aim_weights,
            "or_range": DEFAULT_OR_RANGES.get(asset_upper, 4.0),
            "point_value": POINT_VALUES.get(asset_upper, 50.0),
        }
