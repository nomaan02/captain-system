# Dependencies & Reuse Audit Report

<!-- AUDIT-META
worker: ln-625
category: Dependencies & Reuse
domain: global
scan_path: .
score: 5.9
total_issues: 9
critical: 0
high: 1
medium: 5
low: 3
status: completed
-->

## Checks

| ID | Check | Status | Details |
|----|-------|--------|---------|
| 1 | Outdated Packages | warning | vite 6.4.1 patch-behind with active CVEs; npm major-version gaps (React 18→19, Vite 6→8) are deliberate ecosystem choices; Python deps use loose `>=` floors — containers install latest at build time |
| 2 | Unused Dependencies | failed | 10 unused Python production deps across 3 services; 1 ghost npm dependency (prop-types) |
| 3 | Available Features Not Used | warning | pytz used where Python 3.12 stdlib `zoneinfo` available |
| 4 | Custom Implementations | failed | 8 hand-rolled retry loops (tenacity declared but unused); 2 hand-rolled validation blocks (pydantic available); 3 urllib calls bypassing declared deps |
| 5 | Vulnerability Scan (CVE/CVSS) | failed | vite 6.4.1: 2 advisories (1 high, 1 moderate); pip-audit not available on host — Python CVE scan limited to constraint analysis |

## Findings

| Severity | Location | Issue | Principle | Recommendation | Effort |
|----------|----------|-------|-----------|----------------|--------|
| HIGH | captain-gui/package.json (vite 6.4.1) | 2 known CVEs: GHSA-p9ff-h696-f583 (arbitrary file read via dev server WebSocket, CWE-200/306, high); GHSA-4w7w-66w2-5vf9 (path traversal in optimized deps .map handling, CWE-22, moderate). Fix available. | Vulnerability Scan / CVE | Update vite to >=6.4.2 (`npm update vite`). Fix is a patch — safe auto-fix. | S |
| MEDIUM | captain-offline/requirements.txt | 2 unused production deps: `scikit-learn` (no `import sklearn` found), `pydantic` (no `import pydantic` found). Bloats Docker image and increases attack surface. | Unused Deps / Bloat | Remove both lines from requirements.txt and rebuild. | S |
| MEDIUM | captain-online/requirements.txt | 5 unused production deps: `scipy`, `scikit-learn`, `xgboost`, `pydantic`, `tenacity` — none imported in captain-online/ or shared/. xgboost alone adds ~500 MB to the image. | Unused Deps / Bloat | Remove all 5 lines from requirements.txt and rebuild. Verify no dynamic imports exist. | S |
| MEDIUM | captain-command/requirements.txt | 3 unused production deps: `websockets`, `httpx`, `tenacity` — none imported in captain-command/ or shared/. | Unused Deps / Bloat | Remove all 3 lines from requirements.txt and rebuild. | S |
| MEDIUM | captain-gui/package.json | Ghost dependency: `prop-types` imported in 10 .jsx files (ChartPanel, MarketTicker, TopBar, AssetCard, BlockDetail, RiskPanel, SignalCards, SignalExecutionBar, SystemLog, TradeLog) but not declared in package.json. Resolves only as transitive dep — fragile. | Unused Deps / Ghost Dep | Add `prop-types` to production dependencies. | S |
| MEDIUM | captain-command/blocks/orchestrator.py:148-226, captain-offline/blocks/orchestrator.py:79-124, captain-online/blocks/orchestrator.py:703-728, captain-online/blocks/b7_position_monitor.py:387-401, shared/topstep_client.py:351-376, captain-command/blocks/b4_tsm_manager.py:437-451 | 6 hand-rolled exponential-backoff retry loops in production code. `tenacity>=8.0` is declared in captain-online and captain-command requirements.txt but never imported anywhere. Identical backoff pattern (1s→30s cap, `backoff = min(backoff * 2, 30)`) copied across 3 orchestrators. | Custom Implementations / Retry | Replace with `@tenacity.retry(wait=wait_exponential(max=30), ...)` decorators. Consolidates 6 scattered patterns into a single consistent retry policy. | M |
| LOW | captain-command/blocks/telegram_bot.py:587-621, scripts/update_vix_daily.py:40-57, scripts/roll_calendar_update.py:331-351 | 3 calls use `urllib.request.Request` + `urlopen` for HTTP. `requests` and `python-telegram-bot` are already declared deps. telegram_bot.py even uses the telegram library elsewhere in the same file but bypasses it for `send_message`. | Custom Implementations / HTTP | Replace `urllib` calls with `requests.post()` or native `python-telegram-bot` methods. | S |
| LOW | captain-online/requirements.txt (pytz>=2024.1) | `pytz` used in captain-online when Python 3.12 provides `zoneinfo` + `datetime.timezone` in stdlib. External dep for functionality already in the standard library. | Available Features / Native | Replace `pytz.timezone("America/New_York")` with `zoneinfo.ZoneInfo("America/New_York")`. Coordinate with CLAUDE.md timezone rule. | M |
| LOW | scripts/sat_014_google_trends_fetch.py:238-276, scripts/roll_calendar_update.py:249-258 | 2 hand-rolled retry loops in utility scripts (rate-limit retry for Google Trends, DB-busy retry). Lower blast radius than production code but still avoidable duplication. | Custom Implementations / Retry | Replace with `tenacity` decorators if tenacity is added to a shared requirements context, or leave as-is given script scope. | S |

## Extended Analysis

### Python Dependency Constraint Hygiene

All 3 `requirements.txt` files use open-ended `>=` constraints with no upper bound (except `xgboost==2.0.3`). No `requirements.lock`, `pip-tools` compiled output, or `poetry.lock` exists. Each `docker build` can produce a different dependency tree. This is not scored as a finding (it's a process concern, not a code issue), but is noted as a risk factor for reproducibility.

**Declared Python packages across all services:** 20 unique packages (some shared).

### npm Dependency Version Status (captain-gui)

| Package | Current | Latest | Gap |
|---------|---------|--------|-----|
| vite | 6.4.1 | 8.0.8 | 2 major (CVE in current) |
| @vitejs/plugin-react | 4.7.0 | 6.0.1 | 2 major |
| react | 18.3.1 | 19.2.5 | 1 major |
| react-dom | 18.3.1 | 19.2.5 | 1 major |
| eslint | 9.39.4 | 10.2.0 | 1 major |
| web-vitals | 4.2.4 | 5.2.0 | 1 major |
| postcss | 8.5.8 | 8.5.9 | patch |
| react-resizable-panels | 4.8.0 | 4.9.0 | minor |
| react-router-dom | 7.13.2 | 7.14.0 | minor |

React 18→19 and Vite 6→8 are ecosystem-level upgrades with breaking changes. These are deliberate choices, not neglect.

### Custom Implementation Inventory

| Pattern | Occurrences | Library Available | Already Declared? |
|---------|-------------|-------------------|-------------------|
| Exponential backoff retry | 8 (6 prod + 2 scripts) | tenacity | Yes (unused) |
| Dict/input validation | 2 functions (~300 LOC) | pydantic v2 | Yes (command only) |
| Raw urllib HTTP calls | 3 | requests / python-telegram-bot | Yes |

### Unused Dependency Summary

| Service | Declared | Used | Unused | Waste |
|---------|----------|------|--------|-------|
| captain-offline | 8 | 6 | 2 | 25% |
| captain-online | 11 | 6 | 5 | 45% |
| captain-command | 14 | 11 | 3 | 21% |
| captain-gui (npm) | 10 prod | 10 | 0 | 0% |

**Total Python waste:** 10 unused packages across 3 Docker images. `xgboost` alone adds ~500 MB; `scikit-learn` adds ~150 MB. Removing unused deps would significantly reduce image sizes and build times.
