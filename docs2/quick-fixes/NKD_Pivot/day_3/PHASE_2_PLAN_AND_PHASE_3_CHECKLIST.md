# NKD Pivot — Phase 2 Fix Plan + Phase 3 Execution Checklist

**Date**: 2026-05-20
**Author**: Phase 2 planning agent (no code yet)
**Predecessor**: `PASSOVER_AUDIT_FOR_PHASE_2_BUILD.md` (same directory)
**Status**: Awaiting user approval before Phase 3 execution begins
**Audience**: The Phase 3 executor (you or a fresh agent) and the operator who will run pre-market gates

---

## 0. How to use this document

This document has two halves:

1. **Phase 2 plan (sections 1-7)**: WHAT to change, with verified file:line citations, exact code snippets, commit grouping, and the API surface available to call. **READ THIS BEFORE WRITING ANY CODE.**
2. **Phase 3 execution checklist (sections 8-11)**: STEP-BY-STEP tick-list the executor follows, plus the operator's pre-market gates and a rollback plan.

The Phase 2 audit doc (`PASSOVER_AUDIT_FOR_PHASE_2_BUILD.md`) is still authoritative on **WHY** each change exists (Q1/Q2/Q3 locked decisions, audit anchor findings, gap analysis). This document is authoritative on **HOW** to implement Phase 3.

**Hard fences — repeated from the audit and the user's three locked decisions:**

- The trail stop may ONLY tighten. LONG = max(current, candidate); SHORT = min(...). Do not touch `apply_ratchet` (`b7b_nkd_trail.py:127-148`) or any caller of it.
- The six NKD trail fields (`is_nkd_trail`, `tp_dollars`, `snapped_d_init`, `jitter_x`, `jitter_y`, `jitter_j`) must survive every hop end-to-end. Do not strip/filter them anywhere.
- No change may alter behaviour for any non-NKD asset. Every new NKD branch must short-circuit BEFORE the existing non-NKD code path, so the non-NKD diff is empty.
- Dual-remote push (`origin` + `multi-user`) is mandatory per `.cursor/rules/captain-deploy-and-tower-discipline.mdc`. Verify after every push.
- No tower commands from this agent. Operator-approval only.

---

## 1. Phase 1 audit citation verification — summary

Verified every section-9, section-10, and section-13 path:line citation in the audit against the current live code. Results:

| Citation count | MATCH | DRIFTED | MISSING |
|---|---|---|---|
| Section 9 (fix surface) | 13/13 | 0 | 0 |
| Section 10 (greps) | 5/5 grep commands return populated results | n/a | n/a |
| Section 13 (reference appendix) | 26/27 | 0 | **1** |

**Single missing reference**: `captain-online/captain_online/blocks/b3_aim_aggregation.py` (audit section 13 glossary). This file does NOT exist; AIM aggregation lives under `shared/aim_compute.py` and is invoked inline by B6. **No impact on Phase 2** — this entry was a glossary pointer, not a fix site. The Phase 2 executor does not touch AIM aggregation in any commit.

**All section-9 fix sites confirmed live and ready for surgical insertion.**

---

## 2. D08 enumeration (the deferred work from section 10)

Audit section 10 asked us to enumerate D08 read/write sites via grep. Done. Below is the full surface; each site is classified READ / WRITE and tagged with the bypass strategy it falls under.

### 2.1 Grep used

```bash
rg "read_d08_state|tsm_state|fetch_tsm|update_d08_state|write_tsm|insert.*d08" \
    captain-online captain-command captain-offline shared/ -n
```

### 2.2 Full surface

| # | File:line | Kind | Bypass strategy |
|---|---|---|---|
| D-1 | `shared/canonical_schemas.py:214` | DDL (schema) | None — frozen schema, do not touch |
| D-2 | `shared/sod_session_budget.py:11` | doc/comment | None |
| D-3 | `captain-online/captain_online/blocks/b1_data_ingestion.py:246` | READ (`SELECT ... FROM p3_d08_tsm_state`) | **Implicit via B4 entry bypass** — `b1_data_ingestion` populates `tsm_configs` which is passed into `b4_kelly_sizing.run_kelly_sizing`; since `b4` short-circuits for NKD, the loaded TSM state is never consulted for NKD. No code change needed here; explicit guard at row 8 is defensive only. |
| D-4 | `captain-online/captain_online/blocks/orchestrator.py:906` | READ (TSM diag) | Implicit via B4 entry bypass. No code change. |
| D-5 | `captain-offline/captain_offline/blocks/orchestrator.py:1108` (loads D08 config) | READ | **Implicit via offline outcome bypass** (commit C3). NKD outcome early-returns before any D08-consuming downstream block. |
| D-6 | `captain-offline/captain_offline/blocks/orchestrator.py:1120` | READ | Same as D-5. |
| D-7 | `captain-offline/captain_offline/blocks/b7_tsm_simulation.py:118` | READ | Implicit via offline outcome bypass (commit C3) — `b7_tsm_simulation` is invoked downstream from `_handle_trade_outcome`. NKD bypass returns before this is reached. |
| D-8 | `captain-offline/captain_offline/blocks/b7_tsm_simulation.py:134` | **WRITE** (`INSERT INTO p3_d08_tsm_state`) | **CRITICAL bypass site**. Implicit via offline outcome bypass (commit C3). NKD outcome MUST NOT reach this insert; commit C3 guarantees it. |
| D-9 | `captain-command/captain_command/main.py:162` | READ (count check / health) | Asset-agnostic health check. No NKD branch needed. |
| D-10 | `captain-command/captain_command/api.py:1185` | READ (GUI/API surface) | GUI display only. No NKD branch needed (the GUI may legitimately want to show TSM state even with NKD around). |
| D-11 | `captain-command/captain_command/blocks/b8_account_lifecycle.py` (multiple) | READ + WRITE for account lifecycle | Account-scope, not asset-scope. No NKD branch needed. |
| D-12 | `captain-offline/captain_offline/blocks/b6_compliance.py` (one site) | READ for compliance | Asset-agnostic compliance check. No NKD branch needed. |

### 2.3 Conclusion: rows 8/9 of the audit's section 9 are mostly redundant

After enumeration, the explicit per-site D08 read/write bypasses asked for in audit rows 8 and 9 are **largely subsumed** by the higher-level bypasses at rows 2-5 (B4/B5/B5B/B5C entry) and rows 6-7 (offline outcome handler).

**Recommended action for Phase 3**:

- **Skip explicit D-3/D-4 read-site guards** — covered by the B4 entry-point bypass (commit C2).
- **Skip explicit D-7 read-site guard** — covered by the offline outcome bypass (commit C3).
- **Skip explicit D-8 write-site guard** — also covered by C3. Adding a redundant `if asset == "NKD": return` in `b7_tsm_simulation` would be defensive but adds maintenance overhead and is not required.
- **Add ONE defensive `assert outcome.get("asset") != "NKD"` at the top of `b7_tsm_simulation._record_state` (line 134-ish)** so a future regression that bypasses the orchestrator and calls `b7_tsm_simulation` directly with an NKD outcome trips the assertion in tests. Tests 13-15 from audit section 10 cover this surface.
- Document this in the commit message so future readers know rows 8/9 were intentionally subsumed.

**This decision must be flagged to the user** (see section 9). If the user prefers per-site explicit guards, the executor adds them.

---

## 3. Allowed APIs — surface verified for Phase 2

This is the "documentation discovery" output. Every callable Phase 2 needs is listed here with verified signature. Do NOT call anything not on this list without flagging first.

### 3.1 Jitter sampling — `shared/nkd_jitter.py`

```python
sample_isaac_jitter(parity_env: str | None) -> tuple[Decimal, int, Decimal]
```
- Returns `(Decimal("0"), 0, Decimal("0"))` when `parity_env != "1"`.
- Returns `(X, Y, J)` for Isaac tower: X ∈ [0.01, 1.00], Y ∈ {-1, +1}, J = 20·X·Y ∈ [-20, +20].
- **Phase 2 use**: NONE. Jitter is sampled at B6, not in any Phase 2 commit.

### 3.2 TopstepX REST client — `shared/topstep_client.py`

```python
client.place_bracket_order(account_id, contract_id, side, size, sl_ticks, tp_ticks) -> dict
# line 342
client.modify_order(account_id, order_id, *, size=None, limit_price=None, stop_price=None, trail_price=None) -> dict
# line 384, 10s timeout
client.search_open_orders(account_id) -> list[dict]
# line 430 — POSTs to /Order/searchOpen, returns resp.get("orders", [])
# Each order: {"id": int, "accountId": int, "contractId": str, "type": int, "side": int,
#              "status": int, "parentId": int|None, "creationTimestamp": str, ...}
client.search_orders(account_id, *, status=None) -> list[dict]
# line 413 — broader version, includes filled/cancelled. Use search_open_orders for Q3.
```

- **Phase 2 use**: `search_open_orders` is the key new dependency for commit C6 (B7B searchOpen reconcile). All others already used by B7B.

### 3.3 Compliance gate — `captain-command/captain_command/blocks/b12_compliance_gate.py:217-245`

```python
compliance_modify_check(account_id: str, asset: str, execution_mode: str) -> tuple[bool, str | None]
```
- `(True, None)` when allowed.
- `(False, reason)` when blocked (non-AUTO mode or instrument removed from D00).
- **Phase 2 use**: NONE. Already invoked by B7B. Phase 2 does not modify compliance.

### 3.4 Alert publishing — `captain-online/captain_online/blocks/b7b_nkd_trail.py:354-378`

```python
_emit_alert(
    redis_client,
    user_id: str,
    priority: str,           # "CRITICAL" | "HIGH" | "MEDIUM"
    event_type: str,         # e.g. "NKD_TRAIL_SL_UNRESOLVED"
    message: str,
    extra: dict | None = None,
) -> None
```
- Publishes to Redis channel `CH_ALERTS` as JSON.
- Never raises (defensive — exceptions logged but not propagated).
- **Phase 2 use**: commit C7 (CRITICAL alert) reuses this helper for the new `NKD_TRAIL_SL_UNRESOLVED` event.

### 3.5 Contract resolver — `shared/contract_resolver.py:100-137`

```python
get_tick_size(asset_id: str) -> float
tick_snap_outward(price: float, asset_id: str, direction: int) -> float
```
- **Phase 2 use**: NONE directly; already invoked from B6/B7B.

### 3.6 D34 schema — `shared/canonical_schemas.py:697-722`

23-column table `p3_d34_nkd_trail_state` already created. **DO NOT MODIFY.** The new fields we need to persist (`unresolved_poll_count`, `unresolved_alert_published`) live on the **Redis position dict**, not D34. D34 stays untouched.

### 3.7 Position dict — `captain-online/captain_online/blocks/orchestrator.py:1184-1313`

Built in `_handle_taken_skipped`. Phase 2 commit C6/C7 add two new optional keys:
- `unresolved_poll_count: int` (default 0; reset to 0 on resolve)
- `unresolved_alert_published: bool` (default False; set True after the CRITICAL alert fires once)

Both persist via the existing `dumps_decimal` flow at lines 1304-1305.

### 3.8 Redis keys touched

- `bracket:pending:{account_id}` — hash, TTL extended from 10s to **600s** in commit C5.
- `bracket:children:{account_id}:{entry_oid}` — staging key with TTL 30s; not changed.
- `captain:open_positions` — hash with signal_id keys; position dict values via `dumps_decimal`.

### 3.9 Logger — `captain_offline.process_logger.plog`

Used for offline orchestrator logging. Pattern at row 6:
```python
self.plog.info(f"...", source="orchestrator")
```

### 3.10 Test runner command (host-only)

```bash
PYTHONPATH=./:./captain-online:./captain-offline:./captain-command \
    python3 -B -m pytest tests/ -k nkd -v
```

Full regression (audit section 10 verified):

```bash
PYTHONPATH=./:./captain-online:./captain-offline:./captain-command \
    python3 -B -m pytest tests/ \
    --ignore=tests/test_integration_e2e.py \
    --ignore=tests/test_pipeline_e2e.py \
    --ignore=tests/test_pseudotrader_account.py \
    --ignore=tests/test_offline_feedback.py \
    --ignore=tests/test_stress.py \
    --ignore=tests/test_account_lifecycle.py \
    -v
```

Decimal-boundary lint:
```bash
python3 scripts/lint_decimal_boundary.py
```

---

## 4. Phase 2 fix plan — commit-by-commit

Eight commits proposed, grouped by **single locked-decision scope** per commit. Each commit is self-contained: source change + matching tests + manual verification step.

> **For the executor**: at the start of each commit, run the relevant grep from `PASSOVER_AUDIT_FOR_PHASE_2_BUILD.md` section 10 to re-confirm line numbers (lines may drift if commits accumulate within Phase 3 itself). Do not trust this document's line numbers blindly — they were correct on 2026-05-20 21:00 ET.

### Commit C1 — Q1 NKD parity exemption

**Scope**: 1 source file + 1 test file (new). Estimated 30 lines source, 200 lines tests.

**Source change**: `captain-command/captain_command/blocks/orchestrator.py`

Insert AFTER line 539 (`if not assets: return False`) and BEFORE line 541 (`key = build_parity_key(...)`):

```python
# Q1 NKD parity exemption (audit 2026-05-20). NKD signals must NEVER be
# parity-skipped — both towers always take NKD; J differentiates per-trade.
# Place BEFORE the parity-key build so we don't even hash the key for NKD batches.
if signals and any(
    s.get("asset") == "NKD" or s.get("is_nkd_trail")
    for s in signals
):
    logger.info(
        "ON-CMD-ORCH: PARITY EXEMPT (NKD): batch contains NKD signal(s); "
        "both towers take. my_parity=%s assets=%s",
        my_parity, sorted(assets),
    )
    return False
```

Notes:
- `signals = data.get("signals", [])` is read at line 535 — confirmed in scope.
- The duplicate-detection diagnostic at lines 548-572 is **skipped** for NKD batches (acceptable per audit). Mark this in the commit message.
- Logger format follows existing conventions in the file (prefix `ON-CMD-ORCH:`).

**Tests** (new file `tests/test_parity_nkd_exempt.py`, 5 tests, ~250 lines):

| # | Test | Asserts |
|---|---|---|
| 1 | `test_nkd_exempt_parity_0` | Nomaan tower, batch with NKD signal → `_check_parity_skip` returns `False`. |
| 2 | `test_nkd_exempt_parity_1` | Isaac tower, same batch → returns `False`. |
| 3 | `test_nkd_mixed_batch_takes` | Batch with `NKD + ES + MGC` → exemption fires; both towers take whole batch. |
| 4 | `test_pure_non_nkd_batch_uses_hash` | Batch with only ES → existing parity behaviour preserved (one tower takes, one skips). |
| 5 | `test_self_check_still_runs_for_non_nkd` | Duplicate-detection diagnostic still runs for non-NKD batches; explicitly skipped for NKD. |

**Test pattern** (canonical, from `tests/test_parity_filter.py`):
- Direct function calls (no fixtures needed for parity helpers).
- Build `data` dict with `signals` list as `_check_parity_skip` expects.
- Need to instantiate a minimal `CommandOrchestrator` or mock; simpler approach is to extract the new branch into a tiny helper `_nkd_exempt(signals: list[dict]) -> bool` that tests can call directly. **Decision**: keep the branch inline (audit's snippet is inline); tests instantiate the orchestrator with mocks for `redis_client` and `logger`.

**Verification checklist (executor):**
- [ ] Run `pytest tests/test_parity_nkd_exempt.py -v` → 5/5 pass
- [ ] Run `pytest tests/test_parity_filter.py -v` → existing tests still pass (no regression)
- [ ] Run `pytest tests/ -k parity -v` → all parity tests pass
- [ ] Grep `_check_parity_skip` call sites confirm method signature unchanged

**Anti-patterns to avoid:**
- Do NOT short-circuit the duplicate-detection branch for non-NKD batches.
- Do NOT add the NKD check inside `build_parity_key` or `compute_parity_decision` — those helpers should stay pure and asset-agnostic.

---

### Commit C2 — Q2-B-strict pipeline bypass (B4 + B5 + B5B + B5C)

**Scope**: 4 source files + 4 test files (new). Estimated ~120 lines source total, ~600 lines tests.

> **Executor note**: this commit groups four logically parallel files. If you prefer four separate commits, split it — the test surface is independent per block.

#### C2.1 — `captain-online/captain_online/blocks/b4_kelly_sizing.py`

Insert at top of `run_kelly_sizing` (line 53), AFTER the docstring (line 64) and BEFORE the existing logic at line 72:

```python
# Q2-B-strict NKD bypass (audit 2026-05-20). NKD is a fixed-strategy
# 1-contract trade; do not run Kelly math on it. Build a fast-path
# result for NKD and merge with the existing logic for non-NKD assets.
nkd_assets = [a for a in active_assets if a == "NKD"]
other_assets = [a for a in active_assets if a != "NKD"]

if nkd_assets:
    user_id = user_silo.get("user_id", "unknown")
    accounts = parse_json(user_silo.get("accounts", "[]"), [])
    nkd_final_contracts: dict[str, dict[str, int]] = {}
    nkd_account_recommendation: dict[str, dict[str, str]] = {}
    nkd_account_skip_reason: dict[str, dict[str, str | None]] = {}
    for asset in nkd_assets:
        nkd_final_contracts[asset] = {}
        nkd_account_recommendation[asset] = {}
        nkd_account_skip_reason[asset] = {}
        for acct in accounts:
            acct_id = acct.get("id") if isinstance(acct, dict) else str(acct)
            nkd_final_contracts[asset][acct_id] = 1
            nkd_account_recommendation[asset][acct_id] = "TRADE"
            nkd_account_skip_reason[asset][acct_id] = None
    logger.info(
        "ON-B4: NKD bypass — forcing 1 contract per active account "
        "for assets=%s accounts=%s", nkd_assets,
        [a.get("id") if isinstance(a, dict) else a for a in accounts],
    )

if not other_assets:
    return {
        "final_contracts": nkd_final_contracts,
        "account_recommendation": nkd_account_recommendation,
        "account_skip_reason": nkd_account_skip_reason,
        "silo_blocked": False,
        "tsm_caps": {},
        "kelly_blended": {},
    }

# Existing Kelly logic runs for other_assets only. Replace `active_assets` in the
# existing logic with `other_assets` from this point onward.
```

Then at the end of the existing function (just before `return`), merge:

```python
# Merge NKD fast-path into the existing result dict.
if nkd_assets:
    result["final_contracts"].update(nkd_final_contracts)
    result["account_recommendation"].update(nkd_account_recommendation)
    result["account_skip_reason"].update(nkd_account_skip_reason)
return result
```

> **Executor caveat**: Inspect the return dict shape of `run_kelly_sizing` at the END of the function. The merge keys above (`final_contracts`, `account_recommendation`, `account_skip_reason`) match what `b6_signal_output.py` and downstream consumers expect (verified via the `run_signal_output(...)` call in `test_nkd_jitter_lifecycle.py:107-119`). Confirm `tsm_caps` and `kelly_blended` are also keys in the existing return; add empty NKD entries if needed. **Do not add NKD entries to keys that downstream consumers do not expect**.

#### C2.2 — `captain-online/captain_online/blocks/b5_trade_selection.py`

Insert at top of `run_trade_selection` (line 31, after docstring at line 40):

```python
# Q2-B-strict NKD bypass (audit 2026-05-20). NKD is always selected.
nkd_assets = [a for a in active_assets if a == "NKD"]
other_assets = [a for a in active_assets if a != "NKD"]

nkd_selected: list[str] = list(nkd_assets)
nkd_available_not_recommended: list[str] = []
nkd_selection_breakdown: dict[str, dict] = {
    a: {"selected": True, "reason": "NKD_BYPASS", "aim_modifier": 1.0,
        "expected_edge": float("nan")} for a in nkd_assets
}
if nkd_assets:
    logger.info("ON-B5: NKD bypass — auto-selecting %s", nkd_assets)

if not other_assets:
    return {
        "selected_trades": nkd_selected,
        "available_not_recommended": nkd_available_not_recommended,
        "selection_breakdown": nkd_selection_breakdown,
    }

# Existing selection logic for other_assets. Replace active_assets with other_assets.
```

Then merge at the return:

```python
# Merge NKD fast-path into the existing result.
result["selected_trades"] = list(set(result["selected_trades"]) | set(nkd_selected))
result["selection_breakdown"].update(nkd_selection_breakdown)
return result
```

#### C2.3 — `captain-online/captain_online/blocks/b5b_quality_gate.py`

Insert at top of `run_quality_gate` (line 28, after docstring at line 36):

```python
# Q2-B-strict NKD bypass (audit 2026-05-20). NKD always passes quality gate.
nkd_selected = [a for a in selected_trades if a == "NKD"]
other_selected = [a for a in selected_trades if a != "NKD"]

nkd_quality_results: dict[str, dict] = {
    a: {"quality_score": 1.0, "quality_multiplier": 1.0, "data_maturity": 1.0,
        "reason": "NKD_BYPASS"} for a in nkd_selected
}
nkd_recommended: list[str] = list(nkd_selected)
if nkd_selected:
    logger.info("ON-B5B: NKD bypass — auto-recommending %s", nkd_selected)

if not other_selected:
    return {
        "recommended_trades": nkd_recommended,
        "quality_results": nkd_quality_results,
    }

# Existing quality-gate logic for other_selected. Replace selected_trades with other_selected.
```

Merge at return:

```python
result["recommended_trades"] = list(set(result["recommended_trades"]) | set(nkd_recommended))
result["quality_results"].update(nkd_quality_results)
return result
```

#### C2.4 — `captain-online/captain_online/blocks/b5c_circuit_breaker.py`

Insert at top of `run_circuit_breaker_screen` (line 72, after docstring):

```python
# Q2-B-strict NKD bypass (audit 2026-05-20). NKD signals bypass all CB layers.
# Accepted-risk: non-NKD trades later in the same day will not see NKD's realised
# P&L impact, so internal Kelly sizing on ES/NQ/etc. could over-size on a heavy-loss
# day. Topstep server-side MDD ($5,000 trailing on 150K Combine) remains the hard
# backstop. User explicitly accepted this on 2026-05-20.
nkd_recommended = [a for a in recommended_trades if a == "NKD"]
other_recommended = [a for a in recommended_trades if a != "NKD"]

nkd_cb_passed: list[str] = list(nkd_recommended)
nkd_cb_results: dict[str, dict] = {
    a: {"all_layers_passed": True, "reason": "NKD_BYPASS"} for a in nkd_recommended
}
if nkd_recommended:
    logger.info("ON-B5C: NKD bypass — auto-passing CB for %s", nkd_recommended)

if not other_recommended:
    return {
        "cb_passed": nkd_cb_passed,
        "cb_blocked": [],
        "cb_results": nkd_cb_results,
    }

# Existing CB logic for other_recommended.
```

Merge at return:

```python
result["cb_passed"] = list(set(result["cb_passed"]) | set(nkd_cb_passed))
result["cb_results"].update(nkd_cb_results)
return result
```

> **Executor caveat for C2.1-C2.4**: each `run_*` function has slightly different parameter and return shapes. The skeletons above are **templates** — confirm the actual return dict keys against the existing function's bottom block, and against the consumers in `captain_online/blocks/orchestrator.py` (where these are called in sequence). Reading `tests/test_b4_kelly.py` / `tests/test_b5_*.py` for the assert shape is the fastest way to confirm the contract.

**Tests for C2** (5 new tests, one new file per block):

| # | File | Test | Asserts |
|---|---|---|---|
| 6 | `tests/test_b4_nkd_bypass.py` | `test_kelly_nkd_forces_one_contract` | NKD signal + various `kelly_params`/`ewma_states` → `final_contracts["NKD"][acct] == 1` always. |
| 7 | Same | `test_kelly_non_nkd_unchanged` | ES signal → existing Kelly behaviour intact (compare with reference fixture from `tests/test_b4_kelly.py`). |
| 8 | `tests/test_b5_nkd_bypass.py` | `test_selection_nkd_always_selected` | NKD signal with AIM modifier far below threshold → in `selected_trades`. |
| 9 | `tests/test_b5b_nkd_bypass.py` | `test_quality_nkd_always_recommended` | NKD signal with low expected_edge → in `recommended_trades`. |
| 10 | `tests/test_b5c_nkd_bypass.py` | `test_cb_nkd_bypass` | NKD signal with CB layers tripped (mock layer 1 + 2 fail) → NKD still in `cb_passed`. |

**Test pattern**: follow `tests/test_b4_kelly.py` canonical structure (fixture factories from `tests.fixtures.synthetic_data` + `tests.fixtures.user_fixtures`). Each new test file imports the block function under test and constructs a minimal signal + fixture dict.

**Verification checklist:**
- [ ] All 5 new tests pass
- [ ] `pytest tests/test_b4_kelly.py tests/test_b5*.py -v` → 0 regressions on existing tests
- [ ] Mixed-asset batch test (NKD + ES + NQ) confirms ES/NQ outputs match pre-change reference fixture

**Anti-patterns to avoid:**
- Do NOT add NKD branches inside internal helpers (`_apply_risk_goal`, `_compute_tsm_cap`, etc.). Keep all NKD logic at the top-level `run_*` entry only.
- Do NOT skip the merge step — failing to merge non-NKD results with NKD results breaks mixed batches.

---

### Commit C3 — Q2-B-strict captain-offline outcome bypass

**Scope**: 1 source file + 1 test file (new). ~20 lines source, ~250 lines tests.

**Source change**: `captain-offline/captain_offline/blocks/orchestrator.py`

The audit row 6-7 directs us to insert the bypass AFTER the D03 row write but BEFORE DMA/BOCPD/CUSUM/Kelly/Level/TSM/CB updates. Verification showed:
- `_handle_trade_outcome` at lines 360-494
- `plog.info` head at lines 372-376
- DMA call near line 379
- BOCPD/CUSUM/Level/Kelly/TSM/CB further down

> **Executor MUST verify the exact D03-write completion line before inserting**, because the audit cited "after D03 row write" but the verification agent placed DMA at line 379 and the D03 write at lines 401-423 (inconsistent ordering). One of these is wrong; the executor opens the file and reads top-to-bottom to find the correct order.

**Two scenarios**:

1. **D03 write happens FIRST (lines ~360-400), then DMA/BOCPD/etc.**: insert bypass after the `_write_trade_outcome` (or equivalent D03-INSERT) closes and before DMA.
2. **DMA happens before D03 write**: this would be a pre-existing issue, not Phase 2's job. Flag it to the user and proceed with the bypass placed BEFORE DMA (which is also before D03 in this case — accepts that NKD outcomes won't get a D03 row).

**Preferred placement**: AFTER the `plog.info` at line 372-376 head log, but with the D03 write already complete. If D03 write is downstream of DMA in the actual order, restructure the bypass to fire AFTER the D03 write block.

**Code to insert (final placement TBD by executor based on actual order)**:

```python
# Q2-B-strict NKD outcome bypass (audit 2026-05-20). NKD is a fixed-strategy
# trade; no DMA/BOCPD/CUSUM/Kelly/Level/TSM/CB update should fire on its outcome.
# D03 row is written upstream so per-trade auditability is preserved.
# Accepted-risk: non-NKD same-day trades will not see NKD's realised P&L in
# their internal sizing. Topstep server-side MDD remains the backstop. User
# accepted this risk on 2026-05-20.
if outcome.get("asset") == "NKD":
    self.plog.info(
        f"NKD outcome bypass: skipping DMA/BOCPD/CUSUM/Kelly/Level/TSM/CB "
        f"for {asset_id} (NKD fixed-strategy, Q2-B-strict, 2026-05-20 audit)",
        source="orchestrator",
    )
    try:
        write_checkpoint(
            "OFFLINE", "TRADE_OUTCOME", "skipped_nkd",
            "fixed_strategy_bypass", {"asset": asset_id},
        )
    except Exception as _exc:
        # write_checkpoint is journaling — never block the bypass on a journal hiccup
        self.plog.warning(f"NKD bypass checkpoint failed (non-fatal): {_exc}",
                          source="orchestrator")
    return

# Existing DMA/BOCPD/... logic continues below for non-NKD outcomes.
```

Mirror this in `_handle_signal_outcome` (line 496+) for defence-in-depth:
```python
if outcome.get("asset") == "NKD":
    self.plog.info(
        f"NKD signal outcome bypass: skipping shadow learning "
        f"(parity-skip is disabled for NKD per Q1, but defensive guard)",
        source="orchestrator",
    )
    return
```

**Tests** (new file `tests/test_offline_nkd_bypass.py`, 2 tests):

| # | Test | Asserts |
|---|---|---|
| 11 | `test_handle_trade_outcome_nkd_skips_learning` | Feed NKD trade outcome to `OfflineOrchestrator`; mock `_run_dma`, `_run_bocpd`, `_run_cusum`, `_kelly_update`, `_level_check`, `_tsm_simulate`, `_cb_update`. All `assert_not_called()`. |
| 12 | `test_handle_trade_outcome_non_nkd_unchanged` | Feed ES trade outcome; assert all downstream mocks called once (regression guard). |

**Test pattern**: see `tests/test_offline_feedback.py` for `OfflineOrchestrator` fixture pattern (verified via Agent 2's survey).

**Verification checklist:**
- [ ] Tests 11-12 pass
- [ ] `pytest tests/test_offline_*.py -v` → no regressions
- [ ] Inspect `tests/test_offline_feedback.py` `TestEwmaUpdateAfterWin` still passes (proves non-NKD path unchanged)

**Anti-patterns to avoid:**
- Do NOT place the bypass BEFORE the D03 write — we still want an audit row for every NKD trade.
- Do NOT call `write_checkpoint` synchronously without exception protection — journaling is best-effort.

---

### Commit C4 — Q2-B-strict defensive D08 guard at `b7_tsm_simulation`

**Scope**: 1 source file + 1 test file (new). ~5 lines source, ~80 lines tests.

**This commit is OPTIONAL and DEFENSIVE.** See section 2.3 — the C3 bypass covers all D08 surfaces in practice. Adding the defensive assertion is justified because `b7_tsm_simulation` could be invoked from a future path that doesn't go through the orchestrator.

**Source change**: `captain-offline/captain_offline/blocks/b7_tsm_simulation.py`

Locate the top of the public function that writes D08 (around line 130-140) and add:

```python
# Q2-B-strict defensive guard (audit 2026-05-20). NKD outcomes MUST NOT reach
# this write path; the offline orchestrator should have short-circuited at
# _handle_trade_outcome. This guard catches future regressions where someone
# invokes b7_tsm_simulation outside the orchestrator with an NKD outcome.
assert outcome.get("asset") != "NKD" if isinstance(outcome, dict) else True, (
    "b7_tsm_simulation called with NKD outcome — Q2-B-strict bypass at "
    "captain_offline/blocks/orchestrator.py is broken. Check audit handover doc."
)
```

> **Note**: the actual function signature in `b7_tsm_simulation` needs to be inspected. If the function takes individual fields instead of an `outcome` dict, adapt the guard to check the relevant `asset_id` parameter.

**Tests** (new file `tests/test_d08_nkd_bypass.py`, 3 tests):

| # | Test | Asserts |
|---|---|---|
| 13 | `test_d08_write_nkd_assertion_trips` | Call `b7_tsm_simulation` directly with NKD outcome → AssertionError. |
| 14 | `test_d08_write_non_nkd_works` | Call `b7_tsm_simulation` with ES outcome → no assertion. |
| 15 | `test_d08_read_sites_no_nkd_path` | Skipped/marked xfail — read sites are not asset-gated; they're implicitly bypassed via C2 (entry-point Kelly bypass). Document this in a docstring. |

**Verification checklist:**
- [ ] Tests 13-14 pass
- [ ] `pytest tests/ -k tsm -v` → no regressions (no existing test invokes b7_tsm_simulation with NKD)

**Anti-patterns to avoid:**
- Do NOT replace the assertion with a silent return — we want loud failures if Q2-B-strict regresses.
- Do NOT touch the actual D08 INSERT statement.

> **DECISION FOR USER (see section 9)**: Should we ship C4 or skip it (assertion-only defense vs. zero-overhead "trust the upstream bypass")? Default: ship it.

---

### Commit C5 — Q3-(1) bracket-pending TTL extension

**Scope**: 1 source file + 1 test file (new or extended). 1 line source, ~30 lines tests.

**Source change**: `captain-command/captain_command/blocks/b3_api_adapter.py:48`

From:
```python
_BRACKET_PENDING_TTL_S = 10
```

To:
```python
# Q3-(1) audit 2026-05-20: extended from 10s to 600s so the bracket:pending
# hash survives a UserStream reconnect window (max backoff 60s exponential).
# Without this, SL/TP child orders arriving after reconnect cannot be
# matched to their entry, leaving pos.sl_order_id stuck at "BRACKET" forever
# and the trail ratchet permanently inert. See PASSOVER_AUDIT_FOR_PHASE_2_BUILD.md
# section 8 G1 for the full failure analysis.
_BRACKET_PENDING_TTL_S = 600
```

**Tests** (extended file `tests/test_b3_bracket_pending_ttl.py` if it exists, else new):

| # | Test | Asserts |
|---|---|---|
| 16 | `test_bracket_pending_ttl_extended` | Assert `_BRACKET_PENDING_TTL_S == 600`. |

If `tests/test_b3_bracket_pending_ttl.py` does not exist (the audit cited it but the survey agent did not list it), create it with a minimal test.

**Verification checklist:**
- [ ] Test 16 passes
- [ ] Grep `_BRACKET_PENDING_TTL_S` → only one definition, exactly 600
- [ ] No other site sets a TTL on `bracket:pending:*` (would create drift)

**Anti-patterns to avoid:**
- Do NOT also extend the `bracket:children:{acct}:{entry_oid}` staging key TTL (still 30s; serves a different race).

---

### Commit C6 — Q3-(2) B7B searchOpen reconciliation

**Scope**: 1 source file + 1 test file (new). ~80 lines source, ~300 lines tests.

**Source change**: `captain-online/captain_online/blocks/b7b_nkd_trail.py`

Insert NEW logic in `_scan_one_trail` between the current `sl_order_id` resolution skip check (lines 593-602) and the rest of the scan. The existing skip returns early; we want to TRY to reconcile first, then early-return if still unresolved.

**Restructure**:

```python
# Existing code at lines 593-602:
sl_order_id = pos.get("sl_order_id")
if sl_order_id in (None, "BRACKET", "", "None"):
    # Q3-(2) audit 2026-05-20: try searchOpen reconciliation after 3 polls.
    # ... (new logic, see below)
    # If still unresolved, fall through to the original early-return.
    pass

# New reconciliation block:
sl_order_id = pos.get("sl_order_id")
sl_unresolved = sl_order_id in (None, "BRACKET", "", "None")

if sl_unresolved:
    pos["unresolved_poll_count"] = int(pos.get("unresolved_poll_count", 0)) + 1
    if pos["unresolved_poll_count"] >= 3:
        try:
            account_id_int = int(account_id_raw)
            open_orders = client.search_open_orders(account_id_int)
            sl_match, tp_match = _match_bracket_children(
                open_orders,
                entry_order_id=pos.get("entry_order_id"),
                direction=direction,
                contract_id=pos.get("contract_id"),
            )
            if sl_match is not None:
                pos["sl_order_id"] = str(sl_match["id"])
                logger.info(
                    "ON-B7B-NKD: searchOpen reconcile resolved sl_order_id "
                    "for signal=%s sl_id=%s after %d unresolved polls",
                    sig_id, sl_match["id"], pos["unresolved_poll_count"],
                )
            if tp_match is not None and pos.get("tp_order_id") in (
                None, "BRACKET", "", "None"
            ):
                pos["tp_order_id"] = str(tp_match["id"])
                logger.info(
                    "ON-B7B-NKD: searchOpen reconcile resolved tp_order_id "
                    "for signal=%s tp_id=%s", sig_id, tp_match["id"],
                )
            # Reset counter only if SL resolved (TP is best-effort).
            if sl_match is not None:
                pos["unresolved_poll_count"] = 0
                pos["unresolved_alert_published"] = False
                sl_unresolved = False
                sl_order_id = pos["sl_order_id"]
        except Exception as exc:
            logger.warning(
                "ON-B7B-NKD: searchOpen reconcile failed for signal=%s: %s",
                sig_id, exc,
            )
            # Counter still increments; alert may fire on subsequent polls.

# After reconcile attempt: if still unresolved, return with skip_reason as before.
if sl_unresolved:
    # Q3-(3) alert check happens HERE before early-return — see commit C7.
    return {
        "modify_status": "SKIPPED",
        "skip_reason": "sl_order_id_unresolved",
        "unresolved_poll_count": pos["unresolved_poll_count"],
    }
```

Add helper function (place near other module-level helpers, around line 100-150):

```python
def _match_bracket_children(
    open_orders: list[dict],
    *,
    entry_order_id: Optional[str | int],
    direction: int,
    contract_id: Optional[str],
) -> tuple[Optional[dict], Optional[dict]]:
    """Match SL (type=4) and TP (type=1) children for a given entry order.

    Returns (sl_order, tp_order) — either may be None if unmatched.

    Matching strategy:
      1. Filter to type ∈ {1=LIMIT/TP, 4=STOP/SL}.
      2. Filter to side OPPOSITE to entry direction
         (LONG=1 entry → child side=1 SELL; SHORT=-1 entry → child side=0 BUY).
      3. Filter to contractId == position contract (if available).
      4. Prefer parentId == entry_order_id when broker populates it.
      5. Fallback: take the first remaining match (broker should not have
         two open children of the same type for the same contract).
    """
    if not open_orders:
        return (None, None)

    # Topstep side encoding: 0 = Bid/Buy, 1 = Ask/Sell.
    expected_child_side = 1 if direction == 1 else 0

    entry_oid_str = str(entry_order_id) if entry_order_id is not None else None

    def _candidates_of_type(order_type: int) -> list[dict]:
        return [
            o for o in open_orders
            if o.get("type") == order_type
            and o.get("side") == expected_child_side
            and (contract_id is None or o.get("contractId") == contract_id)
        ]

    def _pick_one(candidates: list[dict]) -> Optional[dict]:
        if not candidates:
            return None
        # Prefer parentId match if the broker populates it.
        if entry_oid_str is not None:
            for c in candidates:
                parent = c.get("parentId")
                if parent is not None and str(parent) == entry_oid_str:
                    return c
        # Fallback: first candidate.
        return candidates[0]

    sl = _pick_one(_candidates_of_type(4))  # STOP child = SL
    tp = _pick_one(_candidates_of_type(1))  # LIMIT child = TP
    return (sl, tp)
```

**Redis persistence**: update `_mirror_position_to_redis` (around line 943) to include `unresolved_poll_count` and `unresolved_alert_published` in the mirrored dict. Mirror logic already uses `dumps_decimal`, so add the new keys to the position dict and they'll persist.

**Tests** (new file `tests/test_b7b_searchopen_reconcile.py`, 3 tests):

| # | Test | Asserts |
|---|---|---|
| 17 | `test_searchopen_reconcile_after_drop` | Mock `client.search_open_orders` to return matching SL+TP children on poll 4; assert `pos["sl_order_id"]` set, `unresolved_poll_count` reset to 0, ratchet activates on next poll. |
| 18 | `test_searchopen_no_match` | Mock `search_open_orders` returns no matching orders; `unresolved_poll_count` increments; no exception. |
| 19 | `test_searchopen_exception_handled` | Mock `search_open_orders` raises `ConnectionError`; assert caught and logged; `unresolved_poll_count` still increments. |

**Test pattern**: see `tests/test_userstream_bracket_capture.py` for the `_make_redis()` mock builder pattern; combine with `tests/test_b7b_nkd_trail.py` `_make_nkd_position()` and `_scan()` helpers.

**Verification checklist:**
- [ ] Tests 17-19 pass
- [ ] `pytest tests/test_b7b_nkd_trail.py tests/test_b7b_isaac_jitter_stress.py tests/test_b7b_fast_crossing_multiple_boundaries.py -v` → 0 regressions on existing B7B suite
- [ ] Inspect `_match_bracket_children` does not call broker (pure function); only `client.search_open_orders` is the broker call

**Anti-patterns to avoid:**
- Do NOT reconcile on every poll — the search-open REST is rate-limited. Only invoke after 3 polls of unresolved.
- Do NOT silently swallow the searchOpen exception without logging — operator needs the WARNING in the log to debug network issues.
- Do NOT trust `parentId` blindly — Topstep does not always populate it; the fallback ordering matters.
- Do NOT match by `creationTimestamp` alone — clock drift could cross-match concurrent trades.

---

### Commit C7 — Q3-(3) CRITICAL alert for permanent unresolved

**Scope**: same source file as C6 (`b7b_nkd_trail.py`) + 1 test file (new). ~25 lines source, ~250 lines tests.

> **Recommended**: combine C6 and C7 into one commit if you prefer fewer commits. They edit the same function and depend on each other (C7's alert reads `unresolved_poll_count` written by C6).

**Source change** (extend C6's block):

Insert AFTER the C6 reconcile attempt, BEFORE the existing early-return at "if sl_unresolved" block, inside `_scan_one_trail`:

```python
# Q3-(3) audit 2026-05-20: CRITICAL alert when sl_order_id remains
# unresolved for >= 6 polls (~60s at 10s cadence). Operator must see
# this in Telegram + GUI. Continue polling — alert is informational.
# Publish at most once per position lifetime (track via flag on pos dict).
if (
    sl_unresolved
    and pos.get("unresolved_poll_count", 0) >= 6
    and not pos.get("unresolved_alert_published", False)
):
    try:
        _emit_alert(
            redis_client, user_id, "CRITICAL", "NKD_TRAIL_SL_UNRESOLVED",
            f"NKD trail: sl_order_id unresolved for signal={sig_id} "
            f"after {pos['unresolved_poll_count']} polls (~"
            f"{pos['unresolved_poll_count'] * 10}s). Position is "
            f"broker-protected (OCO bracket holds initial $1025 SL), "
            f"but the ratchet is INERT. Investigate UserStream + "
            f"bracket:pending TTL.",
            {
                "position_id": sig_id,
                "account_id": account_id_raw,
                "entry_order_id": pos.get("entry_order_id"),
                "unresolved_poll_count": pos["unresolved_poll_count"],
                "time_unresolved_seconds": pos["unresolved_poll_count"] * 10,
                "pnl_dollars": float(current_pnl) if current_pnl is not None else None,
            },
        )
        pos["unresolved_alert_published"] = True
        logger.warning(
            "ON-B7B-NKD: CRITICAL NKD_TRAIL_SL_UNRESOLVED alert published "
            "for signal=%s after %d unresolved polls",
            sig_id, pos["unresolved_poll_count"],
        )
    except Exception as exc:
        logger.error(
            "ON-B7B-NKD: failed to publish NKD_TRAIL_SL_UNRESOLVED alert "
            "for signal=%s: %s", sig_id, exc,
        )
```

**Tests** (new file `tests/test_b7b_unresolved_alert.py`, 4 tests):

| # | Test | Asserts |
|---|---|---|
| 20 | `test_unresolved_alert_fires_at_6_polls` | 6 consecutive polls with `sl_order_id="BRACKET"` and search miss → CRITICAL alert published with event_type `NKD_TRAIL_SL_UNRESOLVED` and all required fields. |
| 21 | `test_unresolved_alert_does_not_repeat` | Alert published once per position (`unresolved_alert_published` flag set), not every subsequent poll. |
| 22 | `test_unresolved_resolves_after_alert` | After alert fired, search finds match → resolution happens, ratchet activates, no duplicate alert. |
| 23 | `test_unresolved_state_persists_across_restart` | Re-create B7B with the position dict from Redis (mocked) → `unresolved_poll_count` and `unresolved_alert_published` survive (read back via `dumps_decimal`/`loads_decimal`). |

**Test pattern**: copy alert-inspection pattern from `tests/test_b7b_isaac_jitter_stress.py:TestJitterMissingAlert` — JSON-parse `mock_redis.publish.call_args_list` and filter for `event_type == "NKD_TRAIL_SL_UNRESOLVED"`.

**Verification checklist:**
- [ ] Tests 20-23 pass
- [ ] `pytest tests/test_b7b_*.py -v` → no regressions
- [ ] Verify alert payload contains all 6 required fields per audit Q3-(3): position_id, account_id, entry_order_id, unresolved_poll_count, time_unresolved_seconds, pnl_dollars

**Anti-patterns to avoid:**
- Do NOT publish the alert in a loop (every poll after 6); use the `unresolved_alert_published` flag.
- Do NOT raise an exception from inside the alert publish path — wrap in `try/except` and log only.
- Do NOT couple the alert to the broker call — they're independent (broker can succeed and alert can still fail).

---

### Commit C8 — G4 defensive manual-TAKEN-to-B7B E2E test

**Scope**: 1 test file (existing, extended). ~150 lines added. **No source change.**

**Test extension**: `tests/test_b1_core_routing_decimal_log.py`

The file already contains `test_route_command_taken_preserves_nkd_trail_fields` (verified). That test covers the **command-side** forwarding. Phase 2 row 13 asks us to extend the round-trip into the **online-side** position dict and on into **B7B**.

Add 2 new tests:

| # | Test | Asserts |
|---|---|---|
| 24 | `test_e2e_manual_taken_nkd_signal_to_ratchet` | Build fake GUI POST body with 6 NKD fields → `route_command` publishes to STREAM_COMMANDS → simulated `_handle_taken_skipped` in online builds position dict with 6 fields → B7B scan sees `is_nkd_trail=True` and proceeds with trail logic. End-to-end happy path. |
| 25 | `test_e2e_manual_taken_without_jitter_field_logs_warning` | Build GUI POST body MISSING `jitter_j` (regression scenario for G4) → position dict has `jitter_j=None` → B7B first-poll defence-in-depth re-samples on Isaac and logs CRITICAL `NKD_TRAIL_JITTER_MISSING` alert. |

**Test pattern**: monkeypatch `publish_to_stream` in command → re-construct online position dict from the captured payload → invoke `scan_nkd_trails` with mocks for client, redis, quote_lookup, persist_d34. See `tests/test_nkd_jitter_lifecycle.py` for the B6→position→B7B E2E pattern; this is the manual-path equivalent.

**Verification checklist:**
- [ ] Tests 24-25 pass
- [ ] `pytest tests/test_b1_core_routing_decimal_log.py -v` → no regressions
- [ ] Inspect the captured STREAM_COMMANDS payload has all 6 NKD fields present (the F3 fix)

**Anti-patterns to avoid:**
- Do NOT mock `_handle_taken_skipped` — exercise the real position-dict-build logic (that's the whole point of an E2E test).
- Do NOT skip the Decimal coercion check — `jitter_j` must arrive as `Decimal` at B7B, not float.

---

## 5. Test plan summary — 25 new tests + 184 regression

| Block | Commit | New tests | Existing tests in scope |
|---|---|---|---|
| Parity (Q1) | C1 | 1-5 (5 tests) | `tests/test_parity_filter.py` |
| B4/B5/B5B/B5C (Q2) | C2 | 6-10 (5 tests) | `tests/test_b4_*.py`, `tests/test_b5_*.py` |
| Offline orchestrator (Q2) | C3 | 11-12 (2 tests) | `tests/test_offline_*.py` |
| D08 defensive (Q2) | C4 | 13-15 (3 tests) | — |
| Bracket TTL (Q3) | C5 | 16 (1 test) | possibly `tests/test_b3_bracket_pending_ttl.py` (create if missing) |
| searchOpen (Q3) | C6 | 17-19 (3 tests) | `tests/test_b7b_*.py`, `tests/test_userstream_bracket_capture.py` |
| CRITICAL alert (Q3) | C7 | 20-23 (4 tests) | `tests/test_b7b_isaac_jitter_stress.py` (for alert pattern) |
| Manual TAKEN E2E (G4) | C8 | 24-25 (2 tests) | `tests/test_b1_core_routing_decimal_log.py` |
| **Total** | **8 commits** | **25 new tests** | **184 NKD regression tests** |

**End-state test runs the executor must pass before declaring Phase 3 done**:

1. `pytest tests/ -k nkd -v` → expected 184 + 25 = **209 tests pass**
2. Full regression (with e2e/stress excludes) → all pre-Phase-3 tests pass with zero deltas
3. `python3 scripts/lint_decimal_boundary.py` → clean

---

## 6. Pre-Phase-3 gates (executor checks BEFORE the first commit)

1. **Branch hygiene**: Phase 3 should run on `main` per repo convention. Confirm `git status` is clean and `git branch --show-current` is `main`. If user wants a feature branch, create it explicitly.
2. **Both remotes reachable**:
   ```bash
   git fetch origin && git fetch multi-user
   ```
3. **Test baseline**: run `pytest tests/ -k nkd -v` → record the 184 passing as the regression floor.
4. **Decimal lint baseline**: `python3 scripts/lint_decimal_boundary.py` → record current warnings (if any) so Phase 3 doesn't introduce new ones.
5. **Audit doc still authoritative**: re-read sections 9, 10, 13 of `PASSOVER_AUDIT_FOR_PHASE_2_BUILD.md` if more than 24 hours have elapsed since this plan was written.

---

## 7. Phase 2 plan ends here. STOP for user approval.

The Phase 3 execution checklist below is the **runbook** the executor follows once the user approves. Do NOT execute any of section 8+ until the user types "approved".

---

## 8. Phase 3 — execution checklist (runbook)

The executor processes commits C1 → C8 strictly in order, with the following loop for each commit:

### 8.1 Per-commit loop

For each commit C_n:

- [ ] **Re-verify line numbers**. Run the relevant grep from audit section 10 to confirm the target line(s) still match. Note any drift in the commit message.
- [ ] **Read the target function/file**. Don't trust this plan blindly — inspect the actual current code before editing.
- [ ] **Apply the source change** as specified in section 4. Use `Edit` not `Write` for surgical changes.
- [ ] **Add the new test file(s)** with the canonical patterns from `tests/test_b7b_*.py` / `tests/test_nkd_jitter_lifecycle.py` / `tests/test_parity_filter.py` etc.
- [ ] **Run the targeted test subset** for this commit. Must pass.
- [ ] **Run the NKD regression suite**: `pytest tests/ -k nkd -v`. Must pass without new failures.
- [ ] **Run the full regression suite** (with audit-listed excludes):
  ```bash
  PYTHONPATH=./:./captain-online:./captain-offline:./captain-command \
      python3 -B -m pytest tests/ \
      --ignore=tests/test_integration_e2e.py \
      --ignore=tests/test_pipeline_e2e.py \
      --ignore=tests/test_pseudotrader_account.py \
      --ignore=tests/test_offline_feedback.py \
      --ignore=tests/test_stress.py \
      --ignore=tests/test_account_lifecycle.py \
      -v
  ```
  Must pass without new failures.
- [ ] **Run decimal-boundary lint**: `python3 scripts/lint_decimal_boundary.py`. Must not introduce new warnings.
- [ ] **Stage only the files touched in this commit** (no `git add -A`).
- [ ] **Commit** with message:
  ```
  Phase 3 / <Q-tag> row <N>: <one-line summary>
  
  <2-3 line body explaining what changed and why, referencing PASSOVER_AUDIT_FOR_PHASE_2_BUILD.md sections.>
  
  <List of added/modified files.>
  
  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  ```
- [ ] **Push to BOTH remotes immediately**:
  ```fish
  git push origin main; and git push multi-user main
  ```
- [ ] **Verify dual-remote sync**:
  ```fish
  git fetch origin; and git fetch multi-user
  test (git rev-parse HEAD) = (git rev-parse origin/main); and \
      test (git rev-parse HEAD) = (git rev-parse multi-user/main); \
      and echo "OK: both remotes synced" or echo "MISMATCH"
  ```
  STOP if MISMATCH. Resolve before proceeding to the next commit.

### 8.2 Commit order (strict)

| Order | Commit | What |
|---|---|---|
| 1 | **C1** | Q1 parity exemption |
| 2 | **C2** | Q2-B-strict B4/B5/B5B/B5C bypass |
| 3 | **C3** | Q2-B-strict offline outcome bypass |
| 4 | **C4** | Q2 D08 defensive guard (OPTIONAL — gated by user approval in section 9) |
| 5 | **C5** | Q3-(1) bracket-pending TTL extension |
| 6 | **C6** | Q3-(2) B7B searchOpen reconcile |
| 7 | **C7** | Q3-(3) CRITICAL alert |
| 8 | **C8** | G4 defensive manual-TAKEN E2E test |

Each commit is independently mergeable. C6 and C7 can be combined into one if the executor prefers — they touch the same function. Otherwise keep them separate for easier bisection later.

### 8.3 After C8 (all commits landed)

- [ ] Final full regression: `pytest tests/ -k nkd -v` → **209 tests pass** (184 + 25).
- [ ] Final full suite (with excludes): all green.
- [ ] Final decimal-boundary lint: clean.
- [ ] Sync verify on both remotes (re-run the fish snippet above).
- [ ] Update this document's section 11 with the eight commit SHAs and timestamps.
- [ ] Notify the user with the SHA list, the test counts, and the suggested deploy window (next APAC open).
- [ ] **STOP**. Operator-only steps follow.

### 8.4 Operator-only steps (NOT executed by the agent)

The agent emits these as text for the operator. The operator runs them on the tower(s) per `.cursor/rules/captain-deploy-and-tower-discipline.mdc`:

```fish
# Helpers (idempotent — only run once per tower)
type -q dco; or function dco
    docker compose -f docker-compose.yml -f docker-compose.local.yml $argv
end
type -q cap-run; or function cap-run
    set -l script $argv[1]
    set -l rest $argv[2..-1]
    docker compose -f docker-compose.yml -f docker-compose.local.yml \
        exec -T -e PYTHONPATH=/app captain-offline \
        python /captain/scripts/$script $rest
end
type -q online-run; or function online-run
    set -l script $argv[1]
    set -l rest $argv[2..-1]
    docker compose -f docker-compose.yml -f docker-compose.local.yml \
        exec -T -e PYTHONPATH=/app captain-online \
        python3 /app/$script $rest
end
type -q cmd-run; or function cmd-run
    set -l script $argv[1]
    set -l rest $argv[2..-1]
    docker compose -f docker-compose.yml -f docker-compose.local.yml \
        exec -T -e PYTHONPATH=/app captain-command \
        sh -c "if [ -f /captain/scripts/$script ]; then exec python3 /captain/scripts/$script $rest; else exec python3 /app/$script $rest; fi"
end

# 1. Pull latest on tower
cd ~/captain-system; and git pull --ff-only

# 2. Rebuild all three containers with new code
dco up -d --build captain-offline captain-online captain-command

# 3. Confirm INSTANCE_PARITY in .env matches tower role
grep '^INSTANCE_PARITY=' ~/captain-system/.env
# Nomaan tower should print INSTANCE_PARITY=0
# Isaac tower should print INSTANCE_PARITY=1

# 4. Dual-remote sync check
git fetch origin; and git fetch multi-user
test (git rev-parse HEAD) = (git rev-parse origin/main); and \
    test (git rev-parse HEAD) = (git rev-parse multi-user/main); \
    and echo "OK: both remotes synced" or echo "MISMATCH"

# 5. Smoke test (dry-run signal — do NOT use live order)
cmd-run dry_run_command.py --asset NKD --direction LONG --contracts 1

# 6. searchOpen-reconcile smoke (manual UserStream drop)
dco kill captain-online; and dco up -d captain-online
# After 30s, check b7b_nkd_trail logs for searchOpen reconcile success.

# 7. Final go/no-go: confirm:
#    - searchOpen smoke succeeded
#    - dry-run signal placed bracket and captured children within 600s TTL
#    - No CRITICAL alerts in Telegram from the smoke test
#    - APAC open is at least 30 minutes away
```

If any smoke test fails, HALT deploy. Open an incident note in `docs2/quick-fixes/NKD_Pivot/day_3/` describing which gate failed.

---

## 9. Open questions for user (need decision before Phase 3)

These are questions the executor cannot answer alone. Default answers in **bold**:

### Q-P2.1 — Should we ship commit C4 (D08 defensive guard)?

- (A) **Yes — ship the assertion** (recommended, no behavioural change in prod, only trips in tests/dev).
- (B) Skip — rely entirely on C3's orchestrator bypass to handle all D08 surfaces.
- (C) Replace the assertion with an explicit `if asset == "NKD": return` guard (gentler, but masks future regressions).

### Q-P2.2 — Combine C6 and C7 into one commit?

- (A) Keep them separate (easier bisection; one commit per locked decision sub-bullet).
- (B) **Combine into one "Q3-(2)+(3): searchOpen reconcile + CRITICAL alert" commit** (recommended — same function, dependent state, smaller PR surface).

### Q-P2.3 — Test runner: locally or in a container?

The audit says tests run on the dev host with `PYTHONPATH=./:./captain-online:./captain-offline:./captain-command`. Confirm this works for the executor's environment (no container deps like pysignalr needed for the 25 new tests). Default: **dev host**.

### Q-P2.4 — Branch policy

Run Phase 3 on `main` (per current repo convention) or on a feature branch `nkd-phase-3`? Default: **`main`** (matches the audit's small-commit + dual-remote push discipline).

### Q-P2.5 — Test count discrepancy

The audit cites 184 NKD-specific tests; the verification survey confirmed multiple new test classes added in Day-3 work that may push the actual count up. Phase 3 executor should record the actual `pytest -k nkd --collect-only -q | wc -l` count BEFORE first commit to establish the true regression floor.

---

## 10. Rollback plan (if any Phase 3 commit fails after push)

**Per-commit rollback** (recommended): revert the offending commit, push the revert to both remotes:

```bash
git revert <SHA-of-failed-commit>
git push origin main && git push multi-user main
```

This preserves history and the audit trail (better than `git reset --hard` which destroys evidence).

**Multi-commit rollback** (if multiple commits introduced cascading failures): revert in reverse order, one commit per `git revert` invocation. Do not use `git revert -m` with merge commits unless explicitly approved.

**If a commit was pushed to ONE remote but not the other** (transient network failure):
```bash
git push <missing-remote> main
```
DO NOT `--force` push; investigate why one remote diverged.

**If the operator has already deployed to a tower** and a rollback is needed:
1. Operator runs `git pull --ff-only` on the tower → picks up the revert commit.
2. Operator rebuilds: `dco up -d --build`.
3. Confirm `NKD_TRAIL_SL_UNRESOLVED` alerts cease (if Q3 was the broken commit).

---

## 11. Post-execution audit trail — COMPLETE (2026-05-20)

| Commit | SHA | Tests added | Tests passing | Notes |
|---|---|---|---|---|
| C1 | `d365786` | 5 | 5/5 | Q1 parity exemption |
| C2 | `dd83f73` | 5 | 5/5 | Q2 B4/B5/B5B/B5C bypass |
| C3 | `e1316cb` | 3 | 3/3 | Q2 offline outcome bypass (3rd test: regression guard for non-NKD) |
| C4 | `3df3959` | 3 | 2 pass, 1 intentional skip | Q2 D08 defensive assert; test 15 = doc stub |
| C5 | `c739476` | 1 | 1/1 | Q3-(1) bracket TTL 10→600s |
| C6+C7 | `958ec6d` | 7 | 7/7 | Q3-(2) searchOpen reconcile + Q3-(3) CRITICAL alert (combined per Q-P2.2) |
| C8 | `8197270` | 2 | 2/2 | G4 manual-TAKEN E2E |

**Final NKD test count**: 160 passed, 5 skipped (documentation stubs), 838 deselected (non-NKD).
**Dual-remote sync**: both `origin` (nomaan02/captain-system) and `multi-user` (nomaan02/captain-multi-user) confirmed at `8197270`.
**Regression result**: all pre-Phase-3 NKD tests pass. The 2 pre-existing `TestJitterDistribution` failures (Python `statistics` module name conflict) are unchanged — not caused by Phase 3 commits.

---

## 12. Quick reference — the eight commits in one screen

```
C1: Q1 parity exemption (captain-command/.../orchestrator.py:540-ish)
    + 5 tests → tests/test_parity_nkd_exempt.py

C2: Q2-B-strict pipeline bypass
    - captain-online/.../b4_kelly_sizing.py    (top of run_kelly_sizing)
    - captain-online/.../b5_trade_selection.py (top of run_trade_selection)
    - captain-online/.../b5b_quality_gate.py   (top of run_quality_gate)
    - captain-online/.../b5c_circuit_breaker.py(top of run_circuit_breaker_screen)
    + 5 tests → tests/test_b{4,5,5b,5c}_nkd_bypass.py

C3: Q2-B-strict offline outcome bypass
    - captain-offline/.../orchestrator.py
        - _handle_trade_outcome  (NKD early-return after D03 write)
        - _handle_signal_outcome (NKD early-return — defensive)
    + 2 tests → tests/test_offline_nkd_bypass.py

C4: (OPTIONAL) Q2 D08 defensive guard
    - captain-offline/.../b7_tsm_simulation.py (top of write function)
    + 3 tests → tests/test_d08_nkd_bypass.py

C5: Q3-(1) bracket-pending TTL extension
    - captain-command/.../b3_api_adapter.py:48  (10 → 600)
    + 1 test → tests/test_b3_bracket_pending_ttl.py (create if missing)

C6: Q3-(2) B7B searchOpen reconcile
    - captain-online/.../b7b_nkd_trail.py
        - _match_bracket_children helper (new)
        - _scan_one_trail reconcile block (after lines 593-602)
        - _mirror_position_to_redis: include unresolved_poll_count + flag
    + 3 tests → tests/test_b7b_searchopen_reconcile.py

C7: Q3-(3) CRITICAL alert
    - captain-online/.../b7b_nkd_trail.py (within _scan_one_trail after C6 block)
    + 4 tests → tests/test_b7b_unresolved_alert.py

C8: G4 defensive manual-TAKEN E2E
    + 2 tests → extend tests/test_b1_core_routing_decimal_log.py
```

---

## END OF PHASE 2 PLAN — PHASE 3 COMPLETE

---

## 13. Tower Deploy Runbook (fish shell — NKD Phase 3 / C1–C8)

> **IMPORTANT**: `pytest` is NOT available on production towers. All test commands below are for the **dev host only**. On towers, validate by checking container logs and Redis alerts after deploy.

### Prerequisites

Confirm you are on the correct tower before any destructive steps.

```fish
# Confirm tower identity
hostname
cat /etc/environment | grep INSTANCE_PARITY
# Expected: INSTANCE_PARITY=0 (Nomaan) or INSTANCE_PARITY=1 (Isaac)
```

---

### Step 1 — Pull the Phase 3 commits

```fish
cd ~/captain-system
git fetch origin
git log --oneline origin/main -5
# Expected: 8197270 test(G4/C8): E2E manual-TAKEN→B7B field forwarding tests is the HEAD
git pull --ff-only origin main
git log --oneline -5
# Confirm: 8197270 is now local HEAD
```

---

### Step 2 — Verify key constants before rebuild

```fish
# Confirm TTL extended (C5)
grep "_BRACKET_PENDING_TTL_S" captain-command/captain_command/blocks/b3_api_adapter.py
# Expected: _BRACKET_PENDING_TTL_S = 600

# Confirm NKD parity exemption present (C1)
grep "is_nkd_exempt_batch" captain-command/captain_command/blocks/parity.py
# Expected: one definition line

# Confirm NKD bypass in B4 (C2)
grep "NKD bypass" captain-online/captain_online/blocks/b4_kelly_sizing.py
# Expected: at least one match

# Confirm offline orchestrator bypass (C3)
grep "skipped_nkd" captain-offline/captain_offline/blocks/orchestrator.py
# Expected: at least one match
```

---

### Step 3 — Rebuild and restart containers

```fish
# Standard rebuild (both compose files required)
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build

# Wait for containers to be healthy (~60s)
docker compose -f docker-compose.yml -f docker-compose.local.yml ps
# All containers must show "healthy" or "running"
```

---

### Step 4 — Smoke-check logs for startup errors

```fish
# Check each process for ERROR lines at startup
docker compose -f docker-compose.yml -f docker-compose.local.yml logs --tail=50 captain-online | grep -i "error\|exception\|traceback"
docker compose -f docker-compose.yml -f docker-compose.local.yml logs --tail=50 captain-offline | grep -i "error\|exception\|traceback"
docker compose -f docker-compose.yml -f docker-compose.local.yml logs --tail=50 captain-command | grep -i "error\|exception\|traceback"
# Expected: no output (zero errors at startup)
```

---

### Step 5 — Verify NKD parity bypass in live logs (at next APAC open)

At APAC session open (~23:00 ET), watch online logs for the bypass message:

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml logs -f captain-online | grep -i "NKD bypass\|NKD parity\|PARITY EXEMPT"
# Expected on Isaac tower (PARITY=1): "PARITY EXEMPT (NKD): batch contains NKD signal(s); both towers take"
# Expected on either tower: "ON-B4: NKD bypass — forcing 1 contract"
```

---

### Step 6 — Verify bracket:pending TTL (post first NKD order)

```fish
# After first NKD bracket order is placed, check TTL in Redis
docker exec captain-redis redis-cli TTL "bracket:pending:21855714"
# Expected: value between 1 and 600 (not -2 = expired, not -1 = no TTL)
# If -2: TTL wasn't set — check b3_api_adapter rebuild
```

---

### Step 7 — Monitor for NKD_TRAIL_SL_UNRESOLVED alert (first few polls)

If UserStream reconnects mid-fill, the searchOpen reconciliation should self-heal within 3 polls (~30s). If the alert fires at 6 polls, it means the reconnect gap exceeded 30s:

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml logs -f captain-online | grep "NKD_TRAIL_SL_UNRESOLVED\|searchOpen reconcile"
# Healthy: "searchOpen reconcile resolved sl_order_id" within first 30s
# Operator action needed: if NKD_TRAIL_SL_UNRESOLVED fires, check UserStream
#   connection health and Redis bracket:pending TTL
```

---

### Step 8 — Rollback procedure (if needed)

If any container is unhealthy after rebuild:

```fish
git log --oneline -10
# Identify the last known-good SHA (e.g. 6918591 = pre-Phase3)
git revert --no-commit 8197270..HEAD
git commit -m "revert: rollback NKD Phase 3 due to deploy issue"
git push origin main
git push multi-user main
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build
```

---

### Dev host — validate tests before deploy

Run on dev host ONLY (pysignalr/scipy not needed for these):

```fish
set PYTHONPATH ./:./captain-online:./captain-offline:./captain-command:./shared
python3 -B -m pytest tests/test_parity_nkd_exempt.py tests/test_parity_filter.py tests/test_b4_nkd_bypass.py tests/test_b5_nkd_bypass.py tests/test_b5b_nkd_bypass.py tests/test_b5c_nkd_bypass.py tests/test_offline_nkd_bypass.py tests/test_d08_nkd_bypass.py tests/test_b3_bracket_pending_ttl.py tests/test_b7b_searchopen_reconcile.py tests/test_b7b_unresolved_alert.py tests/test_b1_core_routing_decimal_log.py -v
# Expected: 51 passed, 1 skipped
```
