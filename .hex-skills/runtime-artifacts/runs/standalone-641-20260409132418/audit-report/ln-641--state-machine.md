<!-- AUDIT-META
skill: ln-641-pattern-analyzer
pattern: State Machine
score: 6.4
score_compliance: 72
score_completeness: 61
score_quality: 74
score_implementation: 58
issues_critical: 0
issues_high: 3
issues_medium: 4
issues_low: 3
files_analyzed: 8
-->

# Pattern Analysis: State Machine

**Audit Date:** 2026-04-09
**Score:** 6.4/10 (C:72 K:61 Q:74 I:58) | Issues: 10 (H:3 M:4 L:3)

## Files Analyzed

| File | Lines |
|---|---|
| `captain-command/captain_command/blocks/b4_tsm_manager.py` | 451 |
| `shared/account_lifecycle.py` | 640 |
| `config/tsm/providers/*.json` | 4 files |
| `tests/test_account_lifecycle.py` | 960 |

## Checks

| Check | Score | Evidence |
|---|---|---|
| compliance_check | 72/100 | `TopstepStage` enum with EVAL/XFA/LIVE; `_VALID_STAGES` allowlist; no explicit transition table; no guard in `_transition_to()`; stage vocabulary mismatch |
| completeness_check | 61/100 | All 3 states have constraint objects; LIVE failure path entirely absent; no state restore from D08; `payouts_remaining` reads static config |
| quality_check | 74/100 | Clean state/transition separation; `LifecycleEvent` audit trail; D08 `_update_topstep_state()` writes wrong table; no invalid-transition tests |
| implementation_check | 58/100 | `MultiStageTopstepAccount` used only in replay, not live path; no Redis alert on transition; D08 stage never updated after transition |

## Findings

| # | Severity | Category | File:Line | Issue | Suggestion | Effort |
|---|---|---|---|---|---|---|
| P0 | HIGH | completeness | `account_lifecycle.py:320-322` | LIVE failure path missing — spec says fee + revert to EVAL; LIVE never calls `handle_failure()` | Add balance-zero check in `end_of_day()` for LIVE stage | M |
| P1a | HIGH | implementation | `b8_reconciliation.py:501-514` | D08 `classification` column never updated after stage transition — shows stale stage | Add UPDATE path triggered by `_transition_to()` | M |
| P1b | HIGH | implementation | `b8_reconciliation.py:274` | `payouts_remaining` reads static `max_total_payouts` from config, not computed from `payouts_taken` | Compute `max - payouts_taken` from live state | S |
| P2a | MEDIUM | completeness | `account_lifecycle.py:575` | `get_state_snapshot()` exists but no `from_snapshot()` — process restart resets to EVAL/$150K | Implement `from_snapshot()` classmethod | M |
| P2b | MEDIUM | compliance | `account_lifecycle.py:362` | No guard condition in `_transition_to()` — any caller can skip stages | Add `assert self.current_stage == expected_from` | S |
| P2c | MEDIUM | implementation | `account_lifecycle.py:362` | No Redis alert published on stage transition | Publish to `captain:alerts` on EVAL->XFA and XFA->LIVE | S |
| P2d | MEDIUM | quality | `b8_reconciliation.py:501-514` | `_update_topstep_state()` writes to `p3_session_event_log` not `p3_d08_tsm_state` despite function name | Rename or fix write target | S |
| P3a | LOW | compliance | `main.py:93-101` | TSM config uses STAGE_1/STAGE_2/STAGE_3 while runtime uses EVAL/XFA/LIVE — vocabulary gap | Unify vocabulary or add explicit mapping | S |
| P3b | LOW | quality | `account_lifecycle.py:270-298` | Dual state on exact-limit LIVE trade: returns `allowed: True` but sets `halted_until_19est = True` | Clarify: reject trade or accept-and-halt consistently | S |
| P3c | LOW | completeness | `tests/test_account_lifecycle.py` | No tests for invalid transitions or corrupted TopstepStage values | Add negative-path tests | M |

<!-- DATA-EXTENDED
{
  "pattern": "State Machine",
  "gaps": {
    "missingComponents": [
      "LIVE failure path (spec-required, not implemented)",
      "State restore from D08 on restart",
      "Explicit transition table (ALLOWED_TRANSITIONS dict)",
      "D08 stage update on transition"
    ],
    "inconsistencies": [
      "Stage vocabulary: STAGE_1/2/3 in config vs EVAL/XFA/LIVE in runtime",
      "_update_topstep_state() writes wrong table",
      "MultiStageTopstepAccount used in replay only, not live trading path"
    ]
  }
}
-->
