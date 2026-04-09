<!-- AUDIT-META
worker: ln-643-api-contract-auditor
pattern: API Contracts
scope: global
score: 6.6
score_compliance: 58
score_completeness: 45
score_quality: 80
score_implementation: 45
issues_total: 7
severity_critical: 0
severity_high: 1
severity_medium: 4
severity_low: 2
produced_at: 2026-04-09T11:19:10Z
-->

# API Contract Audit — Captain System

**Score: 6.6 / 10** (C:58 K:45 Q:80 I:45) | Issues: 7 (H:1 M:4 L:2)

---

## Scope

Full codebase audit of all API boundaries in the Captain System monorepo:

| Layer | Location | Files |
|-------|----------|-------|
| API (HTTP) | `captain-command/captain_command/api.py` | 1 (943 lines) |
| Service (Blocks) | `captain-command/captain_command/blocks/` | 11 block files |
| Shared | `shared/` | 14 modules |
| Inter-service | Redis pub/sub + streams | 5 channels, 3 streams |

**Endpoints audited:** 28 REST + 1 WebSocket across 8 functional groups.

---

## Checks

| # | Rule | Result | Severity | Notes |
|---|------|--------|----------|-------|
| 1 | Layer Leakage in Signatures | **PASS** | - | Blocks do not import/accept HTTP types (Request, Response, Header, etc.) |
| 1b | Layer Leakage — DB in API | **FAIL** | HIGH | 4 endpoints bypass service layer, query QuestDB directly |
| 2 | Missing DTO for Grouped Params | **FAIL** | MEDIUM | `start_replay` (6 params), `start_batch_replay` (7 params) |
| 2b | Untyped dict Params | **FAIL** | LOW | 5 request models use opaque `dict` fields |
| 3 | Entity Leakage to API | **FAIL** | MEDIUM | All GET endpoints return untyped `JSONResponse(dict)`, no response schemas |
| 4 | Inconsistent Error Contracts | **FAIL** | MEDIUM | POST errors return HTTP 200 + `{"error": "..."}`, service mixes raise/return-None/return-{} |
| 5 | Redundant Method Overloads | **PASS** | - | No `_with_`/`_and_` suffix overloads found |
| 6 | Architectural Honesty | **PASS** | - | All read-named functions (`get_*`, `check_*`, `validate_*`) are pure reads |

---

## Findings

### F-001: Direct Database Access in API Layer [HIGH]

**Rule:** Layer Leakage (boundary violation)
**Location:** `captain-command/captain_command/api.py`

Four API endpoints bypass the service layer (blocks) and directly import `get_cursor()` to query/write QuestDB:

| Endpoint | Line | Operation | Should Belong To |
|----------|------|-----------|------------------|
| `api_telegram_history` | ~686 | SELECT from `p3_d10_notification_log` | B7 (notifications) |
| `api_replay_history` | ~840 | SELECT from `p3_replay_results` | B11 (replay_runner) |
| `api_replay_presets` | ~872 | SELECT from `p3_replay_presets` | B11 (replay_runner) |
| `api_replay_preset_save` | ~905 | INSERT into `p3_replay_presets` | B11 (replay_runner) |

**Impact:** API layer becomes coupled to database schema. Schema changes require editing both api.py and block files. The write operation in `api_replay_preset_save` is especially problematic — the API layer should never directly insert rows.

**Suggestion:** Extract each query into the owning block module and call from api.py. Effort: ~2h.

---

### F-002: No Response DTOs on GET Endpoints [MEDIUM]

**Rule:** Entity Leakage to API
**Location:** `captain-command/captain_command/api.py` — all GET endpoints

All 12 GET endpoints return `JSONResponse(dict)` or `JSONResponse(_make_json_safe(dict))` without Pydantic response model validation. The dicts are assembled by service functions that return `-> dict` with no typed contract.

**Affected endpoints:**
- `/api/health`, `/api/status`, `/api/accounts`
- `/api/dashboard/{user_id}`, `/api/system-overview`, `/api/processes/status`
- `/api/aim/{aim_id}/detail`
- `/api/reports/types`
- `/api/notifications/preferences/{user_id}`, `/api/notifications/telegram-history`
- `/api/replay/status`, `/api/replay/history`, `/api/replay/presets`

**Impact:** No schema enforcement — the GUI client has no contract guarantee. Silent field additions/removals break the frontend without compile-time or runtime errors.

**Mitigating factor:** Internal API with single consumer (captain-gui). Downgraded from HIGH to MEDIUM per audit rules.

**Suggestion:** Define Pydantic response models for at least the 5 most-used endpoints (health, dashboard, status, aim detail, replay status). Effort: ~4h.

---

### F-003: Missing DTO for Replay Functions [MEDIUM]

**Rule:** Missing DTO for Grouped Parameters
**Location:** `captain-command/captain_command/blocks/b11_replay_runner.py`

Two functions exceed the 5-parameter threshold without a grouping DTO:

```python
# 6 parameters
def start_replay(user_id, date_str, sessions, config_overrides, speed, gui_push_fn): ...

# 7 parameters
def start_batch_replay(user_id, date_from, date_to, sessions, config_overrides, speed, gui_push_fn): ...
```

**Suggestion:** Create a `ReplayConfig` dataclass grouping `sessions`, `config_overrides`, `speed`. Effort: ~1h.

---

### F-004: Inconsistent Error Contracts [MEDIUM]

**Rule:** Inconsistent Error Contracts
**Location:** `captain-command/captain_command/api.py` + blocks

**Problem 1 — HTTP status codes:** POST endpoint error responses return HTTP 200 with `{"error": "Internal server error"}` body. Standard practice is 4xx/5xx:

```python
# Current (api.py ~769)
except Exception as exc:
    return JSONResponse({"error": "Internal server error"})  # HTTP 200!

# Expected
except Exception as exc:
    return JSONResponse({"error": "Internal server error"}, status_code=500)
```

Affected: 9 POST endpoints (all replay, reports, notifications).

**Problem 2 — Service layer inconsistency:**

| Pattern | Example | Location |
|---------|---------|----------|
| `raise ValueError` | `start_batch_replay` date validation | b11_replay_runner.py:224,631,634,645,648 |
| `return None` | `get_active_replay()`, `get_adapter()` | b11:290, b3:365 |
| `return {}` | `build_system_overview()` on error | b2:796,856 |
| Silently pass | `_get_user_preferences()` | b7:376 |

**Suggestion:** Standardize: service functions raise typed exceptions, API layer maps to HTTP status codes. Effort: ~3h.

---

### F-005: Path Parameter Authorization Gap [MEDIUM]

**Rule:** Layer Leakage (boundary enforcement)
**Location:** `captain-command/captain_command/api.py`

Two endpoints accept `{user_id}` path parameters without verifying the authenticated user matches:

```python
@app.get("/api/dashboard/{user_id}")
def api_dashboard(user_id: str):   # No check: user_id == request.state.user_id
    return JSONResponse(_make_json_safe(build_dashboard_snapshot(user_id)))

@app.get("/api/notifications/preferences/{user_id}")
def api_get_notification_prefs(user_id: str):  # Same gap
```

**Impact:** Any authenticated user can request another user's dashboard or notification preferences. Currently mitigated by single-user deployment, but violates multi-user-from-day-one principle (CLAUDE.md Rule 5).

**Suggestion:** Add `if user_id != request.state.user_id: raise HTTPException(403)`. Effort: ~30m.

---

### F-006: Untyped dict Parameters in Request Models [LOW]

**Rule:** Missing DTO for Grouped Parameters
**Location:** `captain-command/captain_command/api.py`

Five Pydantic request models use opaque `dict` fields, bypassing schema validation:

| Model | Field | Used By |
|-------|-------|---------|
| `ValidateInputRequest` | `context: dict[str, Any] = {}` | `/api/validate/input` |
| `AssetConfigRequest` | `asset_config: dict[str, Any]` | `/api/validate/asset-config` |
| `ReportRequest` | `params: dict[str, Any] = {}` | `/api/reports/generate` |
| `NotificationPrefsRequest` | `preferences: dict[str, Any]` | `/api/notifications/preferences` |
| `ReplayStartRequest` | `config_overrides: dict = {}` | `/api/replay/start`, `/api/replay/whatif` |

**Impact:** Clients can send arbitrary keys/types. Schema changes propagate silently.

**Suggestion:** Replace with explicit Pydantic models where field set is known (especially `config_overrides` and `preferences`). Effort: ~2h.

---

### F-007: Inconsistent Success Response Shapes [LOW]

**Rule:** Inconsistent Error Contracts
**Location:** `captain-command/captain_command/api.py`

Success responses use 5 different envelope shapes:

| Shape | Example Endpoint |
|-------|-----------------|
| `{"status": "ok", ...}` | `api_save_notification_prefs` |
| `{"ok": true, ...}` | `api_aim_activate` |
| `{"replay_id": "..."}` | `api_replay_start` |
| `{"replays": [...]}` | `api_replay_history` |
| `{"items": [...], "count": N}` | `api_telegram_history` |

**Impact:** Client must handle each endpoint's shape individually. No standard envelope for success/error discrimination.

**Suggestion:** Adopt consistent envelope: `{"ok": true, "data": {...}}` / `{"ok": false, "error": "..."}`. Effort: ~3h.

---

## Score Justification

### Primary Score: 6.6 / 10

```
penalty = (critical × 2.0) + (high × 1.0) + (medium × 0.5) + (low × 0.2)
        = (0 × 2.0) + (1 × 1.0) + (4 × 0.5) + (2 × 0.2)
        = 0 + 1.0 + 2.0 + 0.4
        = 3.4

score = max(0, 10 - 3.4) = 6.6
```

### Diagnostic Sub-Scores

**Compliance: 58 / 100**

| Criterion | Points | Awarded | Rationale |
|-----------|--------|---------|-----------|
| No layer leakage (HTTP types in service) | 35 | 35 | Blocks are clean — no HTTP imports |
| Consistent error handling pattern | 25 | 0 | Mixed raise/return-None/return-{}/silent-pass |
| Follows project naming conventions | 10 | 8 | Good overall, minor inconsistencies |
| No hidden side-effects in read-named functions | 10 | 10 | All `get_*`/`check_*` are pure reads |
| No entity leakage to API | 20 | 5 | All responses are untyped dicts |

**Completeness: 45 / 100**

| Criterion | Points | Awarded | Rationale |
|-----------|--------|---------|-----------|
| All service methods have typed params | 30 | 20 | Most typed, some use `Any`/`dict` |
| All service methods have typed returns | 30 | 10 | All return `dict` — not specific types |
| DTOs defined for complex data | 20 | 10 | Request DTOs exist, no response DTOs |
| Error types documented/typed | 20 | 5 | No typed error hierarchy |

**Quality: 80 / 100**

| Criterion | Points | Awarded | Rationale |
|-----------|--------|---------|-----------|
| No boolean flag params in service methods | 15 | 15 | Clean |
| No opaque return types hiding write actions | 10 | 10 | Clean |
| No methods with >5 params without DTO | 25 | 10 | Replay functions exceed threshold |
| Consistent naming across module | 25 | 20 | Good, minor prefix inconsistencies |
| No redundant overloads | 25 | 25 | None found |

**Implementation: 45 / 100**

| Criterion | Points | Awarded | Rationale |
|-----------|--------|---------|-----------|
| DTOs/schemas exist and are used | 30 | 15 | Request-only (12 Pydantic models) |
| Type annotations present | 25 | 15 | Partial — `-> dict` not specific |
| Validation at boundaries (Pydantic) | 25 | 15 | Request bodies only, no response validation |
| API response DTOs separate from domain | 20 | 0 | No response DTOs exist |

---

## Positive Observations

1. **Clean layer separation for HTTP types.** Service blocks (B1-B11) do not import or reference any FastAPI/HTTP types. The API layer correctly translates HTTP concerns to plain Python arguments.

2. **Strong outbound sanitization.** B3 API Adapter enforces a strict 6-field whitelist via `sanitise_for_api()`, preventing internal signal fields (AIM weights, Kelly params, regime data) from reaching the brokerage API.

3. **Architectural honesty.** All read-prefixed functions (`get_*`, `check_*`, `validate_*`, `find_*`) across the entire codebase are free of write side-effects. No violations of the naming contract.

4. **No redundant overloads.** The codebase avoids the `_with_`/`_and_` anti-pattern entirely.

5. **JWT authentication middleware.** Proper separation — auth is handled in middleware, not leaked into service functions.

---

## Remediation Priority

| Priority | Finding | Effort | Impact |
|----------|---------|--------|--------|
| 1 | F-001: Move DB queries out of api.py | ~2h | Restores clean layer boundary |
| 2 | F-004: Fix HTTP 200 error responses | ~1h | Correct HTTP semantics |
| 3 | F-005: Add path param authorization | ~30m | Multi-user security |
| 4 | F-002: Add response DTOs (top 5) | ~4h | Client schema guarantees |
| 5 | F-003: Replay config DTO | ~1h | Cleaner service interface |
| 6 | F-006: Type dict params | ~2h | Input validation coverage |
| 7 | F-007: Standardize response envelope | ~3h | Client consistency |

**Total estimated effort: ~13.5h**

---

<!-- DATA-EXTENDED
[
  {"id":"F-001","rule":"layer_leakage","severity":"HIGH","location":"api.py:686-928","principle":"Layer Boundary","domain":"global","effort":"2h"},
  {"id":"F-002","rule":"entity_leakage","severity":"MEDIUM","location":"api.py:all-GET","principle":"Response Contract","domain":"global","effort":"4h"},
  {"id":"F-003","rule":"missing_dto","severity":"MEDIUM","location":"b11_replay_runner.py:start_replay,start_batch_replay","principle":"Parameter Grouping","domain":"replay","effort":"1h"},
  {"id":"F-004","rule":"error_contracts","severity":"MEDIUM","location":"api.py:all-POST,blocks/*","principle":"Error Consistency","domain":"global","effort":"3h"},
  {"id":"F-005","rule":"layer_leakage","severity":"MEDIUM","location":"api.py:dashboard,notifications","principle":"Authorization Boundary","domain":"global","effort":"0.5h"},
  {"id":"F-006","rule":"missing_dto","severity":"LOW","location":"api.py:5-request-models","principle":"Input Validation","domain":"global","effort":"2h"},
  {"id":"F-007","rule":"error_contracts","severity":"LOW","location":"api.py:all-endpoints","principle":"Response Consistency","domain":"global","effort":"3h"}
]
-->
