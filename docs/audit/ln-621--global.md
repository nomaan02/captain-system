---
category: Security
auditor: ln-621-security-auditor
scope: Full codebase (captain-command, captain-online, captain-offline, shared, captain-gui, scripts, config)
date: 2026-04-09
score: 6.5/10
---

# Security Audit Report

**Score: 6.5 / 10**

| Severity | Count |
|----------|-------|
| CRITICAL | 1 |
| HIGH     | 3 |
| MEDIUM   | 4 |
| LOW      | 4 |
| INFO     | 2 |

---

## Check 1: Hardcoded Secrets

**Result: PASS (Clean)**

No hardcoded API keys, passwords, tokens, or private keys found in source code. All secrets are loaded from environment variables via `os.environ.get()` or the AES-256-GCM encrypted vault (`shared/vault.py`).

- `.env` is in `.gitignore` (verified).
- Vault mounted as `:ro` in `docker-compose.yml`.
- No `AKIA*` AWS keys, no `BEGIN RSA/EC/OPENSSH` private keys in any file.

**Findings: 0**

---

## Check 2: SQL Injection

**Result: PASS (Residual low-risk f-strings in internal scripts)**

All user-facing SQL queries use parameterized binding. The Session 04 fix (obs 1154/1166) correctly remediated the `b7_notifications.py` role query with positional `$N` placeholders.

| # | Location | Pattern | User Input? | Severity |
|---|----------|---------|-------------|----------|
| 2.1 | `scripts/verify_questdb.py:154` | `f"SELECT ... '{table_name}'"` — table name from hardcoded dict | No | **LOW** |
| 2.2 | `scripts/captain-update.sh:181` | `f'SELECT count() FROM {table}'` — table from hardcoded dict | No | **LOW** |
| 2.3 | `shared/questdb_client.py:99` | `f"INSERT INTO ... ({col_names})"` — column names from module constant `D00_COLUMNS`; values use `%s` parameterized | No | **LOW** |

**Recommendation:** Even for internal scripts, use parameterized queries or at minimum validate table names against an allowlist. Effort: **S** (< 1 hour).

---

## Check 3: XSS Vulnerabilities

**Result: PASS (No confirmed XSS)**

Three `innerHTML` usages found in `captain-gui/src/components/chart/TradingViewWidget.jsx:42,51,75`. All are safe:

- Line 42/75: `containerRef.current.innerHTML = ""` — clearing container, no user data.
- Line 51: `script.innerHTML = JSON.stringify({...})` — widget config with hardcoded values and `selectedAsset` from an internal state map (`TV_SYMBOLS`), not raw user input.

No `dangerouslySetInnerHTML`, `v-html`, or `document.write` with user data found.

**Findings: 0**

---

## Check 4: Insecure Dependencies

### 4.1 No Lockfile or Hash Pinning

| # | Location | Finding | Severity |
|---|----------|---------|----------|
| 4.1 | All `requirements.txt` | `>=` floor pinning only, no `pip-compile` lockfile, no `--require-hashes` | **HIGH** |

All packages use `>=` minimum version without upper bounds. No `requirements.lock` or hash verification exists. A compromised release of any dependency (especially small-community packages like `pysignalr`) would be pulled automatically on rebuild.

**Recommendation:** Adopt `pip-compile --generate-hashes` for all three services. Effort: **M** (2-3 hours initial setup + CI integration).

### 4.2 Base Images Not Digest-Pinned

| # | Location | Finding | Severity |
|---|----------|---------|----------|
| 4.2 | All Dockerfiles | `python:3.12-slim`, `redis:7-alpine`, `nginx:alpine` — tag-only, no `sha256` digest pin | **LOW** |

Tags are mutable. A `sha256` digest pin guarantees exact reproducibility.

**Recommendation:** Pin base images by digest. Effort: **S**.

---

## Check 5: Missing Input Validation

### 5.1 Unvalidated Path Parameters (User-Facing)

| # | Location | Endpoint | Finding | Severity |
|---|----------|----------|---------|----------|
| 5.1a | `api.py:509` | `GET /api/dashboard/{user_id}` | Bare `str` path param, no length/charset constraint. Passed directly to `build_dashboard_snapshot()` which queries DB. | **HIGH** |
| 5.1b | `api.py:520` | `GET /api/aim/{aim_id}/detail` | `int` type coercion only, no range check. Negative/huge IDs accepted. | **MEDIUM** |
| 5.1c | `api.py:526,536` | `POST /api/aim/{aim_id}/activate` and `/deactivate` | Same as 5.1b — raw `int` forwarded to Redis command bus. | **MEDIUM** |
| 5.1d | `api.py:644` | `GET /api/notifications/preferences/{user_id}` | Bare `str`, no constraints, passed to DB lookup. | **MEDIUM** |
| 5.1e | `api.py:678` | `GET /api/notifications/telegram-history` | `limit: int = 50` clamped to `min(limit, 200)` but accepts negative values (negative LIMIT in SQL is undefined). | **MEDIUM** |

### 5.2 Weak Pydantic Models (Structural Gaps)

| # | Location | Field | Finding | Severity |
|---|----------|-------|---------|----------|
| 5.2a | `api.py` (ReplayStartRequest) | `date: str` | No date format validation (`YYYY-MM-DD`). Passed to replay engine as `date_str`. | **HIGH** |
| 5.2b | `api.py` (BatchReplayStartRequest) | `date_from/date_to: str` | No format or chronological order check. | **HIGH** |
| 5.2c | `api.py` (ReplayControlRequest) | `action: str` | No `Literal` enum. Any string forwarded to `control_replay()`. | **MEDIUM** — potential for unexpected behavior |
| 5.2d | `api.py` (ReplayStartRequest) | `speed: float` | No `ge`/`le` bounds. Zero or negative speeds accepted. | **LOW** |
| 5.2e | `api.py` (ReportRequest) | `report_type: str` | No whitelist against `REPORT_TYPES`. | **LOW** |
| 5.2f | `api.py` (ValidateInputRequest) | `input_type: str` | No whitelist against known input types. | **LOW** |

**Recommendation:** Add `Literal` types for enum fields, `constr(regex=...)` for dates, `ge=0.1` bounds for speed, and a `constr(max_length=128, regex=...)` for user_id path params. Effort: **M** (2-4 hours).

---

## Additional Findings

### A.1 Unsafe Deserialization — pickle.loads

| # | Location | Finding | Severity |
|---|----------|---------|----------|
| A.1 | `captain-offline/captain_offline/blocks/b1_drift_detection.py:106` | `pickle.loads(base64.b64decode(d["state"]))` — deserializes ADWIN detector state from QuestDB | **CRITICAL** |

`pickle.loads` can execute arbitrary code if an attacker can inject a crafted payload into the `d["state"]` field in QuestDB. The data source is the database (not direct user input), so exploitation requires prior DB compromise — but this is exactly the kind of defense-in-depth violation that turns a data breach into full RCE.

**Recommendation:** Replace `pickle` with a safe serialization format (JSON, msgpack) or use `RestrictedUnpickler` that only allows `river.drift.ADWIN` classes. Effort: **M** (2-3 hours — need to handle river's internal state serialization).

### A.2 Ephemeral JWT Secret Fallback

| # | Location | Finding | Severity |
|---|----------|---------|----------|
| A.2 | `api.py:72-74` | If `JWT_SECRET_KEY` env var is unset, a random ephemeral key is generated. All tokens are invalidated on every restart. | **MEDIUM** — operational risk, not a direct exploit |

**Recommendation:** Fail hard on startup if `JWT_SECRET_KEY` is unset (production), or at minimum warn loudly in logs. Currently warns but continues. Effort: **S**.

### A.3 Fixed PBKDF2 Salt in Vault

| # | Location | Finding | Severity |
|---|----------|---------|----------|
| A.3 | `shared/vault.py:24` | `VAULT_SALT = b"captain-vault-salt-v1"` — fixed salt for all vault encryptions | **MEDIUM** |

OWASP requires per-credential random salts. A fixed salt allows precomputed rainbow table attacks against the master key. Low exploitability (requires vault file access), but deviates from best practice.

**Recommendation:** Generate random salt on vault creation, store it in the vault file header. Requires vault format migration. Effort: **M**.

### A.4 Exception String Leakage in Internal Blocks

| # | Location | Finding | Severity |
|---|----------|---------|----------|
| A.4 | `b11_replay_runner.py:184,193,198`, `b5_injection_flow.py:146`, `b9_incident_response.py:189,257`, `b3_api_adapter.py:189,274` | `str(exc)` returned in error dicts. Some of these propagate to API responses. | **MEDIUM** |

Internal exception strings may leak implementation details (DB schema, file paths, library versions) if they reach the API response. The top-level API endpoints already return generic `"Internal server error"` — but block-level `str(exc)` in return dicts can bypass this if a new endpoint exposes them.

**Recommendation:** Audit the chain from block return dicts to API responses. Ensure no `str(exc)` reaches the client. Effort: **S-M**.

---

## Scoring Breakdown

| Check | Weight | Penalty | Notes |
|-------|--------|---------|-------|
| Hardcoded Secrets | 2.0 | 0.0 | Clean |
| SQL Injection | 2.0 | -0.3 | 3 low-risk internal f-strings |
| XSS Vulnerabilities | 1.5 | 0.0 | Clean |
| Insecure Dependencies | 1.5 | -0.8 | No lockfile/hashes (HIGH) |
| Missing Input Validation | 3.0 | -1.4 | 5 unvalidated endpoints, 6 weak Pydantic models |
| pickle.loads (bonus) | — | -0.5 | CRITICAL deserialization |
| Vault fixed salt | — | -0.3 | Deviation from OWASP |
| Ephemeral JWT fallback | — | -0.2 | Operational risk |

**Raw: 10.0 - 3.5 = 6.5 / 10**

---

## Summary

The codebase has a solid security baseline: no hardcoded secrets, non-root containers, all ports on localhost, JWT auth on all endpoints, AES-256-GCM vault, and parameterized SQL queries. The Session 04 hardening (JWT, non-root, SQL fix, RCE endpoint removal) addressed the most critical gaps.

**Remaining priorities:**

1. **CRITICAL:** Replace `pickle.loads` in `b1_drift_detection.py:106` with safe deserialization
2. **HIGH:** Add `pip-compile --generate-hashes` for supply-chain integrity
3. **HIGH:** Validate all path parameters (`user_id`, `aim_id`) and date strings at API boundary
4. **MEDIUM:** Fail-hard on missing `JWT_SECRET_KEY` in production
5. **MEDIUM:** Migrate vault to use random per-file salt
6. **MEDIUM:** Audit `str(exc)` propagation to API responses
