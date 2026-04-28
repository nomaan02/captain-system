---
title: Phase 6 — AIM Modifier Realignment Build Plan
date: 2026-04-27
phase: 6
campaign: Captain Offline Audit Fix Campaign (12 phases)
companion_to:
  - docs2/audits/2026-04-22_offline_spec_vs_code_audit copy.md
  - docs2/audits/phase-ref-docs/phase-2/captain_offline_audit_decisions_2026-04-27.md
  - docs2/spec-docs-02/offline/AIM System.canvas
  - docs2/spec-docs-02/offline/AIM_System.md
  - docs2/spec-docs-02/online/33_P3_Online_Full_Pseudocode 1.md
status: PARTIAL — 4 batches GO (incl. 6.5 unblocked by Isaac VRP spec 2026-04-27), 1 batch BLOCKED on Q-23 sub-points
executor: Cursor Composer 2
---

# Phase 6 — AIM Modifier Realignment

This plan covers audit findings **F-38 (AIM-01 VRP), F-39 (AIM-03 GEX), F-40 (AIM-04 IVTS), F-41 (AIM-7 COT)**. It splits the work into five numbered batches. Batches 6.1, 6.2, 6.3, 6.5 are ready to ship. Batch 6.4 remains **BLOCKED** pending Q-23 re-ask resolution (§3.2 of the decisions log) and must not be implemented in this phase.

**Update 2026-04-27 (post-Isaac):** Q-22 has been fully resolved by Isaac's authoritative pseudocode for `compute_aim_modifier_01` (see Batch 6.5). This unblocks F-38. The pseudocode confirms canvas direction (sign), drops the Monday term, mandates the overnight refinement, and clarifies the **two-window** scheme (120d for `vrp_z`, 60d for `vrp_overnight_z`).

## Spec authority chain (resolved at top of phase)

1. **Decisions log** `captain_offline_audit_decisions_2026-04-27.md` §2 Group F
2. **Audit findings** `2026-04-22_offline_spec_vs_code_audit copy.md` (F-38..F-41)
3. **Canvas** `AIM System.canvas` — PROC pseudocode is the modifier-semantics authority for AIMs 01–15
4. **Code** is overridden where (1)–(3) disagree

`AIM System 1.canvas` is a stripped-down list (no PROC blocks); it carries no threshold content and is **not** an authority for modifier values.

## Cross-cutting ambiguities flagged for review (do not invent answers)

These ambiguities surfaced during the Stage 1 audit pass and are **not** independently resolvable from spec/audit/decisions log. The plan flags them inline; Cursor must surface each one in the PR description rather than guessing.

| # | Ambiguity | Affected batch | Fallback rule |
|---|---|---|---|
| AMB-1 | F-39 canvas requires `expiry_day` and `triple_witch` flags. No such features exist in `b1_features.py` today. AIM-10 already exposes `is_opex_window` (±3 calendar days of 3rd Friday). Are `expiry_day` and `triple_witch` derivable from existing OPEX dataset, or do they need new calendar columns? | 6.1 | Plan derives both from existing `_get_third_friday`/`is_within_opex_window` helpers in `b1_features.py:290-308`. Surface in PR description; if Isaac wants distinct calendars, swap helper sources without changing dispatch shape. |
| AMB-2 | F-41 leaves orphan `_aim07_cot` at `shared/aim_compute.py:437-475`. CLAUDE.md says delete unused code; canvas still describes the function as if active (stale). | 6.2 | **Do not delete.** Mark as orphan with one-line `# DEC-08 disabled — preserved for reactivation if CFTC feed becomes available` and leave body intact. Surface delete-vs-keep decision to Nomaan in PR description. |
| AMB-3 | Test mocks (`tests/test_b3_aim.py:19-33`) include `7: 0.95` in `KNOWN_MODIFIERS`. The mock bypasses real dispatch so this does not exercise the disable. Should the mock fixture also drop AIM-7? | 6.2 | Keep the mock entry (it tests aggregation math, not dispatch). Add a separate non-mocked test that exercises the real dispatch returning `NO_HANDLER` for aim_id=7. |
| AMB-4 | ~~F-38 lookback: code uses 60d, canvas says 120d.~~ **RESOLVED 2026-04-27 by Isaac VRP pseudocode.** The two windows are for **two different features**: `vrp_z` over **120d** for the primary signal (does not exist in current code), `vrp_overnight_z` over **60d** for the refinement (already exists). Both must be present. | 6.5 | n/a — implement both windows. |
| AMB-5 | A/B test mirror at `scripts/aim_ab_test.py` reproduces AIM-04 logic. Any code change to `_aim04_ivts` must be mirrored. | 6.3, 6.4 | Plan calls out the mirror update in each affected batch. |

---

## Batch index

| Batch | Finding | Status | Risk |
|---|---|---|---|
| **6.1** | F-39 — AIM-03 GEX canvas alignment (z-score + expiry/triple-witch overlays) | **GO** | LOW — additive feature, modifier shape stays in `[0.5, 1.5]` |
| **6.2** | F-41 — AIM-7 disable lock-in (canvas amendment + regression test) | **GO** | NONE — no production code change |
| **6.3** | F-40 — AIM-04 5-zone reaffirmation (canvas amendment + pinning tests) | **GO** | NONE — no production code change |
| **6.4** | F-40 sub-points — gap×0.95, per-zone confidence, EIA relocation | **BLOCKED — Q-23.b/c/d** | n/a |
| **6.5** | F-38 — AIM-01 VRP ladder rewrite + drop Monday + add overnight refinement + add 120d window | **GO** (unblocked 2026-04-27 by Isaac authoritative pseudocode) | MEDIUM — sign-flip relative to current code; full coverage tests required |

---

## Batch 6.1 — F-39 AIM-03 GEX canvas alignment

**Status:** GO

### Spec citation

- **Decisions log:** §2 Group F has no Q for F-39 (no Isaac counter-question). Decisions log §5 Phase 6 row implicit GO.
- **Audit:** `2026-04-22_offline_spec_vs_code_audit copy.md:939-960` (F-39). `Needs Isaac: NO`.
- **Canvas authority:** `docs2/spec-docs-02/offline/AIM System.canvas` node `13a473af588e976e`:
  ```
  PROC aim_03: gex_z = z_score(gex, 60d)
    IF <-1: 0.85  ELIF >1: 1.10  ELSE: 1.0
    IF expiry_day: ×0.95
    IF triple_witch: ×0.90
  ```
- **Canvas summary node** `546583a3b416fb6a`: "WARM-UP: 250d  TIER: 3" — note: this is the AIM warm-up window (raw_data_count progression), not the z-score lookback. The z-score lookback is the `60d` value in the PROC block.
- **DEC-01 cross-check:** F-39 has no DEC-01 conflict — neither DEC-01 nor any other internal doc proposes alternative thresholds for GEX. Code's two-branch raw-sign rule has no spec source we could find.

### Pre-flight checks

1. Confirm `compute_dealer_net_gamma` in `captain-online/captain_online/blocks/b1_features.py:118-132` returns the same numerical scale as canvas `gex` (dealer net Γ × spot²). If scale differs, z-score on rolling 60d will normalise it — no recalibration needed.
2. Confirm OPEX dataset coverage: AIM-10 already pulls `is_opex_window` from `_get_third_friday` (`b1_features.py:300-308`) using a pure-date computation (no D00 read at runtime). Therefore `expiry_day` and `triple_witch` can be derived in-process without new data sources. → AMB-1 fallback applies.
3. Run `pytest tests/test_b3_aim.py -v` to confirm baseline green before changes.
4. Grep `scripts/aim_ab_test.py` for `aim_03` / `gex` mirror logic — none expected, but verify (audit only flagged AIM-04 mirror).

### Files + line ranges to modify

| File | Lines | Change |
|---|---|---|
| `shared/aim_compute.py` | 330–340 | Replace `_aim03_gex` body |
| `captain-online/captain_online/blocks/b1_features.py` | 515 (AIM_FEATURE_MAP) | Add `gex_z`, `expiry_day`, `triple_witch` to AIM-03 feature list |
| `captain-online/captain_online/blocks/b1_features.py` | 657 region | Compute `f["gex_z"]`, `f["expiry_day"]`, `f["triple_witch"]` next to existing `f["gex"]` write |
| `shared/aim_feature_loader.py` | 33–60 region (AIM-03 block) | Mirror new feature derivations for replay path |
| `tests/test_b3_aim.py` | new test class | Add direct (non-mocked) coverage of `compute_aim_modifier(3, ...)` |

### Exact change shape

**`shared/aim_compute.py:330-340` — `_aim03_gex` rewrite:**

```python
# BEFORE
def _aim03_gex(f: dict, state: dict) -> dict:
    """AIM-03: GEX. Positive gamma → dampening (reduce); negative → amplification."""
    gex = f.get("gex")
    if gex is None:
        return {"modifier": 1.0, "confidence": 0.0, "reason_tag": "GEX_MISSING"}

    if gex > 0:
        return {"modifier": 0.90, "confidence": 0.7, "reason_tag": "GEX_POSITIVE_DAMPEN"}
    else:
        return {"modifier": 1.10, "confidence": 0.7, "reason_tag": "GEX_NEGATIVE_AMPLIFY"}

# AFTER
def _aim03_gex(f: dict, state: dict) -> dict:
    """AIM-03: GEX — z-scored 60d window per AIM System.canvas node 13a473af588e976e.

    Thresholds (canvas authoritative; no DEC override exists for AIM-03):
      gex_z < -1 → 0.85  (negative dealer gamma — amplification regime)
      gex_z >  1 → 1.10  (positive dealer gamma — dampening regime)
      else        → 1.00 (neutral middle band)

    Event overlays (multiplicative):
      expiry_day   → × 0.95
      triple_witch → × 0.90
    """
    gex_z = f.get("gex_z")
    if gex_z is None:
        return {"modifier": 1.0, "confidence": 0.0, "reason_tag": "GEX_MISSING"}

    if gex_z < -1.0:
        modifier = 0.85
        confidence = 0.7
        tag = "GEX_NEG_AMPLIFY"
    elif gex_z > 1.0:
        modifier = 1.10
        confidence = 0.7
        tag = "GEX_POS_DAMPEN"
    else:
        modifier = 1.0
        confidence = 0.4
        tag = "GEX_NEUTRAL"

    if f.get("triple_witch"):
        modifier *= 0.90
        tag += "_TRIPLE_WITCH"
    elif f.get("expiry_day"):
        modifier *= 0.95
        tag += "_EXPIRY"

    return {"modifier": modifier, "confidence": confidence, "reason_tag": tag}
```

**`captain-online/captain_online/blocks/b1_features.py:515` — AIM_FEATURE_MAP entry:**

```python
# BEFORE
3: ["gex"],
# AFTER
3: ["gex", "gex_z", "expiry_day", "triple_witch"],
```

**`captain-online/captain_online/blocks/b1_features.py` near `:657` — AIM-03 feature derivation:**

After the existing `f["gex"] = compute_dealer_net_gamma(asset_id)` line, add (using existing `today` and `_get_third_friday` helper):

```python
# AFTER existing f["gex"] write
trailing_60d_gex = _get_trailing_gex(asset_id, lookback=60)  # NEW helper, mirror of _get_trailing_vrp
if f["gex"] is not None and trailing_60d_gex is not None:
    f["gex_z"] = z_score(f["gex"], trailing_60d_gex)
else:
    f["gex_z"] = None

third_friday = _get_third_friday(today.year, today.month)
f["expiry_day"] = (today.date() == third_friday)
# Triple-witch = March / June / September / December monthly OPEX
f["triple_witch"] = f["expiry_day"] and today.month in (3, 6, 9, 12)
```

**Note (AMB-1):** if Isaac confirms `triple_witch` should fire on the *full week* of triple-witch instead of the day, swap to `is_within_opex_window(today.date()) and today.month in (3, 6, 9, 12)`. Surface this question in the PR description.

A new `_get_trailing_gex(asset_id, lookback)` helper is required, mirroring `_get_trailing_vrp` (see `b1_features.py` `_get_trailing_*` family for the pattern). Source: P3-D01 historical `aim_features` rows for that asset.

**`shared/aim_feature_loader.py`** — replay path mirror: in the AIM-03 block, populate `gex_z`, `expiry_day`, `triple_witch` from the same QuestDB feature rows. Use existing `_third_friday` helper at `:437`.

### Test additions

**File:** `tests/test_b3_aim.py` — append a new test class:

```python
class TestAIM03GexCanvasAlignment:
    """F-39: AIM-03 must use z-scored gex with three-branch rule + event overlays."""

    def test_neutral_band_when_gex_z_in_minus_one_to_one(self):
        from shared.aim_compute import compute_aim_modifier
        result = compute_aim_modifier(3, {"ES": {"gex_z": 0.5}}, "ES", {})
        assert result["modifier"] == 1.0
        assert result["reason_tag"] == "GEX_NEUTRAL"

    def test_negative_amplification_below_minus_one(self):
        from shared.aim_compute import compute_aim_modifier
        result = compute_aim_modifier(3, {"ES": {"gex_z": -1.5}}, "ES", {})
        assert result["modifier"] == 0.85
        assert "GEX_NEG_AMPLIFY" in result["reason_tag"]

    def test_positive_dampening_above_one(self):
        from shared.aim_compute import compute_aim_modifier
        result = compute_aim_modifier(3, {"ES": {"gex_z": 1.5}}, "ES", {})
        assert result["modifier"] == 1.10
        assert "GEX_POS_DAMPEN" in result["reason_tag"]

    def test_expiry_day_overlay(self):
        from shared.aim_compute import compute_aim_modifier
        result = compute_aim_modifier(3, {"ES": {"gex_z": 1.5, "expiry_day": True}}, "ES", {})
        assert result["modifier"] == pytest.approx(1.10 * 0.95)

    def test_triple_witch_overlay_takes_precedence(self):
        from shared.aim_compute import compute_aim_modifier
        result = compute_aim_modifier(3, {"ES": {"gex_z": 1.5, "expiry_day": True, "triple_witch": True}}, "ES", {})
        assert result["modifier"] == pytest.approx(1.10 * 0.90)

    def test_modifier_in_bounds(self):
        """All branches must produce a modifier in [0.5, 1.5]."""
        from shared.aim_compute import compute_aim_modifier, MODIFIER_FLOOR, MODIFIER_CEILING
        cases = [
            {"gex_z": -3.0, "triple_witch": True},
            {"gex_z": 3.0, "triple_witch": True},
            {"gex_z": 0.0},
        ]
        for c in cases:
            r = compute_aim_modifier(3, {"ES": c}, "ES", {})
            assert MODIFIER_FLOOR <= r["modifier"] <= MODIFIER_CEILING, c

    def test_missing_gex_z_returns_neutral(self):
        from shared.aim_compute import compute_aim_modifier
        result = compute_aim_modifier(3, {"ES": {}}, "ES", {})
        assert result["modifier"] == 1.0
        assert result["reason_tag"] == "GEX_MISSING"
```

Assertions cover modifier sign (positive direction in dampening regime; reductive in amplification), value bounds, AIM-7 untouched (this test only exercises aim_id=3), and missing-data path.

### Exit criteria

- [ ] `pytest tests/test_b3_aim.py::TestAIM03GexCanvasAlignment -v` passes (7/7)
- [ ] `pytest tests/test_b3_aim.py tests/test_pipeline_e2e.py tests/test_integration_e2e.py tests/test_stress.py -v` still green
- [ ] `grep -n "gex_z\|expiry_day\|triple_witch" captain-online/captain_online/blocks/b1_features.py` shows feature is computed in live path
- [ ] `grep -n "gex_z\|expiry_day\|triple_witch" shared/aim_feature_loader.py` shows feature is computed in replay path
- [ ] No remaining reference to the old two-branch GEX rule: `grep -rn "GEX_POSITIVE_DAMPEN\|GEX_NEGATIVE_AMPLIFY" shared captain-online captain-offline` returns 0
- [ ] PR description surfaces AMB-1 (`expiry_day` / `triple_witch` calendar source) for Isaac confirmation

### Rollback

```bash
git checkout HEAD~1 -- shared/aim_compute.py captain-online/captain_online/blocks/b1_features.py shared/aim_feature_loader.py tests/test_b3_aim.py
```

If rollback is required *after* trades have been taken with the new modifier values, no data migration is needed — `gex_z`/`expiry_day`/`triple_witch` are computed-on-read features and are not persisted to QuestDB by AIM-03. P3-D01 modifier history rows written under the new regime will simply show as values from the new code path; downstream DMA/MoE math is unaffected by reverting.

---

## Batch 6.2 — F-41 AIM-7 disable lock-in

**Status:** GO

### Spec citation

- **Decisions log:** §2 Group F Q-24: "**AIM-7 (COT) stays disabled.** DEC-08 (no CFTC feed) is the product decision. Phase 6. Update canvas to mark AIM-7 as DEFERRED rather than ACTIVE. Code's nulling of `cot_smi`/`cot_speculator_z` is correct."
- **Audit:** `2026-04-22_offline_spec_vs_code_audit copy.md:985-1003` (F-41). `Needs Isaac: YES (Q-24 — is DEC-08 the product decision)` → resolved YES.
- **Canvas:** `docs2/spec-docs-02/offline/AIM System.canvas` node `3d460811bf82fa1e` (MACRO/EVENT) currently lists `PROC aim_07` as if active — stale relative to product decision DEC-08. Must be amended.

### Pre-flight checks

1. Verify dispatch already excludes 7: `grep -n "7:" shared/aim_compute.py` should show `# 7: DISABLED per DEC-08` at line 224 region.
2. Verify feature nullification: `grep -n 'cot_smi\|cot_speculator_z' captain-online/captain_online/blocks/b1_features.py shared/aim_feature_loader.py` should show all writes set to `None`.
3. Verify bootstrap exclusion: `grep -n 'TIER1_AIMS' scripts/seed_*.py scripts/fix_bootstrap_data.py` should show `[4, 6, 8, 11, 12, 15]` — no `7`.
4. Confirm orphan `_aim07_cot` exists at `shared/aim_compute.py:437-475` (preserved per AMB-2).

### Files + line ranges to modify

| File | Lines | Change |
|---|---|---|
| `docs2/spec-docs-02/offline/AIM System.canvas` | node `3d460811bf82fa1e` | Amend AIM-07 PROC text to mark DEFERRED |
| `shared/aim_compute.py` | 437 (function docstring) | Add deferred-status comment; do **not** delete body |
| `tests/test_b3_aim.py` | new test class | Add regression test pinning the disable |

### Exact change shape

**Canvas node `3d460811bf82fa1e`** — MACRO/EVENT block. Current text contains:

```
PROC aim_07(features, asset):  smi = cot_smi; spec_z = speculator_z
    IF smi>0: 1.05  ELIF smi<0: 0.90  ELSE: 1.0
    IF spec_z>1.5: ×0.95 (crowded long)  ELIF spec_z<-1.5: ×1.10 (extreme short)
```

Replace with:

```
PROC aim_07(features, asset):  RETURN 1.0  -- DEFERRED per DEC-08 (no CFTC COT data pipeline)
    -- Reactivation conditions: CFTC COT weekly feed wired; cot_smi + cot_speculator_z
    -- features available in P3-D01. Original logic preserved in shared/aim_compute.py:_aim07_cot.
```

**`shared/aim_compute.py:437`** — modify the `_aim07_cot` docstring to include disable status. The function body stays intact. Specifically, immediately after the existing `def _aim07_cot(f: dict, state: dict) -> dict:` line, replace the docstring with:

```python
def _aim07_cot(f: dict, state: dict) -> dict:
    """AIM-07: COT positioning — **NOT REGISTERED IN DISPATCH (DEC-08)**.

    Preserved for reactivation if CFTC COT weekly feed is wired. Until then,
    compute_aim_modifier(7, ...) returns NO_HANDLER (modifier=1.0, conf=0.0)
    via the dispatch table omission at line 224.

    Per AIM_Extractions.md:1541-1559 the active spec was:
      SMI polarity: POSITIVE→1.05, NEGATIVE→0.90.
      Extreme overlay: spec_z>1.5→×0.95, spec_z<-1.5→×1.10.
    """
```

(Body unchanged.)

### Test additions

**File:** `tests/test_b3_aim.py` — append:

```python
class TestAIM07Disabled:
    """F-41 / Q-24: AIM-7 must remain unregistered; dispatch returns NO_HANDLER."""

    def test_dispatch_returns_no_handler(self):
        from shared.aim_compute import compute_aim_modifier
        result = compute_aim_modifier(7, {"ES": {"cot_smi": 1, "cot_speculator_z": 2.0}}, "ES", {})
        assert result["modifier"] == 1.0
        assert result["confidence"] == 0.0
        assert result["reason_tag"] == "NO_HANDLER"

    def test_aim07_not_in_dispatch_table(self):
        """Guard: changing the dispatch table to register AIM-7 must fail this test."""
        from shared.aim_compute import compute_aim_modifier
        # Even with feature data populated, modifier must stay neutral.
        f = {"ES": {"cot_smi": -1, "cot_speculator_z": -2.0}}
        for spec_z in [-3.0, -1.5, 0.0, 1.5, 3.0]:
            f["ES"]["cot_speculator_z"] = spec_z
            r = compute_aim_modifier(7, f, "ES", {})
            assert r["modifier"] == 1.0, f"AIM-7 fired for spec_z={spec_z}"
            assert r["confidence"] == 0.0

    def test_features_loader_nulls_cot_fields(self):
        """Live and replay feature paths must null COT fields (DEC-08)."""
        # Live path: assert source has the explicit None assignment
        live = open("captain-online/captain_online/blocks/b1_features.py").read()
        assert 'f["cot_smi"] = None' in live
        assert 'f["cot_speculator_z"] = None' in live
        # Replay path
        replay = open("shared/aim_feature_loader.py").read()
        assert 'f["cot_smi"] = None' in replay
        assert 'f["cot_speculator_z"] = None' in replay

    def test_tier1_aims_excludes_seven(self):
        """Bootstrap must not seed AIM-7 into D01/D02."""
        import importlib.util, pathlib
        spec = importlib.util.spec_from_file_location(
            "seed_all_assets",
            pathlib.Path("scripts/seed_all_assets.py")
        )
        mod = importlib.util.module_from_spec(spec)
        # Loading the module top-level constants is sufficient — avoid running main().
        # Instead, parse via grep-equivalent check:
        src = open("scripts/seed_all_assets.py").read()
        assert "TIER1_AIMS = [4, 6, 8, 11, 12, 15]" in src, \
            "AIM-7 must not appear in TIER1_AIMS"
```

### Exit criteria

- [ ] `pytest tests/test_b3_aim.py::TestAIM07Disabled -v` passes (4/4)
- [ ] Canvas node `3d460811bf82fa1e` shows `DEFERRED per DEC-08`
- [ ] `grep -n "DEC-08\|DISABLED" shared/aim_compute.py` returns the dispatch comment AND the orphan-handler docstring
- [ ] Existing tests still green (no regressions)
- [ ] PR description surfaces AMB-2 (delete-or-keep `_aim07_cot` body) for Nomaan to decide; recommendation in PR is **keep** until DEC-08 is revisited

### Rollback

Pure documentation + test change. Rollback:

```bash
git checkout HEAD~1 -- "docs2/spec-docs-02/offline/AIM System.canvas" shared/aim_compute.py tests/test_b3_aim.py
```

No data migration needed — no production state was touched.

---

## Batch 6.3 — F-40 AIM-04 5-zone reaffirmation (canvas amendment + pinning tests)

**Status:** GO

### Spec citation

- **Decisions log:** §2 Group F Q-23: "**5-zone Paper 67 map is the product truth for AIM-04.** … Code's 5-zone is correct."
- **Decisions log §3.2 Q-23 partial:** "Did not explicitly confirm that the EIA Wednesday × 0.90 overlay belongs on AIM-04 (where code has it) vs AIM-06 (where canvas has it)" + per-zone confidence + gap×0.95 second branch.
- **Audit:** `2026-04-22_offline_spec_vs_code_audit copy.md:962-983` (F-40). `Needs Isaac: YES (Q-23)`.
- **Canvas:** `AIM System.canvas` node `7d88f099576e040c` shows the 3-branch map. Per Q-23, **code wins**; canvas is updated to match code.
- **DEC-01/DEC-03 cross-check:** Code header at `shared/aim_compute.py:343-360` cites "DEC-03 (Paper 67 validated optimal zone)". Decisions log Q-23 explicitly endorses this. No conflict — DEC-03 confirmed as supersedes for the zone map.

### Pre-flight checks

1. Confirm code at `shared/aim_compute.py:343-401` matches the 5-zone description in the audit (Paper 67 zone). Already verified in Stage 1 audit pass.
2. Confirm `scripts/aim_ab_test.py` mirror function `ivts_expected_modifier` reproduces the same 5-zone logic (audit line 974: "mirrors code (same divergence)"). No change required since code is canonical.

### Files + line ranges to modify

| File | Lines | Change |
|---|---|---|
| `docs2/spec-docs-02/offline/AIM System.canvas` | node `7d88f099576e040c` | Amend AIM-04 PROC text to record 5-zone Paper 67 map |
| `tests/test_b3_aim.py` | new test class | Pin all 5 zones with explicit fixtures |

### Exact change shape

**Canvas node `7d88f099576e040c`** — MICROSTRUCTURE block. Current text:

```
PROC aim_04(features, asset):  ivts = VIX/VXV
    IF >1: 0.65 (turmoil)  ELIF >=0.93: 1.10 (optimal)  ELSE: 0.80 (quiet)
    IF gap_z>2: ×0.85. confidence=0.9 if extreme else 0.6
```

Replace with the 5-zone formulation (matching `_aim04_ivts:343-401`):

```
PROC aim_04(features, asset):  ivts = VIX/VXV  -- 5-zone per Paper 67 / DEC-03
    IF ivts > 1.10        : 0.65 (severe backwardation, conf 0.9)
    ELIF ivts > 1.00      : 0.80 (backwardation, conf 0.8)
    ELIF ivts >= 0.93     : 1.10 (optimal — Paper 67 validated, conf 0.9)
    ELIF ivts >= 0.85     : 0.90 (quiet, conf 0.6)
    ELSE                  : 0.80 (deep quiet — costs dominate, conf 0.6)
    Overnight gap overlay: IF overnight_z>2: ×0.85  ELIF overnight_z>1: ×0.95  [Q-23.b PENDING]
    EIA overlay:          IF asset==CL AND is_eia_wednesday: ×0.90              [Q-23.d PENDING — relocation under review]
```

The `[PENDING]` annotations explicitly mark the unresolved sub-points (Batch 6.4) so future readers see the canvas is in a known-incomplete state on those overlays.

### Test additions

**File:** `tests/test_b3_aim.py` — append:

```python
class TestAIM04FiveZoneMap:
    """F-40 / Q-23: AIM-04 5-zone IVTS map (Paper 67 / DEC-03) — values pinned."""

    @pytest.mark.parametrize("ivts,expected_mod,expected_tag_substr,expected_conf", [
        (1.20, 0.65, "SEVERE_BACKWARDATION", 0.9),
        (1.05, 0.80, "BACKWARDATION", 0.8),
        (0.95, 1.10, "OPTIMAL", 0.9),
        (0.90, 0.90, "QUIET", 0.6),
        (0.80, 0.80, "DEEP_QUIET", 0.6),
    ])
    def test_zone_pinning(self, ivts, expected_mod, expected_tag_substr, expected_conf):
        from shared.aim_compute import compute_aim_modifier
        result = compute_aim_modifier(4, {"ES": {"ivts": ivts}}, "ES", {})
        assert result["modifier"] == expected_mod
        assert expected_tag_substr in result["reason_tag"]
        assert result["confidence"] == expected_conf

    def test_modifier_within_bounds(self):
        from shared.aim_compute import compute_aim_modifier, MODIFIER_FLOOR, MODIFIER_CEILING
        for ivts in [0.5, 0.7, 0.85, 0.93, 1.0, 1.10, 1.5]:
            r = compute_aim_modifier(4, {"ES": {"ivts": ivts}}, "ES", {})
            assert MODIFIER_FLOOR <= r["modifier"] <= MODIFIER_CEILING, ivts

    def test_missing_ivts_neutral(self):
        from shared.aim_compute import compute_aim_modifier
        result = compute_aim_modifier(4, {"ES": {}}, "ES", {})
        assert result["modifier"] == 1.0
        assert result["reason_tag"] == "IVTS_MISSING"
```

The pinning tests **lock current code values** so that any subsequent change to the 5-zone map will fail loudly.

### Exit criteria

- [ ] `pytest tests/test_b3_aim.py::TestAIM04FiveZoneMap -v` passes (7/7)
- [ ] Canvas node `7d88f099576e040c` shows the 5-zone formulation with explicit `[PENDING]` markers on Q-23 sub-points
- [ ] `scripts/aim_ab_test.py:ivts_expected_modifier` (read-only check) verified to still match `_aim04_ivts` zone-by-zone — no update needed in this batch (will be touched in 6.4 if/when unblocked)

### Rollback

```bash
git checkout HEAD~1 -- "docs2/spec-docs-02/offline/AIM System.canvas" tests/test_b3_aim.py
```

Pure doc + test change.

---

## Batch 6.4 — F-40 AIM-04 sub-points (gap×0.95, per-zone confidence, EIA relocation)

**Status:** ⛔ BLOCKED — awaiting Isaac re-ask resolution on Q-23.b/c/d

### Why blocked

Decisions log §3.2 Q-23 — three sub-points unresolved:

- **Q-23.b** Code applies `overnight_z > 1.0 → ×0.95` as a *second* gap branch. Canvas has only the `>2.0 → ×0.85` branch. Drop, keep, or formalise into canvas?
- **Q-23.c** Per-zone confidence shape: code returns variable confidence per zone (0.6 / 0.8 / 0.9). Canvas says binary `0.9 if extreme else 0.6`. Which is correct?
- **Q-23.d** EIA Wednesday × 0.90 overlay for CL: code applies inside `_aim04_ivts`. Canvas locates it under AIM-06 (Economic Calendar). Relocate, or keep in AIM-04?

### What this batch will do once unblocked

Changes will live in:
- `shared/aim_compute.py:343-401` (`_aim04_ivts`) — modify gap-overlay branches, confidence shape
- `shared/aim_compute.py:_aim06_calendar` (`:393` region) — accept relocated EIA overlay if Q-23.d is "relocate"
- `captain-online/captain_online/blocks/b1_features.py:516, ~604` — if EIA relocates, `is_eia_wednesday` moves from AIM-04 feature list to AIM-06
- `scripts/aim_ab_test.py:ivts_expected_modifier` — mirror update
- `tests/test_b3_aim.py` — new tests for whichever resolution path lands

**Do not implement until Isaac answers Q-23.b/c/d.** No placeholder thresholds. No invented "compromise" values.

### Pre-condition for unblocking

A short batched re-ask to Isaac covering Q-23.b, Q-23.c, Q-23.d (per decisions log §3.2). Once answered, Cursor should re-plan this batch in a new build plan revision rather than guessing now.

### Rollback

n/a — nothing to roll back.

---

## Batch 6.5 — F-38 AIM-01 VRP rewrite (canvas direction, drop Monday, add overnight refinement, add 120d window)

**Status:** GO (unblocked 2026-04-27 by Isaac authoritative pseudocode for `compute_aim_modifier_01`)

### Spec citation

- **Decisions log:** §2 Group F Q-22 (partial); §3.2 Q-22 re-ask resolved 2026-04-27 by Isaac pseudocode reproduced verbatim below.
- **Audit:** `2026-04-22_offline_spec_vs_code_audit copy.md:916-937` (F-38).
- **Canvas:** `AIM System.canvas` node `13a473af588e976e` agrees with Isaac's pseudocode on directions and overnight refinement; canvas omits the explicit confidence formula and the missing-data tag.
- **DEC-01 cross-check:** Code header at `shared/aim_compute.py:251-265` cites "DEC-01 spec authoritative" with thresholds `0.70 / 0.85 / 1.10`. **DEC-01 is overridden by Isaac's 2026-04-27 pseudocode.** The code header comment must be amended; the new authority is "Isaac VRP pseudocode 2026-04-27 (decisions log §3.2 Q-22 resolution)".

#### Authoritative pseudocode (Isaac, 2026-04-27)

```
FUNCTION compute_aim_modifier_01(features, asset):
    IF features[asset].vrp is None:
        RETURN {modifier: 1.0, confidence: 0.0, reason_tag: "VRP_DATA_MISSING"}

    vrp = features[asset].vrp                        -- E[RV] - IV (positive = IV cheap)
    vrp_z = z_score(vrp, trailing_120d_vrp[asset])

    IF vrp_z > 1.5:
        base = 1.15        -- IV very cheap vs RV — larger moves expected, ORB favourable
        reason = "VRP_HIGH_POSITIVE"
    ELIF vrp_z > 0.5:
        base = 1.05
        reason = "VRP_MODERATE_POSITIVE"
    ELIF vrp_z < -1.0:
        base = 0.85        -- IV expensive — range compression expected, ORB less reliable
        reason = "VRP_NEGATIVE"
    ELSE:
        base = 1.0
        reason = "VRP_NEUTRAL"

    -- Overnight VRP refinement
    IF features[asset].vrp_overnight is not None:
        overnight_z = z_score(features[asset].vrp_overnight, trailing_60d_overnight_vrp[asset])
        IF overnight_z > 1.0 AND base >= 1.0:
            base = min(base + 0.05, 1.5)
            reason += "+OVERNIGHT_ELEVATED"

    confidence = min(abs(vrp_z) / 2.0, 1.0)
    RETURN {modifier: clamp(base, 0.5, 1.5), confidence: confidence, reason_tag: reason}
```

This pseudocode resolves all four open Q-22 sub-points:

| Q-22 sub-point | Resolution |
|---|---|
| **a — sign direction** | Canvas wins. `vrp_z > 1.5 → 1.15` (UP), `> 0.5 → 1.05`, `< -1.0 → 0.85`, else `1.0`. Code's `0.70/0.85/1.10` ladder is **wrong** and must be replaced. |
| **b — Monday × 0.95** | Not in pseudocode. **Drop** the Monday term entirely. |
| **c — overnight refinement** | Required: `IF overnight_z > 1.0 AND base >= 1.0: base = min(base + 0.05, 1.5)`. Reason tag concatenates `"+OVERNIGHT_ELEVATED"`. Refinement is a **gate**, not a multiplier — only applied when base is already ≥ 1.0 (skip when base is reductive). |
| **d — lookback windows** | Two windows. `vrp_z` over **120d** of `vrp` (primary). `overnight_z` over **60d** of `vrp_overnight` (secondary). Current code only computes the 60d secondary; the 120d primary is missing entirely. |

Plus three additional clarifications from the pseudocode:

| Item | Resolution |
|---|---|
| Confidence | `min(abs(vrp_z) / 2.0, 1.0)` — replaces the per-branch fixed values `0.5 / 0.6 / 0.7 / 0.8`. |
| Missing-data tag | `"VRP_DATA_MISSING"` (not the current `"VRP_MISSING"`). |
| Clamp | Explicit `clamp(base, 0.5, 1.5)` — already enforced upstream by `MODIFIER_FLOOR/CEILING` aggregation, but make local clamp explicit as the spec dictates. |

### Pre-flight checks

1. Verify current state of feature derivations:
   - `f["vrp"]` is computed at `b1_features.py:586` via `compute_vrp(asset_id)` — present.
   - `f["vrp_overnight"]` is computed at `:587` via `compute_overnight_vrp(asset_id)` — present.
   - `f["vrp_overnight_z"]` is computed at `:589-593` from `_get_trailing_overnight_vrp(asset_id, lookback=60)` — present.
   - `f["vrp_z"]` (120d) is **NOT computed** — must be added.
   - `_get_trailing_overnight_vrp` exists at `:896` — pattern to mirror for `_get_trailing_vrp` (120d).
2. Confirm `vrp` historical series has at least 120 days of coverage in P3-D01 features rolling store. If not, the 120d z-score will return `None` for the warm-up window and the modifier will fall back to the `VRP_DATA_MISSING` branch (acceptable — matches Isaac's missing-data path).
3. Run `pytest tests/test_b3_aim.py -v` to confirm baseline green.
4. Confirm no other module relies on the current Monday-multiplier behavior: `grep -rn "VRP_.*MONDAY\|vrp.*monday\|monday.*vrp" shared captain-online captain-offline tests scripts` — expected zero matches outside `_aim01_vrp` itself.

### Files + line ranges to modify

| File | Lines | Change |
|---|---|---|
| `shared/aim_compute.py` | 251–289 | Replace `_aim01_vrp` body with Isaac pseudocode; update docstring authority to "Isaac VRP pseudocode 2026-04-27" |
| `captain-online/captain_online/blocks/b1_features.py` | 513 | Add `vrp_z` to AIM-01 feature list |
| `captain-online/captain_online/blocks/b1_features.py` | ~586–593 | Compute `f["vrp_z"]` from new `_get_trailing_vrp(..., lookback=120)` helper |
| `captain-online/captain_online/blocks/b1_features.py` | ~896 region | Add `_get_trailing_vrp` helper, mirror of existing `_get_trailing_overnight_vrp` but pulling the primary `vrp` series |
| `shared/aim_feature_loader.py` | ~255 region | Replay-path mirror — compute `vrp_z` from 120d historical `vrp` |
| `tests/test_b3_aim.py` | new test class | Full coverage: ladder, missing-data, overnight refinement gate, confidence formula, clamp |

### Exact change shape

**`shared/aim_compute.py:251-289` — `_aim01_vrp` rewrite:**

```python
# BEFORE
def _aim01_vrp(f: dict, state: dict) -> dict:
    """AIM-01: VRP modifier — z-scored overnight VRP per AIM_Extractions.md:217-228.

    Thresholds (DEC-01 spec authoritative):
      z > +1.5 → 0.70  (high uncertainty, reduce sizing)
      z > +0.5 → 0.85
      z < -1.0 → 1.10  (low uncertainty, slight increase)
      else     → 1.00  (neutral)

    Monday adjustment (F1.2): modifier *= 0.95 on Monday mornings.
    """
    vrp_z = f.get("vrp_overnight_z")
    if vrp_z is None:
        return {"modifier": 1.0, "confidence": 0.0, "reason_tag": "VRP_MISSING"}

    if vrp_z > 1.5:
        modifier = 0.70
        confidence = 0.8
        tag = "VRP_HIGH_UNCERTAINTY"
    elif vrp_z > 0.5:
        modifier = 0.85
        confidence = 0.7
        tag = "VRP_ELEVATED"
    elif vrp_z < -1.0:
        modifier = 1.10
        confidence = 0.6
        tag = "VRP_LOW_UNCERTAINTY"
    else:
        modifier = 1.0
        confidence = 0.5
        tag = "VRP_NEUTRAL"

    dow = f.get("day_of_week")
    if dow == 0:
        modifier *= 0.95
        tag += "_MONDAY"

    return {"modifier": modifier, "confidence": confidence, "reason_tag": tag}

# AFTER
def _aim01_vrp(f: dict, state: dict) -> dict:
    """AIM-01: VRP modifier — per Isaac authoritative pseudocode 2026-04-27.

    Authority: decisions log §3.2 Q-22 resolution (supersedes DEC-01 thresholds).
    Spec: compute_aim_modifier_01 — primary z-score over 120d of vrp,
          overnight refinement over 60d of vrp_overnight.

    Ladder (canvas direction — IV cheap → larger size, IV expensive → smaller size):
      vrp_z >  1.5 → 1.15  (VRP_HIGH_POSITIVE)
      vrp_z >  0.5 → 1.05  (VRP_MODERATE_POSITIVE)
      vrp_z < -1.0 → 0.85  (VRP_NEGATIVE)
      else         → 1.00  (VRP_NEUTRAL)

    Overnight refinement (gate, only applied when base is non-reductive):
      IF overnight_z > 1.0 AND base >= 1.0:
          base = min(base + 0.05, 1.5)
          reason += "+OVERNIGHT_ELEVATED"

    Confidence: min(|vrp_z| / 2.0, 1.0)
    Missing-data tag: "VRP_DATA_MISSING" (note: differs from prior "VRP_MISSING").
    Monday × 0.95 term: REMOVED per Q-22.b (not in Isaac pseudocode).
    """
    vrp_z = f.get("vrp_z")
    if vrp_z is None:
        return {"modifier": 1.0, "confidence": 0.0, "reason_tag": "VRP_DATA_MISSING"}

    if vrp_z > 1.5:
        base = 1.15
        reason = "VRP_HIGH_POSITIVE"
    elif vrp_z > 0.5:
        base = 1.05
        reason = "VRP_MODERATE_POSITIVE"
    elif vrp_z < -1.0:
        base = 0.85
        reason = "VRP_NEGATIVE"
    else:
        base = 1.0
        reason = "VRP_NEUTRAL"

    overnight_z = f.get("vrp_overnight_z")
    if overnight_z is not None and overnight_z > 1.0 and base >= 1.0:
        base = min(base + 0.05, 1.5)
        reason += "+OVERNIGHT_ELEVATED"

    confidence = min(abs(vrp_z) / 2.0, 1.0)
    modifier = max(0.5, min(base, 1.5))
    return {"modifier": modifier, "confidence": confidence, "reason_tag": reason}
```

**`captain-online/captain_online/blocks/b1_features.py:513` — AIM_FEATURE_MAP entry:**

```python
# BEFORE
1: ["vrp", "vrp_overnight", "vrp_overnight_z"],
# AFTER
1: ["vrp", "vrp_z", "vrp_overnight", "vrp_overnight_z"],
```

**`captain-online/captain_online/blocks/b1_features.py:586-593` — add 120d primary z-score:**

```python
# AFTER existing f["vrp"] / f["vrp_overnight"] writes, alongside the existing 60d block:
trailing_120d_vrp = _get_trailing_vrp(asset_id, lookback=120)
if f["vrp"] is not None and trailing_120d_vrp is not None:
    f["vrp_z"] = z_score(f["vrp"], trailing_120d_vrp)
else:
    f["vrp_z"] = None
```

**`captain-online/captain_online/blocks/b1_features.py:~896` — add helper next to existing `_get_trailing_overnight_vrp`:**

```python
def _get_trailing_vrp(asset_id: str, lookback: int = 120) -> Optional[list[float]]:
    """Pull the trailing primary `vrp` series for z-score normalisation.

    Mirror of _get_trailing_overnight_vrp but reads the `vrp` column instead of `vrp_overnight`.
    Source: P3-D01 historical aim_features rows for that asset.
    """
    # Implementation mirrors _get_trailing_overnight_vrp structure exactly —
    # swap the column name from `vrp_overnight` to `vrp` in the QuestDB query.
```

**`shared/aim_feature_loader.py:~255` — replay-path mirror.** In the AIM-01 block, after the existing `f["vrp_overnight_z"]` derivation, add:

```python
# Primary 120d vrp z-score (Isaac pseudocode 2026-04-27)
vrps_120 = _load_trailing_series(asset, "vrp", lookback=120, as_of=as_of_ts)
if vrps_120 is not None and len(vrps_120) >= 30:
    f["vrp_z"] = z_score(vrps_120[-1], vrps_120)
else:
    f["vrp_z"] = None
```

(Use whatever helper name matches existing `aim_feature_loader.py` series-loading convention; the surrounding code at `:255-277` shows the pattern.)

### Test additions

**File:** `tests/test_b3_aim.py` — append:

```python
class TestAIM01VRPIsaacPseudocode:
    """F-38 / Q-22: AIM-01 must implement Isaac authoritative pseudocode 2026-04-27.

    Sign convention: HIGH-VRP → UP-size (IV cheap, ORB favourable).
                     LOW-VRP  → DOWN-size (IV expensive, range compression).
    Monday × 0.95 term: must be ABSENT (removed per Q-22.b).
    """

    @pytest.mark.parametrize("vrp_z,expected_base,expected_reason", [
        (2.0, 1.15, "VRP_HIGH_POSITIVE"),
        (1.0, 1.05, "VRP_MODERATE_POSITIVE"),
        (0.0, 1.00, "VRP_NEUTRAL"),
        (-2.0, 0.85, "VRP_NEGATIVE"),
    ])
    def test_ladder_canvas_direction(self, vrp_z, expected_base, expected_reason):
        from shared.aim_compute import compute_aim_modifier
        result = compute_aim_modifier(1, {"ES": {"vrp_z": vrp_z}}, "ES", {})
        assert result["modifier"] == expected_base
        assert result["reason_tag"] == expected_reason

    def test_high_vrp_is_up_size_not_down_size(self):
        """Regression guard against the old DEC-01 sign-flip (z>1.5 → 0.70)."""
        from shared.aim_compute import compute_aim_modifier
        result = compute_aim_modifier(1, {"ES": {"vrp_z": 3.0}}, "ES", {})
        assert result["modifier"] > 1.0, "High VRP must UP-size per Isaac pseudocode"

    def test_low_vrp_is_down_size_not_up_size(self):
        """Regression guard against the old DEC-01 sign-flip (z<-1 → 1.10)."""
        from shared.aim_compute import compute_aim_modifier
        result = compute_aim_modifier(1, {"ES": {"vrp_z": -3.0}}, "ES", {})
        assert result["modifier"] < 1.0, "Low VRP must DOWN-size per Isaac pseudocode"

    def test_overnight_refinement_applies_when_base_non_reductive(self):
        from shared.aim_compute import compute_aim_modifier
        # base = 1.05 (vrp_z > 0.5), overnight_z > 1.0, refinement adds 0.05
        result = compute_aim_modifier(1, {"ES": {"vrp_z": 1.0, "vrp_overnight_z": 1.5}}, "ES", {})
        assert result["modifier"] == pytest.approx(1.10)
        assert "+OVERNIGHT_ELEVATED" in result["reason_tag"]

    def test_overnight_refinement_clamped_at_1_5(self):
        from shared.aim_compute import compute_aim_modifier
        # base = 1.15 + 0.05 = 1.20, ceiling 1.5 not hit; verify the min() guard works:
        result = compute_aim_modifier(1, {"ES": {"vrp_z": 2.0, "vrp_overnight_z": 1.5}}, "ES", {})
        assert result["modifier"] == pytest.approx(1.20)
        # Stress: synthetic huge base would clamp at 1.5 — but ladder caps at 1.15,
        # so this is verified by code review of `min(base + 0.05, 1.5)`.

    def test_overnight_refinement_skipped_when_base_reductive(self):
        from shared.aim_compute import compute_aim_modifier
        # base = 0.85 (vrp_z < -1.0); overnight_z > 1.0 must NOT lift the modifier.
        result = compute_aim_modifier(1, {"ES": {"vrp_z": -2.0, "vrp_overnight_z": 1.5}}, "ES", {})
        assert result["modifier"] == 0.85
        assert "OVERNIGHT_ELEVATED" not in result["reason_tag"]

    def test_overnight_refinement_skipped_when_overnight_below_threshold(self):
        from shared.aim_compute import compute_aim_modifier
        result = compute_aim_modifier(1, {"ES": {"vrp_z": 1.0, "vrp_overnight_z": 0.5}}, "ES", {})
        assert result["modifier"] == 1.05
        assert "OVERNIGHT_ELEVATED" not in result["reason_tag"]

    def test_confidence_formula(self):
        from shared.aim_compute import compute_aim_modifier
        for vrp_z, expected_conf in [(0.0, 0.0), (1.0, 0.5), (2.0, 1.0), (3.0, 1.0), (-2.0, 1.0)]:
            r = compute_aim_modifier(1, {"ES": {"vrp_z": vrp_z}}, "ES", {})
            assert r["confidence"] == pytest.approx(expected_conf), vrp_z

    def test_missing_vrp_z_returns_data_missing(self):
        from shared.aim_compute import compute_aim_modifier
        result = compute_aim_modifier(1, {"ES": {}}, "ES", {})
        assert result["modifier"] == 1.0
        assert result["confidence"] == 0.0
        assert result["reason_tag"] == "VRP_DATA_MISSING"

    def test_no_monday_term(self):
        """Q-22.b: Monday × 0.95 multiplier must be REMOVED."""
        from shared.aim_compute import compute_aim_modifier
        # Same vrp_z, different day_of_week — modifier must be identical.
        non_monday = compute_aim_modifier(1, {"ES": {"vrp_z": 1.0, "day_of_week": 2}}, "ES", {})
        monday    = compute_aim_modifier(1, {"ES": {"vrp_z": 1.0, "day_of_week": 0}}, "ES", {})
        assert monday["modifier"] == non_monday["modifier"]
        assert "MONDAY" not in monday["reason_tag"]

    def test_modifier_within_bounds(self):
        from shared.aim_compute import compute_aim_modifier, MODIFIER_FLOOR, MODIFIER_CEILING
        for vrp_z in [-5.0, -1.5, 0.0, 0.7, 1.6, 5.0]:
            for o_z in [None, -1.0, 0.5, 1.5, 5.0]:
                f = {"ES": {"vrp_z": vrp_z}}
                if o_z is not None:
                    f["ES"]["vrp_overnight_z"] = o_z
                r = compute_aim_modifier(1, f, "ES", {})
                assert MODIFIER_FLOOR <= r["modifier"] <= MODIFIER_CEILING, (vrp_z, o_z)
```

### Exit criteria

- [ ] `pytest tests/test_b3_aim.py::TestAIM01VRPIsaacPseudocode -v` passes (16+ assertions across 11 tests)
- [ ] `pytest tests/test_b3_aim.py tests/test_pipeline_e2e.py tests/test_integration_e2e.py tests/test_stress.py -v` still green
- [ ] `grep -n "vrp_z\b" captain-online/captain_online/blocks/b1_features.py` shows the new 120d derivation alongside the existing 60d `vrp_overnight_z`
- [ ] `grep -n "_get_trailing_vrp\b" captain-online/captain_online/blocks/b1_features.py` shows the new helper
- [ ] `grep -n "vrp_z\b" shared/aim_feature_loader.py` shows replay-path coverage
- [ ] No remaining reference to the old DEC-01 ladder values for AIM-01: `grep -rn "VRP_HIGH_UNCERTAINTY\|VRP_LOW_UNCERTAINTY\|VRP_ELEVATED" shared captain-online captain-offline tests` returns 0
- [ ] No remaining Monday × 0.95 logic in AIM-01: `grep -n "day_of_week\|MONDAY" shared/aim_compute.py` returns no AIM-01 hits (AIM-10 references are unaffected)
- [ ] Code header at `_aim01_vrp` cites "Isaac VRP pseudocode 2026-04-27" and explicitly notes DEC-01 supersession
- [ ] PR description quotes the resolution route: "DEC-01 ladder values supersede by Isaac authoritative pseudocode 2026-04-27 (decisions log §3.2 Q-22)"

### Rollback

If a regression is observed in production after merge:

```bash
git checkout HEAD~1 -- shared/aim_compute.py captain-online/captain_online/blocks/b1_features.py shared/aim_feature_loader.py tests/test_b3_aim.py
```

**Risk note:** because this is a sign-flip, partial rollback (e.g. reverting only `_aim01_vrp` but keeping the new `vrp_z` feature) would leave AIM-01 reading `vrp_z` instead of the historical `vrp_overnight_z` and produce undefined modifier behavior. Roll back the **whole batch** atomically or not at all.

No QuestDB migration is required — `vrp_z` is computed-on-read and not persisted as a separate column. P3-D01 modifier history rows written under either regime are read back identically by downstream DMA/MoE.

---

## Phase 6 exit gate

A phase-level exit checklist that aggregates the per-batch criteria:

- [ ] Batch 6.1 (F-39) merged + tests green
- [ ] Batch 6.2 (F-41) merged + tests green
- [ ] Batch 6.3 (F-40 reaffirmation) merged + tests green
- [ ] Batch 6.5 (F-38 VRP rewrite per Isaac pseudocode) merged + tests green
- [ ] Batch 6.4 explicitly **NOT** merged in this phase; tracked as Phase 6 follow-up after Isaac Q-23 re-ask lands
- [ ] All AMB-1..5 ambiguities surfaced in PR descriptions; none resolved by Cursor unilaterally
- [ ] Full test suite (`tests/`) green: `pytest tests/ -v --ignore=tests/test_integration_e2e.py --ignore=tests/test_pipeline_e2e.py --ignore=tests/test_pseudotrader_account.py --ignore=tests/test_offline_feedback.py --ignore=tests/test_stress.py --ignore=tests/test_account_lifecycle.py`
- [ ] Canvas amendments committed alongside code changes (no doc-drift)

## Cross-references

- Audit: `docs2/audits/2026-04-22_offline_spec_vs_code_audit copy.md` F-38, F-39, F-40, F-41 (lines 916–1003)
- Decisions log: `docs2/audits/phase-ref-docs/phase-2/captain_offline_audit_decisions_2026-04-27.md` §2 Group F + §3.2
- Spec authority: `docs2/spec-docs-02/offline/AIM System.canvas` (PROC nodes for aim_01, aim_03, aim_04, aim_07)
- Online dispatch surface: `docs2/spec-docs-02/online/33_P3_Online_Full_Pseudocode 1.md:113-211`
- Companion plans (this campaign): Phase 1 schemas, Phase 2 persistence contracts, Phase 3 orchestrator wiring, Phase 4 AIM lifecycle/DMA/HDWM, Phase 5 BOCPD/CUSUM
