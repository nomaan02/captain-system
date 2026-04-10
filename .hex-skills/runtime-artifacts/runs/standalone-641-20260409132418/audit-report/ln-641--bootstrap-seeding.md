<!-- AUDIT-META
skill: ln-641-pattern-analyzer
pattern: Bootstrap/Seeding
score: 6.1
score_compliance: 62
score_completeness: 74
score_quality: 70
score_implementation: 68
issues_critical: 0
issues_high: 5
issues_medium: 5
issues_low: 4
files_analyzed: 10
-->

# Pattern Analysis: Bootstrap/Seeding

**Audit Date:** 2026-04-09
**Score:** 6.1/10 (C:62 K:74 Q:70 I:68) | Issues: 14 (H:5 M:5 L:4)

## Files Analyzed

| File | Lines |
|---|---|
| `scripts/bootstrap_production.py` | 408 |
| `scripts/init_questdb.py` | 798 |
| `scripts/init_all.py` | 137 |
| `scripts/seed_all_assets.py` | 431 |
| `scripts/seed_test_asset.py` | 144 |
| `scripts/seed_system_params.py` | 113 |
| `scripts/init_sqlite.py` | 54 |
| `scripts/fix_bootstrap_data.py` | 255 |
| `captain-offline/.../bootstrap.py` | 285 |
| `captain-start.sh` | Bootstrap integration |

## Checks

| Check | Score | Evidence |
|---|---|---|
| compliance_check | 62/100 | `init_questdb.py` uses `CREATE TABLE IF NOT EXISTS` (idempotent); bootstrap_production phases 2-4 are NOT idempotent; seed scripts have no upsert guards |
| completeness_check | 74/100 | All 38 tables defined; D08 has no canonical seed path; EWMA unit conversion undocumented; D26/D33 never seeded |
| quality_check | 70/100 | Good script separation; `--dry-run` support; ASSET_SPECS duplicated in 2 files; TIER1_AIMS duplicated in 4 files |
| implementation_check | 68/100 | Docker startup integrates init_questdb; bootstrap_production manual-only; fix_bootstrap_data.py undocumented; zero bootstrap tests |

## Findings

| # | Severity | Category | File:Line | Issue | Suggestion | Effort |
|---|---|---|---|---|---|---|
| G1 | HIGH | compliance | `bootstrap_production.py:191,234,269` | Phases 2-4 not idempotent — unconditional INSERT on re-run appends duplicate D16/D02/D25 rows | Add existence check before each phase INSERT | M |
| G4 | HIGH | compliance | `bootstrap_production.py:118` | Phase 1 requires `seed_all_assets.py` pre-run but Dev Setup docs don't mention this prerequisite | Document dependency order or add auto-detection | S |
| G6 | HIGH | completeness | N/A | D08 (TSM state) has no canonical seed path — only exists in undocumented `fix_bootstrap_data.py` | Move D08 seeding into `bootstrap_production.py` Phase 5 | M |
| G9 | HIGH | completeness | `fix_bootstrap_data.py` | EWMA D05 unit conversion required post-bootstrap, not in any workflow documentation | Integrate into `seed_all_assets.py` or `bootstrap_production.py` | S |
| G15 | HIGH | implementation | `tests/` | Zero unit/integration tests for any bootstrap function; test fixture AIM IDs differ from production | Add bootstrap integration tests; align fixture AIMs with `TIER1_AIMS` | L |
| G2 | MEDIUM | compliance | `seed_system_params.py:88` | No upsert guard — multiplies D17 rows on re-run | Add `EXISTS` check or `LATEST ON` dedup | S |
| G3 | MEDIUM | compliance | `seed_test_asset.py:33,82,104` | No existence check before INSERT into D00/D15/D16 | Add IF NOT EXISTS guards | S |
| G5 | MEDIUM | compliance | `bootstrap_production.py:118-290` | No phase-level try/except — one failure aborts silently with no partial-success report | Wrap each phase in try/except with summary output | S |
| G10 | MEDIUM | quality | `bootstrap_production.py:50`, `seed_all_assets.py:67` | ASSET_SPECS dict duplicated across two files | Extract to `shared/asset_specs.py` | S |
| G11 | MEDIUM | quality | 4 files | TIER1_AIMS `[4,6,8,11,12,15]` duplicated in 4 files with no single source | Extract to `shared/constants.py` | S |
| G7 | LOW | completeness | `init_questdb.py:8` | Docstring says "30 tables" but actual count is 38 | Update docstring count | S |
| G8 | LOW | completeness | N/A | D26/D33 tables created but never seeded or verified | Add seed path or document as runtime-populated only | S |
| G13 | LOW | quality | `bootstrap_production.py:207` | Hardcoded date `"2026-03-27"` in capital_history JSON | Use `datetime.now().date().isoformat()` | S |
| G17 | LOW | implementation | `fix_bootstrap_data.py` | Required post-bootstrap corrections not in any documented or automated flow | Add to CLAUDE.md Bootstrap Scripts and `captain-start.sh` | S |

<!-- DATA-EXTENDED
{
  "pattern": "Bootstrap/Seeding",
  "gaps": {
    "missingComponents": [
      "D08 TSM state canonical seed path",
      "EWMA unit conversion in documented workflow",
      "D26/D33 seed data",
      "Bootstrap integration tests"
    ],
    "inconsistencies": [
      "ASSET_SPECS duplicated in 2 files",
      "TIER1_AIMS duplicated in 4 files",
      "fix_bootstrap_data.py performs required steps but is undocumented",
      "Test fixture AIM IDs [1,2,3,6,7,8,9,10,11,12,13,15,16] differ from production [4,6,8,11,12,15]"
    ]
  }
}
-->
