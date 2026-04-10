<!-- AUDIT-META
skill: ln-641-pattern-analyzer
pattern: Orchestrator
score: 7.1
score_compliance: 74
score_completeness: 72
score_quality: 68
score_implementation: 80
issues_critical: 0
issues_high: 2
issues_medium: 6
issues_low: 3
files_analyzed: 3
-->

# Pattern Analysis: Orchestrator

**Audit Date:** 2026-04-09
**Score:** 7.1/10 (C:74 K:72 Q:68 I:80) | Issues: 11 (H:2 M:6 L:3)

## Files Analyzed

| File | Lines | Process |
|---|---|---|
| `captain-offline/captain_offline/blocks/orchestrator.py` | 708 | OfflineOrchestrator |
| `captain-online/captain_online/blocks/orchestrator.py` | 783 | OnlineOrchestrator |
| `captain-command/captain_command/blocks/orchestrator.py` | 571 | CommandOrchestrator |

## Checks

| Check | Score | Evidence |
|---|---|---|
| compliance_check | 74/100 | Consistent naming; spec references in docstrings; AlgorithmImports artifact in all 3; naive datetime in command; stop() inconsistency |
| completeness_check | 72/100 | Startup/shutdown/recovery present; exponential backoff on Redis; no orchestrator unit tests; online stop() missing checkpoint+join |
| quality_check | 68/100 | Methods well-bounded; SRP upheld at class level; `_run_session` 136-line god method; single-except masking in outcome handlers; TOCTOU on position list |
| implementation_check | 80/100 | Redis Stream consumer groups correct; fine-grained scheduler; health monitoring chain; uvicorn SIGTERM override; TSM query every 1s |

## Findings

| # | Severity | Category | File:Line | Issue | Suggestion | Effort |
|---|---|---|---|---|---|---|
| I-01 | HIGH | implementation | `command/main.py:363-371` | `uvicorn.run()` overrides custom SIGTERM handler — `orchestrator.stop()` never called on container shutdown | Use `uvicorn.Config` + `Server` manually with `server.handle_exit` hook | M |
| I-02 | HIGH | quality | `offline/orchestrator.py:136-176` | Single `except Exception` wraps all 7 steps in `_handle_trade_outcome` — one failure silently aborts remaining learning updates | Wrap each step individually or use step-runner that collects partial failures | M |
| I-03 | MEDIUM | completeness | `online/orchestrator.py:86-88` | `stop()` missing `write_checkpoint` and thread join | Add shutdown checkpoint and join command listener thread | S |
| I-04 | MEDIUM | completeness | `command/orchestrator.py:138-143` | `stop()` does not join `_signal_thread` or `_redis_thread` | Store threads as instance attributes and join with 5s timeout | S |
| I-05 | MEDIUM | compliance | `command/orchestrator.py:104,242,315,540,545` | Five `datetime.now()` calls without timezone violate system-wide `America/New_York` rule | Replace with `datetime.now(ZoneInfo(SYSTEM_TIMEZONE))` | S |
| I-06 | MEDIUM | quality | `online/orchestrator.py:146-281` | `_run_session` is 136 lines with ~12 branch points — god method | Extract `_run_session_phase_a` and `_run_session_phase_b` | M |
| I-07 | MEDIUM | quality | `online/orchestrator.py:120,127` | TOCTOU: `self.open_positions` checked outside lock | Move check inside `_run_position_monitor` under the lock | S |
| I-08 | MEDIUM | implementation | `online/orchestrator.py:599-600` | `_load_tsm_configs()` QuestDB query fires every 1s tick while positions open | Cache with 30s TTL, invalidated on TSM_CHANGE command | S |
| I-09 | LOW | compliance | All three files:1-5 | `try: from AlgorithmImports import *` is a QuantConnect artifact | Remove the block from all three files | S |
| I-10 | LOW | completeness | N/A | Zero unit tests for orchestrator lifecycle | Add dedicated test files for each orchestrator | L |
| I-11 | LOW | quality | `command/orchestrator.py:505-516` | `_tg_send` closure redefined on every loop iteration | Define once outside the loop | S |

<!-- DATA-EXTENDED
{
  "pattern": "Orchestrator",
  "codeReferences": [
    "captain-offline/captain_offline/blocks/orchestrator.py",
    "captain-online/captain_online/blocks/orchestrator.py",
    "captain-command/captain_command/blocks/orchestrator.py"
  ],
  "gaps": {
    "missingComponents": [
      "No orchestrator unit tests (test_orchestrator_*.py)",
      "Online stop() has no shutdown checkpoint",
      "Command stop() has no thread join"
    ],
    "inconsistencies": [
      "Shutdown asymmetry: Offline joins threads, Online/Command do not",
      "Checkpoint asymmetry: Offline writes SHUTDOWN, Command writes ORCHESTRATOR_STOP, Online writes nothing",
      "uvicorn SIGTERM override in Command means clean shutdown may not execute"
    ]
  },
  "recommendations": [
    "Standardize stop() across all 3 orchestrators: checkpoint + thread join + resource cleanup",
    "Fix uvicorn SIGTERM override via manual Server API",
    "Add per-step error handling in _handle_trade_outcome to prevent silent partial execution"
  ]
}
-->
