<!-- AUDIT-META
skill: ln-641-pattern-analyzer
pattern: Repository/Data Access
score: 6.4
score_compliance: 72
score_completeness: 58
score_quality: 65
score_implementation: 70
issues_critical: 0
issues_high: 2
issues_medium: 3
issues_low: 2
files_analyzed: 8
-->

# Pattern Analysis: Repository/Data Access

**Audit Date:** 2026-04-09
**Score:** 6.4/10 (C:72 K:58 Q:65 I:70) | Issues: 7 (H:2 M:3 L:2)

## Files Analyzed

| File | Purpose |
|---|---|
| `shared/questdb_client.py` | QuestDB connection helper |
| `shared/redis_client.py` | Redis singleton + pub/sub |
| `shared/journal.py` | SQLite WAL journal |
| `shared/bar_cache.py` | SQLite bar cache |
| `scripts/init_questdb.py` | Schema definitions |
| `scripts/verify_questdb.py` | Verification script |
| 88 call sites across all 3 processes | |

## Checks

| Check | Score | Evidence |
|---|---|---|
| compliance_check | 72/100 | All 88 QuestDB call sites use `%s` parameterization; zero SQL injection risk; wrong `$N` placeholder in b7_notifications.py (runtime bug) |
| completeness_check | 58/100 | No connection pooling (40+ connect/disconnect per pipeline run); no retry/timeout on QuestDB; no bulk INSERT; journal recovery ornamental |
| quality_check | 65/100 | `get_cursor()` centralized and DRY across all processes; cursor not closed explicitly; journal conn leaks on exception; N+1 per-asset cursors |
| implementation_check | 70/100 | All 3 processes use shared module exclusively; health check present; no upper bound on concurrent FastAPI connections |

## Findings

| # | Severity | Category | File:Line | Issue | Suggestion | Effort |
|---|---|---|---|---|---|---|
| DA-01 | HIGH | compliance | `b7_notifications.py:433` | `$1`-style placeholder wrong for psycopg2 — runtime failure for non-TRADER role | Change to `%s` pyformat parameterization | S |
| DA-02 | HIGH | completeness | `shared/questdb_client.py:21-29` | No connection pooling — 40+ connect/disconnect per pipeline run, 130+ on daily close | Add `psycopg2.pool.ThreadedConnectionPool` | M |
| DA-03 | MEDIUM | completeness | `shared/questdb_client.py:21-29` | No `connect_timeout` or retry — QuestDB blip crashes block immediately | Add timeout and exponential backoff (match Redis pattern) | S |
| DA-04 | MEDIUM | quality | `shared/journal.py:63-80` | Connection leak on exception in `write_checkpoint` / `get_last_checkpoint` | Add `try/finally` with `conn.close()` | S |
| DA-05 | MEDIUM | quality | `captain-offline/.../orchestrator.py:575-586` | N+1 cursor-per-asset in daily AIM loop (10 connections where 1 suffices) | Batch-fetch all assets in single query | S |
| DA-06 | LOW | quality | `shared/journal.py:19`, `shared/bar_cache.py:29` | `_initialized` boolean not thread-safe (unlike Redis which has `_client_lock`) | Add threading lock or use `threading.Event` | S |
| DA-07 | LOW | compliance | `scripts/verify_questdb.py:154` | f-string table name interpolation (admin script, low risk) | Use parameterized query | S |

<!-- DATA-EXTENDED
{
  "pattern": "Repository/Data Access",
  "gaps": {
    "missingComponents": [
      "Connection pooling for QuestDB",
      "Connection timeout and retry logic",
      "Bulk INSERT (executemany/execute_values)",
      "Actionable crash recovery from journal"
    ],
    "inconsistencies": [
      "Redis has full retry/timeout/health-check; QuestDB has none",
      "$N vs %s placeholder styles (b7_notifications.py)",
      "journal.py and bar_cache.py _initialized not thread-safe unlike redis_client.py"
    ]
  }
}
-->
