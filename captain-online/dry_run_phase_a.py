#!/usr/bin/env python3
"""Dry run of Phase A (B1-B5C) — validates the full pipeline without trading.

Run inside the captain-online container:
  docker compose exec captain-online python3 /app/dry_run_phase_a.py

This calls the same functions as the orchestrator's _run_session() but:
  - Does NOT publish signals to Redis
  - Does NOT register assets with the OR tracker
  - Does NOT mark the session as evaluated (orchestrator state is in-memory)
  - Does NOT trigger Phase B (B6 signal output)

Note: B1 data ingestion writes diagnostic data (data_quality_flag, session_log)
to QuestDB. These are idempotent and do not affect trading decisions.
"""

import json
import logging
import os
import sys

sys.path.insert(0, "/app")

from shared.decimal_boundary import as_money, to_float

logging.basicConfig(
    level=logging.INFO,
    format="[DRY-RUN] %(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("dry_run")

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"


def main():
    session_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    session_names = {1: "NY", 2: "LON", 3: "APAC"}
    session_name = session_names.get(session_id, "UNKNOWN")

    results = {}

    logger.info("=" * 70)
    logger.info("PHASE A DRY RUN — Session %s (%d)", session_name, session_id)
    logger.info("=" * 70)

    # ── Infrastructure check ──
    logger.info("Checking infrastructure...")
    try:
        from shared.questdb_client import get_connection
        conn = get_connection()
        conn.close()
        logger.info("  QuestDB: OK")
    except Exception as e:
        logger.error("  QuestDB: FAILED — %s", e)
        results["infra"] = FAIL
        _summary(results)
        return False

    try:
        from shared.redis_client import get_redis_client
        get_redis_client().ping()
        logger.info("  Redis: OK")
    except Exception as e:
        logger.error("  Redis: FAILED — %s", e)
        results["infra"] = FAIL
        _summary(results)
        return False

    results["infra"] = PASS

    # ── B1: Data ingestion ──
    logger.info("-" * 70)
    logger.info("B1: Data ingestion...")
    try:
        from captain_online.blocks.b1_data_ingestion import run_data_ingestion
        data = run_data_ingestion(session_id)
        if data is None:
            logger.error("B1: returned None — no active assets for session %s", session_name)
            results["B1"] = FAIL
            _summary(results)
            return False

        n_assets = len(data.get("active_assets", []))
        n_features = sum(len(f) for f in data.get("features", {}).values())
        logger.info("B1: %d assets, %d features computed", n_assets, n_features)
        logger.info("  Assets: %s", data["active_assets"])

        # Check critical data loaded
        for key in ["kelly_params", "ewma_states", "tsm_configs", "locked_strategies"]:
            count = len(data.get(key, {}))
            status = PASS if count > 0 else WARN
            logger.info("  %-20s: %d entries [%s]", key, count, status)

        results["B1"] = PASS
    except Exception as e:
        logger.error("B1 CRASHED: %s", e, exc_info=True)
        results["B1"] = FAIL
        _summary(results)
        return False

    # ── B2: Regime probability ──
    logger.info("-" * 70)
    logger.info("B2: Regime probability...")
    try:
        from captain_online.blocks.b2_regime_probability import run_regime_probability
        regime = run_regime_probability(
            data["active_assets"], data["features"], data["regime_models"]
        )
        for asset, probs in regime.get("regime_probs", {}).items():
            dominant = max(probs, key=probs.get)
            logger.info("  %-6s: %s  → %s", asset,
                        {k: f"{v:.2f}" for k, v in probs.items()}, dominant)

        uncertain = regime.get("regime_uncertain", {})
        if any(uncertain.values()):
            logger.warning("  Uncertain: %s", [a for a, u in uncertain.items() if u])

        results["B2"] = PASS
    except Exception as e:
        logger.error("B2 CRASHED: %s", e, exc_info=True)
        results["B2"] = FAIL
        _summary(results)
        return False

    # ── B3: AIM aggregation ──
    logger.info("-" * 70)
    logger.info("B3: AIM aggregation...")
    try:
        from shared.aim_compute import run_aim_aggregation
        aim = run_aim_aggregation(
            data["active_assets"], data["features"],
            data["aim_states"], data["aim_weights"]
        )
        for asset, mod in sorted(aim.get("combined_modifier", {}).items()):
            logger.info("  %-6s: combined_modifier=%.4f", asset, mod)

        results["B3"] = PASS
    except Exception as e:
        logger.error("B3 CRASHED: %s", e, exc_info=True)
        results["B3"] = FAIL
        _summary(results)
        return False

    # ── Load users + silos ──
    logger.info("-" * 70)
    logger.info("Loading users and capital silos...")
    from shared.questdb_client import get_cursor
    from shared.json_helpers import parse_json

    with get_cursor() as cur:
        cur.execute(
            "SELECT user_id, role FROM p3_d15_user_session_data "
            "ORDER BY last_active DESC"
        )
        rows = cur.fetchall()

    seen = set()
    users = []
    for r in rows:
        if r[0] not in seen:
            seen.add(r[0])
            users.append({"user_id": r[0], "role": r[1]})
    if not users:
        users = [{"user_id": os.environ.get("BOOTSTRAP_USER_ID", "primary_user"),
                  "role": "ADMIN"}]

    logger.info("  Users: %s", [u["user_id"] for u in users])

    any_user_passed = False

    for user in users:
        user_id = user["user_id"]
        logger.info("-" * 70)
        logger.info("Per-user pipeline for: %s", user_id)

        with get_cursor() as cur:
            cur.execute(
                """SELECT user_id, starting_capital, total_capital, accounts,
                          max_simultaneous_positions, max_portfolio_risk_pct,
                          correlation_threshold, user_kelly_ceiling
                   FROM p3_d16_user_capital_silos
                   WHERE user_id = %s
                   LATEST ON last_updated PARTITION BY user_id""",
                (user_id,),
            )
            row = cur.fetchone()

        if row is None:
            logger.error("  NO CAPITAL SILO — B4 will skip this user")
            results[f"silo_{user_id}"] = FAIL
            continue

        # Phase 4 boundary discipline: D16 monetary fields stay Decimal
        # via as_money so this dry-run mirrors the production orchestrator
        # path. The display arithmetic below converts at the explicit
        # to_float boundary.
        user_silo = {
            "user_id": row[0],
            "starting_capital": as_money(row[1]),
            "total_capital": as_money(row[2]),
            "accounts": row[3] or "[]",
            "max_simultaneous_positions": row[4],
            "max_portfolio_risk_pct": row[5] if row[5] is not None else 0.10,  # decimal-boundary: ok
            "correlation_threshold": row[6] if row[6] is not None else 0.7,  # decimal-boundary: ok
            "user_kelly_ceiling": row[7] if row[7] is not None else 1.0,  # decimal-boundary: ok
        }

        accounts = parse_json(user_silo.get("accounts", "[]"), [])
        _total = to_float(user_silo["total_capital"])
        _starting = to_float(user_silo["starting_capital"])
        logger.info("  Capital: $%.0f / $%.0f (%.1f%% drawdown)",
                     _total, _starting,
                     (1 - _total / max(_starting, 1.0)) * 100)
        logger.info("  Accounts: %s", accounts)
        logger.info("  Max positions: %s", user_silo["max_simultaneous_positions"])

        if not accounts:
            logger.error("  NO ACCOUNTS in silo — signals will have empty per_account")
            results[f"silo_{user_id}"] = FAIL
            continue

        results[f"silo_{user_id}"] = PASS

        # ── B4: Kelly sizing ──
        logger.info("  B4: Kelly sizing...")
        try:
            from captain_online.blocks.b4_kelly_sizing import run_kelly_sizing
            sizing = run_kelly_sizing(
                active_assets=data["active_assets"],
                regime_probs=regime["regime_probs"],
                regime_uncertain=regime["regime_uncertain"],
                combined_modifier=aim["combined_modifier"],
                kelly_params=data["kelly_params"],
                ewma_states=data["ewma_states"],
                tsm_configs=data["tsm_configs"],
                sizing_overrides=data["sizing_overrides"],
                user_silo=user_silo,
                locked_strategies=data["locked_strategies"],
                assets_detail=data["assets_detail"],
                session_id=session_id,
            )

            if sizing is None:
                logger.error("  B4: returned None")
                results[f"B4_{user_id}"] = FAIL
                continue
            if sizing.get("silo_blocked"):
                logger.error("  B4: SILO BLOCKED (drawdown exceeded)")
                results[f"B4_{user_id}"] = FAIL
                continue

            non_zero = {}
            for a, accts in sizing["final_contracts"].items():
                nz = {ac: c for ac, c in accts.items() if c > 0}
                if nz:
                    non_zero[a] = nz
            logger.info("  B4: %d assets with non-zero contracts", len(non_zero))
            for asset, accts in non_zero.items():
                logger.info("    %-6s: %s", asset, accts)

            if not non_zero:
                logger.warning("  B4: ALL contracts are zero — no trades will be sized")

            results[f"B4_{user_id}"] = PASS
        except Exception as e:
            logger.error("  B4 CRASHED: %s", e, exc_info=True)
            results[f"B4_{user_id}"] = FAIL
            continue

        # ── B5: Trade selection ──
        logger.info("  B5: Trade selection...")
        try:
            from captain_online.blocks.b5_trade_selection import (
                run_trade_selection, apply_hmm_session_allocation,
            )
            trades = run_trade_selection(
                active_assets=data["active_assets"],
                final_contracts=sizing["final_contracts"],
                account_recommendation=sizing["account_recommendation"],
                account_skip_reason=sizing["account_skip_reason"],
                ewma_states=data["ewma_states"],
                regime_probs=regime["regime_probs"],
                user_silo=user_silo,
                session_id=session_id,
            )
            trades["final_contracts"] = apply_hmm_session_allocation(
                trades["selected_trades"], trades["final_contracts"],
                accounts, session_id,
            )
            selected = trades.get("selected_trades", [])
            logger.info("  B5: %d trades selected: %s", len(selected), selected)

            results[f"B5_{user_id}"] = PASS
        except Exception as e:
            logger.error("  B5 CRASHED: %s", e, exc_info=True)
            results[f"B5_{user_id}"] = FAIL
            continue

        # ── B5B: Quality gate ──
        logger.info("  B5B: Quality gate...")
        try:
            from captain_online.blocks.b5b_quality_gate import run_quality_gate
            quality = run_quality_gate(
                selected_trades=trades["selected_trades"],
                expected_edge=trades["expected_edge"],
                combined_modifier=aim["combined_modifier"],
                regime_probs=regime["regime_probs"],
                user_silo=user_silo,
                session_id=session_id,
                final_contracts=trades["final_contracts"],
            )
            recommended = quality.get("recommended_trades", [])
            below = quality.get("available_not_recommended", [])
            logger.info("  B5B: %d recommended, %d below threshold", len(recommended), len(below))
            logger.info("    Recommended: %s", recommended)
            if below:
                logger.info("    Below threshold: %s", below)

            results[f"B5B_{user_id}"] = PASS
        except Exception as e:
            logger.error("  B5B CRASHED: %s", e, exc_info=True)
            results[f"B5B_{user_id}"] = FAIL
            continue

        # ── B5C: Circuit breaker screen ──
        logger.info("  B5C: Circuit breaker screen...")
        try:
            from captain_online.blocks.b5c_circuit_breaker import run_circuit_breaker_screen
            cb_result = run_circuit_breaker_screen(
                recommended_trades=quality["recommended_trades"],
                final_contracts=trades["final_contracts"],
                account_recommendation=trades["account_recommendation"],
                account_skip_reason=trades["account_skip_reason"],
                accounts=accounts,
                tsm_configs=data["tsm_configs"],
                session_id=session_id,
                proposed_contracts=trades["final_contracts"],
                locked_strategies=data["locked_strategies"],
                assets_detail=data["assets_detail"],
            )
            final = cb_result.get("recommended_trades", [])
            logger.info("  B5C: %d trades passed: %s", len(final), final)

            results[f"B5C_{user_id}"] = PASS
        except Exception as e:
            logger.error("  B5C CRASHED: %s", e, exc_info=True)
            results[f"B5C_{user_id}"] = FAIL
            continue

        # ── Verdict for this user ──
        if final:
            logger.info("  >>> %s: %d assets would proceed to Phase B (B6 signal output)",
                        user_id, len(final))
            any_user_passed = True
        else:
            logger.warning("  >>> %s: ZERO trades recommended — Phase B would produce no signals",
                           user_id)

    _summary(results)

    if any_user_passed:
        logger.info("VERDICT: Phase A would produce signals. System ready to trade.")
    else:
        logger.warning("VERDICT: Phase A completes but NO trades recommended. "
                       "Check sizing, quality gate, and circuit breaker output above.")

    return any_user_passed


def _summary(results: dict):
    logger.info("=" * 70)
    logger.info("RESULTS SUMMARY")
    logger.info("=" * 70)
    for key, status in results.items():
        icon = {PASS: "OK", FAIL: "FAILED", WARN: "WARN"}.get(status, "?")
        logger.info("  %-30s [%s]", key, icon)

    failed = [k for k, v in results.items() if v == FAIL]
    if failed:
        logger.error("FAILURES: %s", failed)
    else:
        logger.info("All checks passed.")


if __name__ == "__main__":
    try:
        ok = main()
        sys.exit(0 if ok else 1)
    except Exception as e:
        logger.error("DRY RUN CRASHED: %s", e, exc_info=True)
        sys.exit(1)
