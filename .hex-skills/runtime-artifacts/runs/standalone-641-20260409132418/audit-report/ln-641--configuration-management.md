<!-- AUDIT-META
skill: ln-641-pattern-analyzer
pattern: Configuration Management
score: 6.4
score_compliance: 72
score_completeness: 48
score_quality: 78
score_implementation: 65
issues_critical: 0
issues_high: 2
issues_medium: 2
issues_low: 2
files_analyzed: 12
-->

# Pattern Analysis: Configuration Management

**Audit Date:** 2026-04-09
**Score:** 6.4/10 (C:72 K:48 Q:78 I:65) | Issues: 6 (H:2 M:2 L:2)

## Files Analyzed

| File | Purpose |
|---|---|
| `shared/constants.py` | Shared constants (FROZEN) |
| `.env.template` | Environment variable template (13 of 27 vars) |
| `docker-compose.yml` | Container env injection |
| `config/` | JSON configs (TSM, compliance, contracts) |
| `shared/questdb_client.py` | Infrastructure defaults |
| `shared/redis_client.py` | Infrastructure defaults |
| `captain-command/.../api.py` | JWT/API secret keys |
| All 3 `main.py` files | Startup env reads |

## Checks

| Check | Score | Evidence |
|---|---|---|
| compliance_check | 72/100 | Clean `TOPSTEP_`, `QUESTDB_`, `REDIS_`, `CAPTAIN_` prefixes; stale `CON.F.US.EP.H26` contract default in 2 files |
| completeness_check | 48/100 | Only 13/27 env vars in template; `JWT_SECRET_KEY` and `API_SECRET_KEY` undocumented; no startup validation of secret env vars |
| quality_check | 78/100 | Well-centralized infrastructure params; one DRY violation (duplicate contract default); no hardcoded IPs/ports |
| implementation_check | 65/100 | Docker integration solid; captain-offline missing `env_file`; no hot-reload; stale contract default at runtime |

## Findings

| # | Severity | Category | File:Line | Issue | Suggestion | Effort |
|---|---|---|---|---|---|---|
| CFG-01 | HIGH | completeness | `api.py:67,70` + `.env.template` | `JWT_SECRET_KEY` and `API_SECRET_KEY` not in template — ephemeral JWT fallback silently invalidates sessions on restart; auth disabled without API key | Add both to `.env.template` with generation instructions | S |
| CFG-02 | HIGH | compliance | `b2_gui_data_server.py:38`, `b3_api_adapter.py:124` | `TOPSTEP_CONTRACT_ID` defaults to expired `CON.F.US.EP.H26` (March 2026) in two places | Centralize default in `shared/constants.py` or read from `config/contract_ids.json` | S |
| CFG-03 | MEDIUM | completeness | All 3 `main.py` | No startup validation of required secret env vars — `TOPSTEP_USERNAME`, `TOPSTEP_API_KEY`, `VAULT_MASTER_KEY` fail silently at point-of-use | Add `_validate_required_env()` at startup with explicit error messages | S |
| CFG-04 | MEDIUM | completeness | `.env.template` | 14 of 27 env vars undocumented in template | Add missing vars with comments and defaults | S |
| CFG-05 | LOW | quality | `b2_gui_data_server.py:38`, `b3_api_adapter.py:124` | `TOPSTEP_CONTRACT_ID` default duplicated in two files | Centralize in `shared/constants.py` | S |
| CFG-06 | LOW | implementation | `docker-compose.yml` | `captain-offline` has no `env_file: .env` — by design but undocumented | Add comment documenting this is intentional | S |

<!-- DATA-EXTENDED
{
  "pattern": "Configuration Management",
  "gaps": {
    "missingComponents": [
      "14 env vars missing from .env.template (48% coverage)",
      "No startup validation of secret env vars",
      "No hot-reload mechanism (acceptable for trading system)"
    ],
    "inconsistencies": [
      "Stale contract ID default (H26 expired March 2026)",
      "TOPSTEP_CONTRACT_ID default duplicated in 2 files",
      "captain-offline missing env_file directive (intentional but undocumented)"
    ]
  }
}
-->
