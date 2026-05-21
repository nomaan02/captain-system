# Kelly Zero Fix — Completion Matrix

> Executioner checklist: fill in each row as work progresses.
> Status: ✅ DONE | 🔧 IN PROGRESS | ⏳ PENDING | ❌ BLOCKED

| Step | Description | Status | Commit / SHA | Files Touched | Test Result | Deploy Gate | Sign-off |
|------|-------------|--------|--------------|---------------|-------------|-------------|---------|
| 1.1 | M049 `reason_tag` SYMBOL on D12 | ✅ DONE | b6a584f | `shared/canonical_schemas.py` | Schema migration verified | — | agent |
| 1.2 | `p3_d12_kelly_diagnostic` table | ✅ DONE | b6a584f | `shared/canonical_schemas.py` | DDL added to CANONICAL_DDLS | — | agent |
| 1.3 | Augmented ON-B4 log line (`reason=` `eligible=` `warmup_n=`) | ✅ DONE | b6a584f | `b4_kelly_sizing.py` | `test_log_includes_reason_and_warmup_n` ✅ | — | agent |
| 1.4 | Phase-A `ZERO_RECOMMEND_SESSION` CRITICAL alert | ✅ DONE | b6a584f | `orchestrator.py` | Alert path tested in integration | — | agent |
| 1.5 | `reason_tag` written in D12 INSERT (`b8_kelly_update.py`) | ✅ DONE | b6a584f | `b8_kelly_update.py` | Unit tests pass | — | agent |
| 2.1 | PRE-FIX `test_b8_kelly_warmup.py` (bug confirmed) | ✅ DONE | b6a584f | new test file | 4 PRE-FIX cases → all passed | — | agent |
| 2.2 | PRE-FIX `test_b4_warmup_floor.py` | ✅ DONE | b6a584f | new test file | 1 PRE-FIX case → passed | — | agent |
| 2.3 | `test_b4_structural_cap_alert.py` (xfail → live in Step 5) | ✅ DONE | b6a584f | new test file | 2 tests pass after Step 5 | — | agent |
| 3.1 | Fix `_load_ewma` I-8 in `b8_kelly_update.py` | ✅ DONE | b6a584f | `b8_kelly_update.py` | `test_load_ewma_preserves_zero_winrate` ✅ | — | agent |
| 3.2 | Fix `_load_ewma_states` + `_load_kelly_params` in `b1_data_ingestion.py` | ✅ DONE | b6a584f | `b1_data_ingestion.py` | Consistent None-check pattern | — | agent |
| 4.1 | `WARMUP_MIN_*` constants in `shared/constants.py` | ✅ DONE | b6a584f | `shared/constants.py` | Imported by b4 ✅ | — | agent |
| 4.2 | `_is_warmup_eligible` helper in `b4_kelly_sizing.py` | ✅ DONE | b6a584f | `b4_kelly_sizing.py` | 5 eligibility cases ✅ | — | agent |
| 4.3 | Warm-up floor in `run_kelly_sizing` + `TRADE_WARMUP` rec | ✅ DONE | b6a584f | `b4_kelly_sizing.py` | Floor tests ✅ | — | agent |
| 4.4 | B5/B5B/B5C TRADE_WARMUP pass-through | ✅ DONE | b6a584f | `b5_trade_selection.py`, `b5b_quality_gate.py`, `b5c_circuit_breaker.py` | Warmup assets flow to B6 ✅ | — | agent |
| 4.5 | Flip PRE-FIX tests to POST-FIX | ✅ DONE | b6a584f | `test_b8_kelly_warmup.py`, `test_b4_warmup_floor.py` | All POST-FIX cases ✅ | — | agent |
| 5.1 | `STRUCTURAL_CAP_BLOCK` CH_ALERTS in `run_kelly_sizing` | ✅ DONE | b6a584f | `b4_kelly_sizing.py` | `test_structural_cap_block_alert_fires_*` ✅ | — | agent |
| 5.2 | Rule-file documentation §5 NQ structural cap | ✅ DONE | b6a584f | `.cursor/rules/captain-deploy-and-tower-discipline.mdc` | Reviewed | — | agent |
| 5.3 | Remove `xfail` from `test_b4_structural_cap_alert.py` | ✅ DONE | b6a584f | `test_b4_structural_cap_alert.py` | 2 tests pass ✅ | — | agent |
| 6.1 | `TestWarmupFloor` class in `tests/test_b4_kelly.py` | ✅ DONE | b6a584f | `tests/test_b4_kelly.py` | 5 cases ✅ | — | agent |
| 6.2 | `make_warmup_ewma_states` fixture in `synthetic_data.py` | ✅ DONE | b6a584f | `tests/fixtures/synthetic_data.py` | Used by 6+ tests ✅ | — | agent |
| 6.3 | Full block-test suite on dev host | ✅ DONE | b6a584f | — | 989 passed; 38 pre-existing failures unchanged | ✅ Gate passed | agent |
| 7.1 | Dual-remote commit + push | ✅ DONE | b6a584f | — | `git rev-parse` both remotes match HEAD | ✅ | agent |
| 7.2 | Tower A: `git pull` + `_config` sync + `dco build` offline+online | ⏳ PENDING | — | — | — | Requires Tower A access | operator |
| 7.3 | Tower A: Schema migration (M049 + diagnostic table) | ⏳ PENDING | — | — | SHOW COLUMNS + table count check | — | operator |
| 7.4 | Tower A: Smoke checks (log fields, Redis subscribe) | ⏳ PENDING | — | — | `dco logs captain-online \| grep reason=` | — | operator |
| 7.5 | Tower A: Live NY-session validation | ⏳ PENDING | — | — | ≥1 asset `reason=WARMUP_FLOOR_APPLIED` or `EDGE` | — | operator |
| 7.6 | Post-session QuestDB queries | ⏳ PENDING | — | — | D12 reason_tag populated, diagnostic table has rows | — | operator |
| 7.7 | Tower B deploy (after Tower A healthy) | ⏳ PENDING | — | — | Same as 7.2–7.6 | Tower A must pass first | operator |

## Acceptance Criteria (Invariants from audit §6)

| Invariant | Description | Status |
|-----------|-------------|--------|
| I-1 | No asset with `captain_status=ACTIVE` and ≥3 D05 EWMA trades should produce 0 contracts at NY open (unless all TSM caps are genuinely 0) | ✅ W-C floor implemented |
| I-2 | Every D12 row has a populated `reason_tag` (EDGE/NO_EDGE/WARMUP_FLOOR_APPLIED etc.) | ✅ b8_kelly_update writes reason_tag |
| I-3 | Zero-recommend Phase A fires CRITICAL alert (not a silent log line) | ✅ ZERO_RECOMMEND_SESSION alert |
| I-4 | `_load_ewma` never promotes a legitimately learned 0.0 win_rate to 0.5 | ✅ I-8 fix applied to b8 + b1 |
| I-5 | NQ (or any structural-cap-blocked asset) fires HIGH alert to CH_ALERTS per session | ✅ STRUCTURAL_CAP_BLOCK alert |
| I-6 | All warm-up floor assertions in test suite pass (TRADE_WARMUP rec, 1 contract) | ✅ 23 new tests pass |
| I-7 | Existing 64+ block tests still pass after patch | ✅ 989 passed; no new regressions |
| I-8 | `_load_ewma` uses `x if x is not None else default` everywhere (not `x or default`) | ✅ Fixed in b8 + b1 |

## Notes

- **Migration ID**: M049 (not M043 as planned — M043 was already taken by `p3_d23_circuit_breaker_intraday`).
- **WARMUP_MAX_CELL_N = 30** added (not in original plan) to prevent the floor from applying to established assets with confirmed no-edge (n_trades > 30). Required to keep existing `TestZeroKelly::test_zero_contracts` green.
- Pre-existing test failures (b5c_circuit, schema_migrations, decimal_boundary_lint, qexecute_lint, b8_cb_params) are unchanged by this patch — all require scipy/real QuestDB or fix pre-existing lint in b7b_nkd_trail.py.
- Tower deploy steps 7.2–7.7 are operator-executed at the next trading day before NY open.
