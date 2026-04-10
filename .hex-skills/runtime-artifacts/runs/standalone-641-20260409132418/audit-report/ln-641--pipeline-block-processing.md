<!-- AUDIT-META
skill: ln-641-pattern-analyzer
pattern: Pipeline/Block Processing
score: 7.2
score_compliance: 74
score_completeness: 68
score_quality: 70
score_implementation: 76
issues_critical: 0
issues_high: 1
issues_medium: 5
issues_low: 4
files_analyzed: 40
-->

# Pattern Analysis: Pipeline/Block Processing

**Audit Date:** 2026-04-09
**Score:** 7.2/10 (C:74 K:68 Q:70 I:76) | Issues: 10 (H:1 M:5 L:4)

## Files Analyzed

40 block files across 3 processes: captain-offline (15), captain-online (14), captain-command (11).

## Checks

| Check | Score | Evidence |
|---|---|---|
| compliance_check | 74/100 | Consistent `b{N}_{name}.py` naming; `run_` prefix in Online/Offline; Command blocks diverge (CRUD-style, utility functions); no base class/protocol |
| completeness_check | 68/100 | `snapshot_before_update` in only 4/15 offline blocks; `write_checkpoint` not imported by block files; `b1_aim16_hmm.py` is orphaned dead code |
| quality_check | 70/100 | Online B2-B6 strongly independent; most blocks compact; `run_kelly_sizing` 231 lines; `b3_pseudotrader` has 6 entry points and 3 responsibilities |
| implementation_check | 76/100 | All Online/Offline blocks wired to orchestrators; Command has split wiring model (orchestrator vs API); `b1_aim16_hmm.py` never called |

## Findings

| # | Severity | Category | File:Line | Issue | Suggestion | Effort |
|---|---|---|---|---|---|---|
| I-01 | HIGH | completeness | `captain-offline/.../b1_aim16_hmm.py:63` | `train_aim16_hmm()` never called — entire file is dead code (G-078) | Delete or wire into `_run_weekly()` scheduler | S/L |
| I-02 | MEDIUM | quality | `captain-online/.../b4_kelly_sizing.py:40` | `run_kelly_sizing` is 231 lines mixing Kelly, TSM constraints, silo checks, scaling | Extract 3-4 private helpers | M |
| I-03 | MEDIUM | quality | `captain-offline/.../b3_pseudotrader.py:169` | 6 public entry points, 3 responsibilities, 272-line main function | Split into b3_pseudotrader and b3_cb_pseudotrader | M |
| I-04 | MEDIUM | compliance | `captain-command/.../b2,b4,b6,b9` | Command blocks don't follow `run_` entry-point convention | Document split or harmonize with `run_*` dispatcher | S |
| I-05 | MEDIUM | completeness | `captain-offline/.../blocks/` | `snapshot_before_update` used in only 4 of 15 offline blocks that write QuestDB | Apply consistently before all strategy-critical DB writes | M |
| I-06 | MEDIUM | implementation | `captain-command/.../blocks/` | Zero dedicated unit tests for all 11 command blocks | Add tests for B1 routing and B8 reconciliation at minimum | M |
| I-07 | LOW | compliance | `b8_kelly_update.py:130` | Missing `-> None` return type annotation | Add annotation | S |
| I-08 | LOW | quality | `b1_data_ingestion.py:604+` | 7 deferred inline imports inconsistent with module-level style | Move to module level where safe | S |
| I-09 | LOW | compliance | N/A | No base class or Protocol defines block interface | Add `shared/block_protocol.py` with `BlockCallable` Protocol | S |
| I-10 | LOW | implementation | `captain-offline/.../blocks/` | Offline blocks don't import `write_checkpoint` — only orchestrator wraps them | Consider block-level checkpoints for multi-table writers | M |

<!-- DATA-EXTENDED
{
  "pattern": "Pipeline/Block Processing",
  "gaps": {
    "missingComponents": [
      "No BlockProtocol or ABC for interface enforcement",
      "Dead block: b1_aim16_hmm.py (168 lines, zero callers)",
      "14 of 15 offline blocks have no dedicated unit test"
    ],
    "inconsistencies": [
      "Command blocks use CRUD/utility naming vs Online/Offline run_ convention",
      "Split wiring: 4/11 Command blocks wired via API only, not orchestrator",
      "snapshot_before_update applied inconsistently across offline blocks"
    ]
  }
}
-->
