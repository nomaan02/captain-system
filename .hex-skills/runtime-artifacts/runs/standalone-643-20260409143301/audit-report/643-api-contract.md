<!-- AUDIT-META
skill: ln-643-api-contract-auditor
version: 2.0.0
run_id: standalone-643-20260409143301
domain_mode: global
scan_path: /home/nomaan/captain-system
produced_at: 2026-04-09T14:33:01Z
score: 5.9
score_compliance: 45
score_completeness: 30
score_quality: 80
score_implementation: 40
issues_total: 8
severity_counts: {critical: 0, high: 2, medium: 3, low: 3}
-->

# API Contract Audit Report

**Skill:** ln-643-api-contract-auditor v2.0.0
**Run ID:** standalone-643-20260409143301
**Scope:** Full codebase (global)
**Score:** 5.9/10 (C:45 K:30 Q:80 I:40) | Issues: 8 (H:2 M:3 L:3)

---

## Service Boundaries Discovered

| Layer | Location | Files |
|-------|----------|-------|
| API Boundary | `captain-command/captain_command/api.py` | 1 (FastAPI, 26 endpoints, JWT middleware) |
| Command Service | `captain-command/captain_command/blocks/` | 12 (b1-b11 + orchestrator + telegram_bot) |
| Online Service | `captain-online/captain_online/blocks/` | 13 (b1-b9 + orchestrator + or_tracker + shadow_monitor + features) |
| Offline Service | `captain-offline/captain_offline/blocks/` | 14 (b1-b9 + orchestrator + bootstrap + version_snapshot + injection + cusum) |
| Shared/Domain | `shared/` | 15 (topstep_client, questdb_client, redis_client, vault, statistics, etc.) |

---

## Checks Table

| # | Rule | Status | Details |
|---|------|--------|---------|
| R1 | Layer Leakage | PASS | No HTTP types (Request, headers, cookies) leak into service blocks. API extracts primitives before calling blocks. |
| R2 | Missing DTO | WARN | Replay functions share 5+ params across 4 call sites without grouping DTO. Two request DTOs use `dict[str, Any]` (no structural validation). |
| R3 | Entity Leakage | FAIL | 26/26 endpoints return raw dicts. Zero response DTOs. No `response_model=` usage. 8 endpoints pass service dicts through opaquely. |
| R4 | Error Contracts | FAIL | 3 incompatible patterns in api.py. b11_replay_runner has 3-way inconsistency. HTTPException never used. |
| R5 | Redundant Overloads | PASS | No `_with_`/`_and_` method pairs found. |
| R6 | Architectural Honesty | FAIL | `check_level_escalation()` performs DB writes, Redis publish, and global mutation behind `check_` prefix. |

---

## Findings Table

| ID | Rule | Severity | Location | Description | Suggestion | Effort |
|----|------|----------|----------|-------------|------------|--------|
| F-001 | R3 | HIGH | `api.py` (all endpoints) | 26/26 API endpoints return raw dicts via `JSONResponse()`. Zero response DTOs defined. OpenAPI spec shows no response schemas. Service-layer dict changes silently break API contract. | Define Pydantic response models for all endpoints. Use `response_model=` in route decorators. Start with the 8 opaque-passthrough endpoints (dashboard, system-overview, reports, replay). | HIGH (26 models) |
| F-002 | R6 | HIGH | `b2_level_escalation.py:179` | `check_level_escalation()` performs 4 categories of write side-effects: QuestDB INSERTs to D00/D04/D12/job_queue, Redis PUBLISH to `captain:alerts`, and module-global `_level2_active` mutation. Calling it twice doubles decay events and corrupts sizing overrides. | Rename to `evaluate_and_apply_escalation()` or split into pure `check_escalation_level() -> Decision` + `apply_escalation(decision)`. | LOW (rename) or MEDIUM (split) |
| F-003 | R4 | MEDIUM | `api.py` (10 endpoints) | 10 endpoints return HTTP 200 with `{"error": "..."}` body on failure. Clients cannot distinguish success from failure by status code. Affects: all `/api/replay/*` and `/api/notifications/telegram-history`. | Return proper HTTP 4xx/5xx status codes. Use `HTTPException` or `JSONResponse(status_code=500, ...)`. | LOW |
| F-004 | R4 | MEDIUM | `b11_replay_runner.py` | 3-way error inconsistency: `start_replay()` raises ValueError, `get_active_replay()` returns None, `control_replay()`/`save_replay()`/`run_whatif()` return `{"error": "..."}`. Callers need 3 different error-handling branches. | Standardize on one pattern (recommend: raise custom exceptions, catch in API layer). | MEDIUM |
| F-005 | R2 | MEDIUM | `b11_replay_runner.py:210,619` | `start_replay()` and `start_batch_replay()` share 5 params (user_id, config/overrides, sessions, speed, gui_push_fn) without a grouping DTO. Same params repeated in `ReplaySession.__init__` and `BatchReplaySession.__init__`. | Extract `ReplayConfig` dataclass grouping shared params. | LOW |
| F-006 | R4 | LOW | `b1_data_ingestion.py:567` | `_get_current_session_volume()` returns `0` on failure while sibling functions `_get_latest_price()` and `_get_avg_session_volume_20d()` return `None`. Callers cannot distinguish "volume is zero" from "lookup failed". | Return `None` consistently for data-unavailable, matching sibling convention. | LOW |
| F-007 | R2 | LOW | `api.py:498,641` | `AssetConfigRequest.asset_config` and `NotificationPrefsRequest.preferences` accept `dict[str, Any]` -- Pydantic DTO provides no structural validation. Also `ReplayControlRequest.action` and `TestNotificationRequest.priority` lack `Literal` constraints. | Define nested Pydantic models for asset config structure. Add `Literal["pause","resume","speed","skip_to_next","stop"]` for action field. | LOW |
| F-008 | R4 | LOW | `b4_tsm_manager.py:197-209` | `load_tsm_for_account()` collapses 3 distinct failure modes (file not found, JSON parse error, validation failure) into single `return None`. Callers cannot distinguish why loading failed. | Return a result tuple `(tsm, error_reason)` or raise typed exceptions. | LOW |

---

## Scoring Justification

### Primary Score: 5.9/10

```
penalty = (0 x 2.0) + (2 x 1.0) + (3 x 0.5) + (3 x 0.2) = 0 + 2.0 + 1.5 + 0.6 = 4.1
score = max(0, 10 - 4.1) = 5.9
```

### Diagnostic Sub-scores

**Compliance: 45/100**
| Criterion | Points | Notes |
|-----------|--------|-------|
| No layer leakage | +35 | Clean -- all endpoints extract primitives |
| Consistent error handling | +0 | 3 incompatible patterns in API layer |
| Project naming conventions | +10 | Generally consistent |
| No hidden side-effects | +0 | `check_level_escalation()` violates |
| No entity leakage | +0 | 26/26 endpoints return raw dicts |

**Completeness: 30/100**
| Criterion | Points | Notes |
|-----------|--------|-------|
| Typed params on service methods | +15 | Partial -- many use `dict` |
| Typed returns on service methods | +10 | Partial -- most return `dict` not typed models |
| DTOs for complex data | +5 | 12 request DTOs, 0 response DTOs |
| Error types documented | +0 | No custom exception hierarchy |

**Quality: 80/100**
| Criterion | Points | Notes |
|-----------|--------|-------|
| No boolean flag params | +15 | Clean |
| No opaque write-hiding returns | +5 | 1 violation (check_level_escalation) |
| No >5 params without DTO | +15 | Replay functions exceed threshold |
| Consistent naming | +20 | Good across modules |
| No redundant overloads | +25 | Clean |

**Implementation: 40/100**
| Criterion | Points | Notes |
|-----------|--------|-------|
| DTOs/schemas used | +15 | Request-side only |
| Type annotations present | +15 | Partial coverage |
| Validation at boundaries | +10 | Pydantic for requests but weak constraints |
| Response DTOs separate from domain | +0 | None exist |

---

## Additional Observations

### Positive Patterns
- **Layer separation is clean (R1):** The API boundary correctly extracts all values before calling service blocks. No HTTP artifacts leak into the service layer.
- **No redundant overloads (R5):** No `_with_`/`_and_` method pairs found across any blocks.
- **GET endpoints are read-only:** All GET endpoints perform pure reads. Write operations are correctly isolated to POST endpoints.
- **Circuit breaker has excellent error contract:** `b5c_circuit_breaker.py` uses a consistent `str | None` pattern across all 7 layers -- one of the best-designed modules in the codebase.

### Error Contract Landscape (Cross-Module)

| Module | raise | return None | return {"error"} | log-and-continue | Consistent? |
|--------|-------|-------------|-------------------|------------------|-------------|
| b3_api_adapter | none | 1 | 4+ | -- | Mild mix |
| b4_tsm_manager | none | 3 | 0 | -- | Yes |
| b5c_circuit_breaker | none | 18 (str\|None) | 0 | -- | Yes (excellent) |
| b8_reconciliation | none | 0 | 0 | all | Yes (silent) |
| b11_replay_runner | ValueError (5x) | 2 | 9 | -- | **No (3-way)** |
| b1_data_ingestion | RuntimeError (1x) | 8+ | 0 | -- | Defensible |

### Internal API Parity Note
This is an internal-only API (GUI + Telegram consumers, no external third parties). Entity leakage severity is downgraded from CRITICAL to HIGH per the skill's guidance: "internal API with no external consumers -> downgrade."

---

## Priority Remediation Path

1. **Quick wins (1-2 hours):** F-003 (add HTTP status codes to 10 endpoints), F-006 (fix return 0 -> None)
2. **Medium effort (1 day):** F-002 (rename or split check_level_escalation), F-004 (standardize replay error contract)
3. **Larger effort (2-3 days):** F-001 (define response DTOs for all 26 endpoints)
