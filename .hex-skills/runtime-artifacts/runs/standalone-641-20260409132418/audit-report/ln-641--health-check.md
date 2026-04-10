<!-- AUDIT-META
skill: ln-641-pattern-analyzer
pattern: Health Check / Heartbeat
score: 5.1
score_compliance: 68
score_completeness: 52
score_quality: 61
score_implementation: 65
issues_critical: 4
issues_high: 2
issues_medium: 3
issues_low: 1
files_analyzed: 10
-->

# Pattern Analysis: Health Check / Heartbeat

**Audit Date:** 2026-04-09
**Score:** 5.1/10 (C:68 K:52 Q:61 I:65) | Issues: 10 (Crit:4 H:2 M:3 L:1)

## Files Analyzed

| File | Purpose |
|---|---|
| `captain-command/.../api.py` | `/api/health`, `/api/status` endpoints |
| `captain-command/.../orchestrator.py` | `_publish_heartbeat` (30s interval) |
| `captain-online/.../orchestrator.py` | `_publish_pipeline_stage` |
| `captain-command/.../b1_core_routing.py` | `handle_status_message` |
| `captain-command/.../b3_api_adapter.py` | `run_health_checks` (brokerage ping) |
| `docker-compose.yml` | Container healthchecks |
| `captain-offline/Dockerfile` | Healthcheck definition |
| `captain-online/Dockerfile` | Healthcheck definition |
| `captain-command/Dockerfile` | Healthcheck definition |

## Checks

| Check | Score | Evidence |
|---|---|---|
| compliance_check | 68/100 | `/api/health` exists; auth-exempt; always returns HTTP 200 even when DEGRADED; no liveness/readiness separation |
| completeness_check | 52/100 | Command heartbeat OK; Offline never publishes heartbeat; Online pipeline_stage has no `status` field; no QuestDB/Redis probe in health endpoint; no stale heartbeat detection |
| quality_check | 61/100 | Health endpoint is read-only (correct); naive timestamps; `_process_health["COMMAND"]` pre-initialized as "ok" before ready; blocking health checks in sync loop |
| implementation_check | 65/100 | Docker HEALTHCHECK on all 3 containers; Offline/Online healthchecks probe QuestDB not themselves; no monitoring dashboard integration |

## Findings

| # | Severity | Category | File:Line | Issue | Suggestion | Effort |
|---|---|---|---|---|---|---|
| HC-01 | CRITICAL | compliance | `api.py:198` | `/api/health` returns HTTP 200 even when `status: "DEGRADED"` — Docker healthcheck always passes | Return `status_code=503` when degraded | S |
| HC-02 | CRITICAL | completeness | `captain-offline/.../orchestrator.py` | Offline process never publishes a heartbeat — always shows `unknown` in `/api/health` | Add `_publish_heartbeat` matching Command pattern | S |
| HC-03 | CRITICAL | completeness | `online/orchestrator.py:94-99` | Online `_publish_pipeline_stage` carries no `status` field — ONLINE always `unknown` | Add `"status": "ok"` to pipeline stage messages | S |
| HC-04 | CRITICAL | implementation | `captain-offline/Dockerfile:32`, `captain-online/Dockerfile:32` | Offline/Online Docker healthchecks probe QuestDB (`SELECT 1`) not the Python process — crashed process shows healthy | Add minimal HTTP health server to each process | M |
| HC-05 | HIGH | completeness | `b1_core_routing.py:339-356` | No stale heartbeat detection — dead process keeps last-known status indefinitely | Add timestamp staleness check (>2min = STALE) | S |
| HC-06 | HIGH | completeness | `api.py:162-209` | `/api/health` does not probe QuestDB or Redis — blind to infrastructure failures | Add `SELECT 1` and `PING` checks to health endpoint | S |
| HC-07 | MEDIUM | quality | `command/orchestrator.py:540,545` | Naive `datetime.now()` timestamps in heartbeat (no timezone) | Use `datetime.now(_ET)` matching Online pattern | S |
| HC-08 | MEDIUM | quality | `api.py:137` | `_process_health["COMMAND"]` pre-initialized as `"ok"` before process is actually ready | Initialize as `"starting"` and update to `"ok"` after orchestrator.start() | S |
| HC-09 | MEDIUM | implementation | N/A | No liveness/readiness probe separation | Split into `/api/livez` (cheap) and `/api/readyz` (probes deps) | M |
| HC-10 | LOW | implementation | N/A | No external monitoring integration (Prometheus/Grafana/Uptime Kuma) | Add `/api/metrics` endpoint or Prometheus exporter | L |

<!-- DATA-EXTENDED
{
  "pattern": "Health Check / Heartbeat",
  "gaps": {
    "missingComponents": [
      "Offline heartbeat (never published)",
      "Online status field in pipeline stage messages",
      "QuestDB/Redis probes in health endpoint",
      "Stale heartbeat detection",
      "Liveness/readiness separation",
      "Process-level Docker healthchecks for Offline/Online"
    ],
    "inconsistencies": [
      "Command publishes heartbeat; Offline doesn't; Online publishes pipeline stage instead",
      "Docker healthcheck probes QuestDB for Offline/Online but HTTP for Command",
      "Naive timestamps in Command heartbeat vs timezone-aware in Online"
    ]
  }
}
-->
