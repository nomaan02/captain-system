#!/usr/bin/env python3
"""AIM A/B Validation — Replay-Based Statistical Testing.

Runs headless batch replay with AIMs ON vs OFF for ~20 trading days,
collects per-asset metrics, and produces a structured validation report.

Usage (inside captain-command container):
    python3 scripts/aim_ab_test.py
"""

import json
import logging
import sys
from datetime import date, timedelta

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Date generation — last 20 trading days before today
# ---------------------------------------------------------------------------

def trading_days(end: date, count: int) -> list[date]:
    """Generate the last *count* weekdays up to and including *end*."""
    days = []
    d = end
    while len(days) < count:
        if d.weekday() < 5:  # Mon-Fri
            days.append(d)
        d -= timedelta(days=1)
    days.reverse()
    return days


# ---------------------------------------------------------------------------
# AIM-04 IVTS zone expected modifier
# ---------------------------------------------------------------------------

def ivts_expected_modifier(ivts: float | None) -> tuple[float, str]:
    """Return (expected_modifier, zone_name) per DEC-03 spec."""
    if ivts is None:
        return 1.0, "MISSING"
    if ivts > 1.10:
        return 0.65, "SEVERE_BACKWARDATION"
    if ivts > 1.0:
        return 0.80, "BACKWARDATION"
    if ivts >= 0.93:
        return 1.10, "OPTIMAL"
    if ivts >= 0.85:
        return 0.90, "QUIET"
    return 0.80, "DEEP_QUIET"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

AIM_NAMES = {
    1: "VRP", 2: "Skew", 3: "GEX", 4: "IVTS", 5: "Deferred",
    6: "Calendar", 7: "COT", 8: "Correlation", 9: "Momentum",
    10: "Calendar Fx", 11: "Regime Warn", 12: "Dyn Costs",
    13: "Sensitivity", 14: "Expansion", 15: "Volume", 16: "HMM",
}

# AIMs that should NEVER fire (no data feed)
EXPECT_NEUTRAL = {3, 5, 7}
# AIMs that SHOULD fire when data exists
# Note: AIM-06 (Calendar) has no data in replay (no calendar feed) — expected neutral
EXPECT_ACTIVE = {4, 8, 9, 10, 11, 15}


def main():
    from shared.replay_engine import load_replay_config, run_replay
    from shared.aim_feature_loader import load_replay_features

    # Determine test dates
    today = date(2026, 4, 1)
    dates = trading_days(date(2026, 3, 28), 20)
    print(f"AIM A/B Test — {len(dates)} trading days: {dates[0]} to {dates[-1]}")
    print("=" * 80)

    # Load config once (shared between ON/OFF runs)
    base_config = load_replay_config()
    user_capital = base_config.get("user_capital", 150000)
    risk_goal = base_config.get("risk_goal", "GROW_CAPITAL")
    max_positions = base_config.get("max_positions", 5)

    print(f"Config: Capital=${user_capital:,.0f}, Risk Goal={risk_goal}, Max Positions={max_positions}")
    print()

    # Collectors
    all_days = []           # [{date, on_results, off_results, aim_breakdown, combined_modifier, features}]
    skipped_dates = []

    for idx, target in enumerate(dates):
        print(f"Day {idx+1}/{len(dates)}: {target} ... ", end="", flush=True)

        # --- Run OFF first (populates bar cache) ---
        config_off = dict(base_config)
        config_off["aim_enabled"] = False
        try:
            result_off = run_replay(config_off, target_date=target, sessions=["NY"])
        except Exception as exc:
            print(f"SKIP (OFF failed: {exc})")
            skipped_dates.append((target, str(exc)))
            continue

        # --- Run ON (reuses cached bars) ---
        config_on = dict(base_config)
        config_on["aim_enabled"] = True
        try:
            result_on = run_replay(config_on, target_date=target, sessions=["NY"])
        except Exception as exc:
            print(f"SKIP (ON failed: {exc})")
            skipped_dates.append((target, str(exc)))
            continue

        # --- Collect AIM details for this day ---
        # Load features separately to get IVTS and per-AIM breakdown
        try:
            from shared.aim_compute import run_aim_aggregation
            ny_assets = ["ES", "MES", "NQ", "MNQ", "M2K", "MYM"]
            features, aim_states, aim_weights = load_replay_features(target, ny_assets)
            aim_output = run_aim_aggregation(ny_assets, features, aim_states, aim_weights)
            combined_mod = aim_output.get("combined_modifier", {})
            breakdown = aim_output.get("aim_breakdown", {})
        except Exception as exc:
            combined_mod = {}
            breakdown = {}
            features = {}

        pnl_on = result_on.get("total_pnl", 0)
        pnl_off = result_off.get("total_pnl", 0)
        trades_on = len(result_on.get("trades_taken", []))
        trades_off = len(result_off.get("trades_taken", []))

        print(f"ON: ${pnl_on:+.2f} ({trades_on}t) | OFF: ${pnl_off:+.2f} ({trades_off}t) | delta: ${pnl_on - pnl_off:+.2f}")

        all_days.append({
            "date": target,
            "result_on": result_on,
            "result_off": result_off,
            "combined_modifier": combined_mod,
            "aim_breakdown": breakdown,
            "features": features,
        })

    print()
    print("=" * 80)
    print(f"Completed: {len(all_days)} days, skipped: {len(skipped_dates)}")
    print()

    if not all_days:
        print("ERROR: No days completed. Cannot generate report.")
        sys.exit(1)

    # ===================================================================
    # ANALYSIS
    # ===================================================================

    # Build per-asset-day records
    asset_day_records = []
    for day in all_days:
        d = day["date"]
        cm = day["combined_modifier"]
        bd = day["aim_breakdown"]
        feats = day["features"]

        # Index results by asset
        on_by_asset = {r["asset"]: r for r in day["result_on"].get("results", []) if "asset" in r}
        off_by_asset = {r["asset"]: r for r in day["result_off"].get("results", []) if "asset" in r}

        # Selected (position-limited) assets
        on_selected = {r["asset"] for r in day["result_on"].get("trades_taken", [])}
        off_selected = {r["asset"] for r in day["result_off"].get("trades_taken", [])}

        for asset in set(list(on_by_asset.keys()) + list(off_by_asset.keys())):
            r_on = on_by_asset.get(asset, {})
            r_off = off_by_asset.get(asset, {})

            rec = {
                "date": d,
                "asset": asset,
                "combined_modifier": cm.get(asset, 1.0),
                "aim_breakdown": bd.get(asset, {}),
                "features": feats.get(asset, {}),
                "contracts_on": r_on.get("contracts", 0),
                "contracts_off": r_off.get("contracts", 0),
                "pnl_per_contract": r_on.get("pnl_per_contract", r_off.get("pnl_per_contract", 0)),
                "total_pnl_on": r_on.get("total_pnl", 0),
                "total_pnl_off": r_off.get("total_pnl", 0),
                "exit_reason": r_on.get("exit_reason", r_off.get("exit_reason")),
                "direction": r_on.get("direction", r_off.get("direction", 0)),
                "direction_str": r_on.get("direction_str", r_off.get("direction_str", "NO_BREAKOUT")),
                "selected_on": asset in on_selected,
                "selected_off": asset in off_selected,
            }
            asset_day_records.append(rec)

    # ------------------------------------------------------------------
    # Test 1 — AIM Activation Rate
    # ------------------------------------------------------------------
    print("## Test 1 — AIM Activation Rate")
    print()

    # Per-AIM stats
    aim_stats = {}  # {aim_id: {"fired": 0, "neutral": 0, "mod_sum": 0.0}}
    for rec in asset_day_records:
        for aim_id in range(1, 17):
            if aim_id not in aim_stats:
                aim_stats[aim_id] = {"fired": 0, "neutral": 0, "mod_sum": 0.0, "mod_count": 0}
            info = rec["aim_breakdown"].get(aim_id)
            if info is None:
                aim_stats[aim_id]["neutral"] += 1
                continue
            mod = info.get("modifier", 1.0)
            if abs(mod - 1.0) > 0.001:
                aim_stats[aim_id]["fired"] += 1
                aim_stats[aim_id]["mod_sum"] += mod
                aim_stats[aim_id]["mod_count"] += 1
            else:
                aim_stats[aim_id]["neutral"] += 1

    # Combined modifier stats
    n_total = len(asset_day_records)
    n_nonneutral = sum(1 for r in asset_day_records if abs(r["combined_modifier"] - 1.0) > 0.001)
    print(f"  Combined modifier != 1.0: {n_nonneutral}/{n_total} ({100*n_nonneutral/n_total:.1f}%) asset-days")
    print()
    print(f"  {'AIM':>5} {'Name':<14} {'Fired%':>7} {'Neutral%':>9} {'Avg Mod':>8}  Flags")
    print(f"  {'-'*5} {'-'*14} {'-'*7} {'-'*9} {'-'*8}  {'-'*20}")

    aim_flags = []
    for aim_id in range(1, 17):
        s = aim_stats.get(aim_id, {"fired": 0, "neutral": 0, "mod_sum": 0, "mod_count": 0})
        total = s["fired"] + s["neutral"]
        if total == 0:
            continue
        fired_pct = 100 * s["fired"] / total
        neutral_pct = 100 * s["neutral"] / total
        avg_mod = s["mod_sum"] / s["mod_count"] if s["mod_count"] > 0 else 1.0
        flag = ""
        if aim_id in EXPECT_NEUTRAL and s["fired"] > 0:
            flag = "BUG: should be neutral"
            aim_flags.append(f"AIM-{aim_id:02d} fired but has no data source")
        if aim_id in EXPECT_ACTIVE and s["fired"] == 0:
            flag = "WARN: never fired"
            aim_flags.append(f"AIM-{aim_id:02d} has data but never fired")
        print(f"  {aim_id:>5} {AIM_NAMES.get(aim_id, '?'):<14} {fired_pct:>6.1f}% {neutral_pct:>8.1f}% {avg_mod:>7.4f}  {flag}")

    print()

    # ------------------------------------------------------------------
    # Test 2 — Sizing Divergence
    # ------------------------------------------------------------------
    print("## Test 2 — Sizing Divergence")
    print()

    breakout_records = [r for r in asset_day_records if r["direction"] != 0]
    n_breakouts = len(breakout_records)
    n_diff = sum(1 for r in breakout_records if r["contracts_on"] != r["contracts_off"])
    diffs = [r["contracts_on"] - r["contracts_off"] for r in breakout_records]
    abs_diffs = [abs(d) for d in diffs]
    avg_abs_diff = sum(abs_diffs) / len(abs_diffs) if abs_diffs else 0

    print(f"  Breakout asset-days: {n_breakouts}")
    print(f"  With different sizing: {n_diff}/{n_breakouts} ({100*n_diff/n_breakouts:.1f}%)" if n_breakouts else "  No breakouts")
    print(f"  Average |contract difference|: {avg_abs_diff:.2f}")

    if n_diff > 0:
        largest = max(breakout_records, key=lambda r: abs(r["contracts_on"] - r["contracts_off"]))
        print(f"  Largest divergence: {largest['asset']} {largest['date']} — ON={largest['contracts_on']} OFF={largest['contracts_off']}")
    print()

    # ------------------------------------------------------------------
    # Test 3 — P&L Divergence
    # ------------------------------------------------------------------
    print("## Test 3 — P&L Impact")
    print()

    total_on = sum(d["result_on"].get("total_pnl", 0) for d in all_days)
    total_off = sum(d["result_off"].get("total_pnl", 0) for d in all_days)
    delta = total_on - total_off

    print(f"  Total P&L (AIMs ON):  ${total_on:>10.2f}")
    print(f"  Total P&L (AIMs OFF): ${total_off:>10.2f}")
    print(f"  Difference:           ${delta:>+10.2f} ({'AIMs helped' if delta > 0 else 'AIMs hurt'})")
    print()
    print(f"  {'Date':<12} {'P&L ON':>10} {'P&L OFF':>10} {'Delta':>10}")
    print(f"  {'-'*12} {'-'*10} {'-'*10} {'-'*10}")
    for day in all_days:
        d = day["date"]
        p_on = day["result_on"].get("total_pnl", 0)
        p_off = day["result_off"].get("total_pnl", 0)
        print(f"  {d!s:<12} ${p_on:>9.2f} ${p_off:>9.2f} ${p_on - p_off:>+9.2f}")
    print()

    # ------------------------------------------------------------------
    # Test 4 — Directional Correctness
    # ------------------------------------------------------------------
    print("## Test 4 — Directional Correctness")
    print()

    group_a = [r for r in breakout_records if r["combined_modifier"] < 0.999]  # reduced
    group_b = [r for r in breakout_records if r["combined_modifier"] > 1.001]  # boosted
    group_n = [r for r in breakout_records if 0.999 <= r["combined_modifier"] <= 1.001]  # neutral

    def group_stats(group, label):
        if not group:
            return {"label": label, "n": 0, "avg_pnl": 0, "win_rate": 0}
        avg_pnl = sum(r["pnl_per_contract"] for r in group) / len(group)
        wins = sum(1 for r in group if r["pnl_per_contract"] > 0)
        return {"label": label, "n": len(group), "avg_pnl": avg_pnl, "win_rate": 100 * wins / len(group)}

    sa = group_stats(group_a, "Reduced (mod < 1.0)")
    sb = group_stats(group_b, "Boosted (mod > 1.0)")
    sn = group_stats(group_n, "Neutral (mod = 1.0)")

    for s in [sa, sb, sn]:
        print(f"  {s['label']}: {s['n']} trades, avg pnl/ct=${s['avg_pnl']:+.2f}, win rate={s['win_rate']:.1f}%")

    if sa["n"] > 0 and sb["n"] > 0:
        if sa["avg_pnl"] < sb["avg_pnl"]:
            direction_verdict = "CORRECT (reduced group has worse outcomes)"
        elif sa["avg_pnl"] > sb["avg_pnl"]:
            direction_verdict = "INVERTED (reduced group has BETTER outcomes — check logic)"
        else:
            direction_verdict = "INCONCLUSIVE (identical)"
    else:
        direction_verdict = "INCONCLUSIVE (insufficient data in one group)"

    print(f"  Direction: {direction_verdict}")
    print(f"  Note: {len(breakout_records)} total observations — limited statistical power")
    print()

    # ------------------------------------------------------------------
    # Test 5 — AIM-04 IVTS Spot Check
    # ------------------------------------------------------------------
    print("## Test 5 — AIM-04 IVTS Spot Check")
    print()
    print(f"  {'Date':<12} {'IVTS':>6} {'Expected Zone':<24} {'Exp Mod':>8} {'Act Mod':>8} {'Result'}")
    print(f"  {'-'*12} {'-'*6} {'-'*24} {'-'*8} {'-'*8} {'-'*6}")

    ivts_results = []
    for day in all_days:
        d = day["date"]
        # Get IVTS from features (same for all assets — VIX-derived)
        feats = day["features"].get("ES", {})
        ivts_val = feats.get("ivts")
        expected_mod, zone = ivts_expected_modifier(ivts_val)

        # Get actual AIM-04 modifier for ES
        es_breakdown = day["aim_breakdown"].get("ES", {})
        aim04 = es_breakdown.get(4, {})
        actual_mod = aim04.get("modifier", None)

        if actual_mod is None:
            result = "N/A"
        elif abs(actual_mod - expected_mod) < 0.011:
            result = "PASS"
        elif actual_mod < expected_mod:
            # AIM-04 has overlays (overnight gap ×0.85/×0.95, EIA ×0.90)
            # that reduce the base zone modifier. Check if the actual is
            # within the overlay range: base × 0.85 (worst case double overlay).
            min_with_overlays = expected_mod * 0.85 * 0.90  # extreme gap + EIA
            if actual_mod >= min_with_overlays - 0.01:
                result = "PASS (overlay)"
            else:
                result = "FAIL"
        else:
            result = "FAIL"

        ivts_results.append(result)
        ivts_str = f"{ivts_val:.4f}" if ivts_val is not None else "  N/A "
        act_str = f"{actual_mod:.4f}" if actual_mod is not None else "    N/A"
        print(f"  {d!s:<12} {ivts_str:>6} {zone:<24} {expected_mod:>7.2f}  {act_str:>7}  {result}")

    ivts_pass = sum(1 for r in ivts_results if "PASS" in r)
    ivts_fail = sum(1 for r in ivts_results if r == "FAIL")
    ivts_na = sum(1 for r in ivts_results if r == "N/A")
    print(f"\n  Summary: {ivts_pass} PASS, {ivts_fail} FAIL, {ivts_na} N/A")
    print()

    # ------------------------------------------------------------------
    # Verdict
    # ------------------------------------------------------------------
    print("## Verdict")
    print()

    aims_fire = n_nonneutral > 0
    aims_change_sizing = n_diff > 0
    direction_ok = "CORRECT" in direction_verdict
    ivts_ok = ivts_fail == 0
    bugs = list(aim_flags)
    ivts_hard_fail = sum(1 for r in ivts_results if r == "FAIL")
    if ivts_hard_fail > 0:
        bugs.append(f"AIM-04 IVTS zone mismatch on {ivts_hard_fail} day(s) (not explained by overlays)")
    if not aims_fire:
        bugs.append("No AIM modifiers != 1.0 — system completely neutral")
    if not aims_change_sizing:
        bugs.append("Zero sizing divergence — AIMs have no effect on contracts")

    if aims_fire and aims_change_sizing and direction_ok and not bugs:
        verdict = "PASS"
    elif aims_fire and not bugs:
        verdict = "PARTIAL"
    else:
        verdict = "FAIL" if bugs else "PARTIAL"

    print(f"  {verdict}")
    if bugs:
        print(f"  Bugs/Issues:")
        for b in bugs:
            print(f"    - {b}")
    print()

    # ===================================================================
    # Write report
    # ===================================================================
    report = _build_report(
        dates[0], dates[-1], len(all_days), len(skipped_dates),
        user_capital, risk_goal, max_positions,
        aim_stats, n_nonneutral, n_total, aim_flags,
        n_breakouts, n_diff, avg_abs_diff, breakout_records,
        total_on, total_off, delta, all_days,
        sa, sb, sn, direction_verdict,
        ivts_results, all_days,
        verdict, bugs,
    )

    report_path = "/tmp/AIM_AB_TEST_REPORT.md"
    with open(report_path, "w") as f:
        f.write(report)
    print(f"Report written to {report_path}")
    # Also print full report to stdout for capture
    print()
    print("=" * 80)
    print("FULL REPORT (Markdown):")
    print("=" * 80)
    print(report)


def _build_report(
    first_date, last_date, n_days, n_skipped,
    capital, risk_goal, max_pos,
    aim_stats, n_nonneutral, n_total, aim_flags,
    n_breakouts, n_diff, avg_abs_diff, breakout_records,
    total_on, total_off, delta, all_days,
    sa, sb, sn, direction_verdict,
    ivts_results, all_days_full,
    verdict, bugs,
):
    lines = []
    lines.append("# AIM A/B Validation Report\n")
    lines.append(f"**Period:** {first_date} to {last_date} ({n_days} trading days, {n_skipped} skipped)")
    lines.append(f"**Session:** NY")
    lines.append(f"**Config:** Capital=${capital:,.0f}, Risk Goal={risk_goal}, Max Positions={max_pos}")
    lines.append(f"**Generated:** {date.today()}")
    lines.append("")

    # Test 1
    lines.append("## Test 1 — AIM Activation Rate\n")
    lines.append(f"Combined modifier != 1.0: **{n_nonneutral}/{n_total}** ({100*n_nonneutral/n_total:.1f}%) asset-days\n")
    lines.append("| AIM | Name | Fired (%) | Neutral (%) | Avg Modifier | Flags |")
    lines.append("|-----|------|-----------|-------------|--------------|-------|")
    for aim_id in range(1, 17):
        s = aim_stats.get(aim_id, {"fired": 0, "neutral": 0, "mod_sum": 0, "mod_count": 0})
        total = s["fired"] + s["neutral"]
        if total == 0:
            continue
        fp = 100 * s["fired"] / total
        np_ = 100 * s["neutral"] / total
        am = s["mod_sum"] / s["mod_count"] if s["mod_count"] > 0 else 1.0
        flag = ""
        if aim_id in EXPECT_NEUTRAL and s["fired"] > 0:
            flag = "BUG"
        if aim_id in EXPECT_ACTIVE and s["fired"] == 0:
            flag = "WARN"
        lines.append(f"| {aim_id:02d} | {AIM_NAMES.get(aim_id, '?')} | {fp:.1f}% | {np_:.1f}% | {am:.4f} | {flag} |")
    lines.append("")

    # Test 2
    lines.append("## Test 2 — Sizing Divergence\n")
    lines.append(f"- Breakout asset-days: {n_breakouts}")
    pct = 100 * n_diff / n_breakouts if n_breakouts else 0
    lines.append(f"- With different sizing: **{n_diff}/{n_breakouts}** ({pct:.1f}%)")
    lines.append(f"- Average |contract difference|: {avg_abs_diff:.2f}")
    if n_diff > 0:
        lg = max(breakout_records, key=lambda r: abs(r["contracts_on"] - r["contracts_off"]))
        lines.append(f"- Largest divergence: {lg['asset']} {lg['date']} — ON={lg['contracts_on']} OFF={lg['contracts_off']}")
    lines.append("")

    # Test 3
    lines.append("## Test 3 — P&L Impact\n")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Total P&L (AIMs ON) | ${total_on:,.2f} |")
    lines.append(f"| Total P&L (AIMs OFF) | ${total_off:,.2f} |")
    lines.append(f"| Difference | ${delta:+,.2f} ({'helped' if delta > 0 else 'hurt'}) |")
    lines.append("")
    lines.append("| Date | P&L ON | P&L OFF | Delta |")
    lines.append("|------|--------|---------|-------|")
    for day in all_days:
        d = day["date"]
        p_on = day["result_on"].get("total_pnl", 0)
        p_off = day["result_off"].get("total_pnl", 0)
        lines.append(f"| {d} | ${p_on:,.2f} | ${p_off:,.2f} | ${p_on - p_off:+,.2f} |")
    lines.append("")

    # Test 4
    lines.append("## Test 4 — Directional Correctness\n")
    lines.append(f"| Group | N | Avg P&L/ct | Win Rate |")
    lines.append(f"|-------|---|------------|----------|")
    for s in [sa, sb, sn]:
        lines.append(f"| {s['label']} | {s['n']} | ${s['avg_pnl']:+,.2f} | {s['win_rate']:.1f}% |")
    lines.append(f"\n**Direction:** {direction_verdict}")
    lines.append("")

    # Test 5
    lines.append("## Test 5 — AIM-04 IVTS Spot Check\n")
    lines.append("| Date | IVTS | Zone | Expected | Actual | Result |")
    lines.append("|------|------|------|----------|--------|--------|")
    for i, day in enumerate(all_days_full):
        d = day["date"]
        feats = day["features"].get("ES", {})
        ivts_val = feats.get("ivts")
        expected_mod, zone = ivts_expected_modifier(ivts_val)
        es_bd = day["aim_breakdown"].get("ES", {})
        aim04 = es_bd.get(4, {})
        actual_mod = aim04.get("modifier")
        r = ivts_results[i] if i < len(ivts_results) else "?"
        iv_s = f"{ivts_val:.4f}" if ivts_val else "N/A"
        ac_s = f"{actual_mod:.4f}" if actual_mod else "N/A"
        lines.append(f"| {d} | {iv_s} | {zone} | {expected_mod:.2f} | {ac_s} | {r} |")

    ivts_pass = sum(1 for r in ivts_results if r == "PASS")
    ivts_fail = sum(1 for r in ivts_results if r == "FAIL")
    lines.append(f"\nSummary: {ivts_pass} PASS, {ivts_fail} FAIL")
    lines.append("")

    # Verdict
    lines.append("## Verdict\n")
    lines.append(f"**{verdict}**\n")
    if bugs:
        lines.append("## Bugs Found\n")
        for b in bugs:
            lines.append(f"- {b}")
    lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    main()
