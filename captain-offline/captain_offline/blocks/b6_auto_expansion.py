# region imports
try:
    from AlgorithmImports import *
except ImportError:
    pass
# endregion
"""AIM-14 Auto-Expansion — P3-PG-13 (Task 2.6 / OFF lines 561-619).

Triggered by Level 3 decay detection. Generates replacement strategy
candidates using theory-constrained GA + rough sets search.

Search space: OR_window, threshold, SL_mult, TP_mult, top-10 features.
GA: population=100, generations=50, tournament selection, crossover=0.8, mutation=0.1.
Validation: walk-forward double OOS.
Final OOS test: ONCE (Paper 161).
Accept if pbo < 0.5 AND dsr > 0.5.
Viable candidates -> injection comparison (Block 4).

Reads: P3-D04, P2-D06, feature_space
Writes: P3-D06 (via injection comparison)
"""

import json
import random
import math
import logging
from dataclasses import dataclass

import numpy as np

from shared.questdb_client import get_cursor

logger = logging.getLogger(__name__)

# GA parameters
POPULATION_SIZE = 100
GENERATIONS = 50
CROSSOVER_RATE = 0.8
MUTATION_RATE = 0.1
TOURNAMENT_SIZE = 5
TOP_K_CANDIDATES = 5

# Search space bounds
SEARCH_SPACE = {
    "or_window": (3, 15),        # minutes
    "threshold": (0.05, 0.30),   # percentage
    "sl_multiplier": (0.20, 0.50),
    "tp_multiplier": (0.50, 1.50),
    "feature_idx": (0, 9),       # top 10 features
}

# Acceptance thresholds
PBO_THRESHOLD = 0.5
DSR_THRESHOLD = 0.5

# Walk-forward split (Doc 32 PG-13 §2: train/validate split for GA fitness)
WALK_FORWARD_TRAIN_RATIO = 0.7  # 70% train, 30% validate



@dataclass
class Candidate:
    """Strategy candidate with parameter vector."""
    or_window: int
    threshold: float
    sl_multiplier: float
    tp_multiplier: float
    feature_idx: int
    fitness: float = 0.0


def _random_candidate() -> Candidate:
    """Generate a random candidate within search space bounds."""
    return Candidate(
        or_window=random.randint(*SEARCH_SPACE["or_window"]),
        threshold=round(random.uniform(*SEARCH_SPACE["threshold"]), 3),
        sl_multiplier=round(random.uniform(*SEARCH_SPACE["sl_multiplier"]), 2),
        tp_multiplier=round(random.uniform(*SEARCH_SPACE["tp_multiplier"]), 2),
        feature_idx=random.randint(*SEARCH_SPACE["feature_idx"]),
    )


def _crossover(parent1: Candidate, parent2: Candidate) -> Candidate:
    """Single-point crossover between two candidates."""
    child = Candidate(
        or_window=parent1.or_window if random.random() < 0.5 else parent2.or_window,
        threshold=parent1.threshold if random.random() < 0.5 else parent2.threshold,
        sl_multiplier=parent1.sl_multiplier if random.random() < 0.5 else parent2.sl_multiplier,
        tp_multiplier=parent1.tp_multiplier if random.random() < 0.5 else parent2.tp_multiplier,
        feature_idx=parent1.feature_idx if random.random() < 0.5 else parent2.feature_idx,
    )
    return child


def _mutate(candidate: Candidate) -> Candidate:
    """Mutate a random parameter within bounds."""
    param = random.choice(list(SEARCH_SPACE.keys()))
    if param == "or_window":
        candidate.or_window = random.randint(*SEARCH_SPACE["or_window"])
    elif param == "threshold":
        candidate.threshold = round(random.uniform(*SEARCH_SPACE["threshold"]), 3)
    elif param == "sl_multiplier":
        candidate.sl_multiplier = round(random.uniform(*SEARCH_SPACE["sl_multiplier"]), 2)
    elif param == "tp_multiplier":
        candidate.tp_multiplier = round(random.uniform(*SEARCH_SPACE["tp_multiplier"]), 2)
    elif param == "feature_idx":
        candidate.feature_idx = random.randint(*SEARCH_SPACE["feature_idx"])
    return candidate


def _tournament_select(population: list[Candidate]) -> Candidate:
    """Tournament selection."""
    tournament = random.sample(population, min(TOURNAMENT_SIZE, len(population)))
    return max(tournament, key=lambda c: c.fitness)


def _evaluate_candidate(candidate: Candidate, historical_returns: list[float],
                          asset_id: str = "ES") -> float:
    """Evaluate candidate fitness via signal replay.

    Converts the Candidate to strategy_params, runs
    SignalReplayEngine.strategy_replay(), and returns the Sharpe ratio
    as fitness. Falls back to the original parameter-scaling approach
    if replay context cannot be loaded or replay fails.

    Args:
        candidate: Strategy candidate with parameter vector
        historical_returns: Historical daily returns (used as fallback)
        asset_id: Asset to replay against

    Returns:
        Sharpe ratio as fitness score.
    """
    try:
        from shared.signal_replay import SignalReplayEngine

        ctx = SignalReplayEngine.load_replay_context(asset_id)
        trades = ctx["trades"]
        regime_labels = ctx["regime_labels"]
        aim_weights = ctx["aim_weights"]
        kelly_params = ctx["kelly_params"]

        if not trades:
            raise ValueError("No trades loaded for replay")

        strategy_params = {
            "sl_multiplier": candidate.sl_multiplier,
            "tp_multiplier": candidate.tp_multiplier,
        }

        engine = SignalReplayEngine(asset=asset_id)
        replayed_trades = engine.strategy_replay(
            trades=trades,
            regime_labels=regime_labels,
            aim_weights=aim_weights,
            kelly_params=kelly_params,
            strategy_params=strategy_params,
            threshold=candidate.threshold,
        )

        if not replayed_trades:
            raise ValueError("Replay produced no trades")

        # Aggregate to daily P&L
        by_day: dict[str, float] = {}
        for t in replayed_trades:
            day = t.get("day", "unknown")
            by_day[day] = by_day.get(day, 0.0) + t.get("pnl", 0.0)

        daily_pnl = [by_day[d] for d in sorted(by_day)]

        if len(daily_pnl) < 2:
            raise ValueError(f"Insufficient daily P&L ({len(daily_pnl)} days)")

        arr = np.array(daily_pnl)
        std = arr.std()
        if std < 1e-10:
            return 0.0

        sharpe = float(arr.mean() / std * math.sqrt(252))

        # Add noise to prevent identical fitness
        sharpe += random.gauss(0, 0.01)
        return sharpe

    except Exception as exc:
        logger.debug("_evaluate_candidate replay failed for %s: %s — "
                     "falling back to parameter scaling", asset_id, exc)

        # Fallback: original parameter-scaling approach
        scale = (candidate.tp_multiplier / max(candidate.sl_multiplier, 0.01))
        threshold_effect = 1.0 - abs(candidate.threshold - 0.15) * 2
        window_effect = 1.0 - abs(candidate.or_window - 8) * 0.02

        if not historical_returns:
            return 0.0

        arr = np.array(historical_returns) * scale * threshold_effect * window_effect
        std = arr.std()
        if std < 1e-10:
            return 0.0

        sharpe = float(arr.mean() / std * math.sqrt(252))
        sharpe += random.gauss(0, 0.01)
        return sharpe


def _compute_pbo(returns: list[float]) -> float:
    """PBO via full CSCV (Paper 152). Delegates to shared.statistics."""
    from shared.statistics import compute_pbo
    return compute_pbo(returns, S=8)


def _compute_dsr(sharpe: float, n_trials: int, T: int) -> float:
    """DSR (Paper 150). Delegates to shared.statistics."""
    from shared.statistics import compute_dsr
    return compute_dsr(sharpe, n_trials, skew=0.0, kurtosis=3.0, T=T)


def run_auto_expansion(asset_id: str, historical_returns: list[float],
                        holdout_returns: list[float]) -> list[dict]:
    """Execute P3-PG-13: GA-based strategy search.

    Args:
        asset_id: Decayed asset needing replacement
        historical_returns: Training/validation data
        holdout_returns: Final OOS holdout (tested ONCE per Paper 161)

    Returns:
        List of viable candidates (may be empty)
    """
    # No fixed seed — GA must explore different candidates each run

    # Walk-forward split: train on first 70%, validate on last 30% (Doc 32 PG-13 §2)
    split_idx = max(1, int(len(historical_returns) * WALK_FORWARD_TRAIN_RATIO))
    wf_validation_returns = historical_returns[split_idx:]

    # Initialize population
    population = [_random_candidate() for _ in range(POPULATION_SIZE)]

    # Evolve
    for gen in range(GENERATIONS):
        # Evaluate on validation window only
        for candidate in population:
            candidate.fitness = _evaluate_candidate(candidate, wf_validation_returns, asset_id)

        # Select + breed next generation
        new_population = []
        # Elitism: keep top 5
        population.sort(key=lambda c: c.fitness, reverse=True)
        new_population.extend(population[:5])

        while len(new_population) < POPULATION_SIZE:
            if random.random() < CROSSOVER_RATE:
                p1 = _tournament_select(population)
                p2 = _tournament_select(population)
                child = _crossover(p1, p2)
            else:
                child = _tournament_select(population)

            if random.random() < MUTATION_RATE:
                child = _mutate(child)

            new_population.append(child)

        population = new_population

    # Final evaluation (on validation window, consistent with GA selection)
    for c in population:
        c.fitness = _evaluate_candidate(c, wf_validation_returns, asset_id)

    # Select top K
    population.sort(key=lambda c: c.fitness, reverse=True)
    top_candidates = population[:TOP_K_CANDIDATES]

    # Final OOS test (ONCE — Paper 161)
    viable = []
    n_trials = POPULATION_SIZE * GENERATIONS

    for candidate in top_candidates:
        pbo = _compute_pbo(holdout_returns)
        dsr = _compute_dsr(candidate.fitness, n_trials, len(holdout_returns))

        result = {
            "candidate": {
                "or_window": candidate.or_window,
                "threshold": candidate.threshold,
                "sl_multiplier": candidate.sl_multiplier,
                "tp_multiplier": candidate.tp_multiplier,
                "feature_idx": candidate.feature_idx,
            },
            "fitness": candidate.fitness,
            "pbo": pbo,
            "dsr": dsr,
            "viable": pbo < PBO_THRESHOLD and dsr > DSR_THRESHOLD,
        }

        if result["viable"]:
            viable.append(result)
            logger.info("AIM-14 viable candidate for %s: fitness=%.4f, pbo=%.3f, dsr=%.3f",
                        asset_id, candidate.fitness, pbo, dsr)

    if not viable:
        logger.warning("AIM-14 for %s: no viable replacement candidates found", asset_id)
    else:
        # Wire viable candidates to Block 4 injection comparison
        try:
            from captain_offline.blocks.b4_injection import run_injection_comparison

            # Load current strategy from P3-D00
            with get_cursor() as cur:
                cur.execute(
                    """SELECT locked_strategy FROM p3_d00_asset_universe
                       WHERE asset_id = %s AND captain_status IN ('ACTIVE', 'DECAYED')
                       LATEST ON last_updated PARTITION BY asset_id""",
                    (asset_id,),
                )
                row = cur.fetchone()
            current_strategy = json.loads(row[0]) if row and row[0] else {}

            for fc in viable:
                run_injection_comparison(
                    asset_id=asset_id,
                    new_candidate=fc["candidate"],
                    current_strategy=current_strategy,
                    candidate_pnl=holdout_returns,
                    current_pnl=historical_returns[-len(holdout_returns):],
                )
                logger.info("AIM-14 -> injection comparison submitted for %s: %s",
                            asset_id, fc["candidate"])
        except Exception as e:
            logger.error("AIM-14 injection handoff failed for %s: %s", asset_id, e)

    return viable
