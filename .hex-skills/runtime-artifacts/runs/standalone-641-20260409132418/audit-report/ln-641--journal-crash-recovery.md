<!-- AUDIT-META
skill: ln-641-pattern-analyzer
pattern: Journal/Crash Recovery
score: 6.3
score_compliance: 72
score_completeness: 60
score_quality: 70
score_implementation: 65
issues_critical: 1
issues_high: 0
issues_medium: 4
issues_low: 3
files_analyzed: 9
-->

# Pattern Analysis: Journal/Crash Recovery

**Audit Date:** 2026-04-09
**Score:** 6.3/10 (C:72 K:60 Q:70 I:65) | Issues: 8 (Crit:1 M:4 L:3)

## Files Analyzed

| File | Purpose |
|---|---|
| `shared/journal.py` | SQLite WAL journal (write_checkpoint / get_last_checkpoint) |
| `scripts/init_sqlite.py` | Journal schema init |
| `captain-offline/.../orchestrator.py` | 15+ checkpoint writes |
| `captain-online/.../orchestrator.py` | 10+ checkpoint writes |
| `captain-command/.../orchestrator.py` | 8+ checkpoint writes |
| All 3 `main.py` files | Startup recovery read |
| `docker-compose.yml` | Volume mounts |
| `tests/test_stress.py` | 2 journal tests |

## Checks

| Check | Score | Evidence |
|---|---|---|
| compliance_check | 72/100 | WAL mode enabled; atomic commits; per-process isolation via Docker volumes; missing `busy_timeout`; `_initialized` not thread-safe |
| completeness_check | 60/100 | All 3 processes write checkpoints throughout lifecycle; **CRITICAL: `next_action` logged but never acted upon — recovery is log-only** |
| quality_check | 70/100 | Clean 2-function abstraction; auto-init on first access; connection-per-write; timestamp ordering fragile; no journal rotation |
| implementation_check | 65/100 | Docker volume mounts correct; 40+ write sites; dead imports in b1_core_routing and b3_api_adapter; tests cover storage only |

## Findings

| # | Severity | Category | File:Line | Issue | Suggestion | Effort |
|---|---|---|---|---|---|---|
| J-01 | CRITICAL | completeness | All 3 `main.py` | `next_action` field is logged but never acted upon — all processes take identical startup paths regardless of checkpoint state. The "R" in WAL recovery has no consumer. | Implement conditional startup logic that branches on `next_action` to skip completed steps | L |
| J-02 | MEDIUM | compliance | `shared/journal.py` | No `PRAGMA busy_timeout` — concurrent writes from same process get immediate `SQLITE_BUSY` | Add `conn.execute("PRAGMA busy_timeout=5000;")` after WAL pragma | S |
| J-03 | MEDIUM | completeness | `b1_core_routing.py:36`, `b3_api_adapter.py:30` | `write_checkpoint` imported but never called — highest-risk operations (signal routing, order placement) produce no journal entries | Add checkpoint calls around signal routing and order submission | M |
| J-04 | MEDIUM | quality | `shared/journal.py:88` | `ORDER BY timestamp` on TEXT column — ISO format sorts correctly only with uniform precision and timezone | Order by ROWID or add auto-increment column | S |
| J-05 | MEDIUM | quality | `shared/journal.py:63-80` | New connection opened and closed on every call — connection-per-write adds latency during high-frequency processing | Cache connection per-thread or use connection pool | M |
| J-06 | LOW | compliance | `shared/journal.py:19` | `_initialized` global not protected by threading lock | Add `threading.Lock` guard | S |
| J-07 | LOW | quality | N/A | No purge/rotate function — journal grows unbounded on long-running system | Add `purge_before(timestamp)` function; call from daily reconciliation | S |
| J-08 | LOW | implementation | `.env.template` | `CAPTAIN_JOURNAL_PATH` not documented in template | Add to template with default value comment | S |

<!-- DATA-EXTENDED
{
  "pattern": "Journal/Crash Recovery",
  "gaps": {
    "missingComponents": [
      "Recovery logic that branches on next_action (the core purpose of the pattern)",
      "Journal rotation/purge",
      "Thread-safe initialization",
      "Checkpoint calls in signal routing and order placement blocks"
    ],
    "inconsistencies": [
      "Dead write_checkpoint imports in b1_core_routing and b3_api_adapter",
      "Connection-per-write pattern vs Redis singleton pattern",
      "CAPTAIN_JOURNAL_PATH not in .env.template but used in journal.py"
    ]
  }
}
-->
