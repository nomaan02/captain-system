# NKD Pivot — Day 1 Completion Checklist

**Generated:** 2026-05-19  
**Source plan:** [`docs2/quick-fixes/NKD_Pivot/day_1/PLAN.md`](../day_1/PLAN.md)  
**Isaac spec (locked):** memory entries #3343, #3342 — confirmed 2026-05-19

---

## Isaac's confirmed spec (supercedes the original day-1 plan in §1 DEC-3/DEC-8 and §5 phase math)

| Parameter | Confirmed value |
|---|---|
| Initial SL (`D_init`) | **$1,025 fixed** for every NKD trade |
| Phase A buffer ($0 → $2,000 profit) | $1,025 (hold at `D_init`) |
| Phase B buffer ($2,000 → $3,000 profit) | **$1,000 flat step** |
| Phase C buffer ($3,000 → $4,450 profit) | **$450 flat step** |
| TP target | $4,450 (broker LIMIT) |
| Jitter J (Isaac tower, `INSTANCE_PARITY=="1"`) | One signed J per trade, `|J| ∈ [0.2, 20.0]`, added in **dollars** to BOTH the SL buffer AND the TP target at broker-order time. Phase boundaries ($2,000 / $3,000 / $4,450) stay clean. |
| Non-NKD assets | No change to SL/TP logic |

---

## C1–C13 status table

> **Status legend:**
> - `DONE` — implementation exactly matches the day-1 plan intent; no further action needed
> - `DONE (spec delta)` — code is landed and working, but deviates from Isaac's confirmed spec; amendment required (see Day-2 plan)
> - `DONE (script, not yet run)` — code/script exists; requires explicit operator approval + manual execution on tower
> - `FILE EXISTS` — test/script file created; may need assertion updates due to spec deltas

| Commit | Day-1 plan intent | Status | Evidence (file:line) | Isaac-spec delta | Verification command |
|---|---|---|---|---|---|
| **C1** | M048 migration + `p3_d34_nkd_trail_state` DDL in `canonical_schemas.py` | **DONE** | [`shared/canonical_schemas.py:696`](../../../../shared/canonical_schemas.py) — `D34_NKD_TRAIL_STATE` constant; [`shared/canonical_schemas.py:861`](../../../../shared/canonical_schemas.py) — listed in `CANONICAL_DDLS`; [`shared/canonical_schemas.py:1085-1091`](../../../../shared/canonical_schemas.py) — migration entry `M048_create_d34_nkd_trail_state` | None | `curl -s -G "http://127.0.0.1:9000/exec" --data-urlencode "query=SHOW TABLES" \| grep p3_d34` |
| **C2** | `tick_snap_outward(price, asset_id, direction)` helper in `shared/contract_resolver.py` | **DONE** | [`shared/contract_resolver.py:109-137`](../../../../shared/contract_resolver.py) — function defined; unit tests at [`tests/test_tick_snap_outward.py`](../../../../tests/test_tick_snap_outward.py) — 9 test cases covering long/short/aligned/precision/invalid | None | `pytest tests/test_tick_snap_outward.py -v` |
| **C3** | `_tp_from_dollars` helper in B6; `_compute_tp` short-circuits on `tp_dollars` key | **DONE (spec delta)** | [`b6_signal_output.py:278-302`](../../../../captain-online/captain_online/blocks/b6_signal_output.py) — `_tp_from_dollars` defined; [`b6_signal_output.py:324-327`](../../../../captain-online/captain_online/blocks/b6_signal_output.py) — `_compute_tp` branch. TP currently placed at exactly `$4,450` for all towers | **C16 required:** on Isaac tower the TP dollar target passed to `_tp_from_dollars` must become `4450 + J`. Currently there is no jitter path into B6. | `grep -n "tp_dollars" captain-online/captain_online/blocks/b6_signal_output.py` |
| **C4** | NKD `locked_strategy` JSON gains `tp_dollars`, `is_nkd_trail`, `trail_step_dollars`, `trail_phase_b_start_dollars`, `trail_phase_c_start_dollars`, `trail_phase_c_buffer_dollars` | **DONE (spec delta)** | [`scripts/bootstrap_production.py:48-51`](../../../../scripts/bootstrap_production.py) — `tp_dollars: 4450, is_nkd_trail: True, trail_step_dollars: 500, trail_phase_b_start_dollars: 1500, trail_phase_c_start_dollars: 4000, trail_phase_c_buffer_dollars: 450`; forwarding loop at [`bootstrap_production.py:118-127`](../../../../scripts/bootstrap_production.py) | **C15 required:** `trail_phase_b_start_dollars` should be `2000` (not `1500`); `trail_phase_c_start_dollars` should be `3000` (not `4000`); add `sl_dollars_fixed: 1025`; add `trail_phase_b_buffer_dollars: 1000` | `cmd-run bootstrap_production.py` then QuestDB query: `SELECT locked_strategy FROM p3_d00_asset_universe WHERE asset_id='NKD' LATEST ON last_updated PARTITION BY asset_id` |
| **C5** | R1 UserStream bracket-child capture: B3 pushes `bracket:pending:{account_id}`; `_on_order_update` matches children; `_handle_taken_skipped` consumes staged race result | **DONE** | [`b3_api_adapter.py:60-68`](../../../../captain-command/captain_command/blocks/b3_api_adapter.py) — `bracket:pending` push logic; [`captain-online/main.py:180-289`](../../../../captain-online/captain_online/main.py) — `_match_bracket_child` function; [`online/orchestrator.py:1260-1290`](../../../../captain-online/captain_online/blocks/orchestrator.py) — TAKEN consumer reads `bracket:children`; tests at [`tests/test_userstream_bracket_capture.py`](../../../../tests/test_userstream_bracket_capture.py) | None | After first NKD trade: `dco logs captain-online \| grep "Bracket child captured"` |
| **C6** | Thread `is_nkd_trail`, `tp_dollars`, `snapped_d_init` through B6 → Command → Online position dict; extend position dict with trail-state nulls | **DONE (spec delta)** | B6 at [`b6_signal_output.py:138-152`](../../../../captain-online/captain_online/blocks/b6_signal_output.py) — builds `nkd_trail_fields`; Command at [`command/orchestrator.py:701-704`](../../../../captain-command/captain_command/blocks/orchestrator.py) — forwards fields; Online at [`online/orchestrator.py:1232-1244`](../../../../captain-online/captain_online/blocks/orchestrator.py) — extends position dict with `is_nkd_trail`, `tp_dollars`, `snapped_d_init`, `jitter_*`, `current_*`, `modify_seq` | **C15 required:** B6 currently computes `snapped_d_init = abs(entry - sl_level) * point_value` at [`b6_signal_output.py:145`](../../../../captain-online/captain_online/blocks/b6_signal_output.py) — this produces the OR-range-derived dollar distance, NOT $1,025. Must become a fixed `1025` (or `strategy.get("sl_dollars_fixed", 1025)`) | `redis-cli hgetall captain:open_positions \| grep snapped_d_init` after NKD position opens |
| **C7** | New `b7b_nkd_trail.py`: phase math (A/B/C/TP_HIT), ratchet, Isaac jitter, D34 persistence, `modify_order` dispatch | **DONE (spec delta)** | [`b7b_nkd_trail.py`](../../../../captain-online/captain_online/blocks/b7b_nkd_trail.py) — 1015-line module; phase math at lines 123-179; jitter sampler at 89-120; ratchet at 182-203; scan entry at 510-611; called from online orchestrator after `monitor_positions` | **C14 required (phase math):** `_PHASE_B_START_BASE_DOLLARS = 1500` (line 69) → should be `2000`; linear taper (lines 160-174) → should be discrete `$1,000` step buffer; `_PHASE_C_START_BASE_DOLLARS = 4000` → should be `3000`. **C16 required (jitter surface):** jitter J currently only shifts phase-boundary thresholds (lines 154-155); docstring lines 99-104 explicitly calls broker-price application "forbidden". Must invert: J should be added to the dollar buffer SENT to the broker, and to the TP target. | `pytest tests/test_b7b_nkd_trail.py -v` |
| **C8** | `compliance_modify_check(account_id, asset, execution_mode)` wrapper in `b12_compliance_gate.py`; trail block calls it before every `modify_order` | **DONE** | [`b12_compliance_gate.py:217-245`](../../../../captain-command/captain_command/blocks/b12_compliance_gate.py) — `compliance_modify_check` defined; wired into trail block at [`b7b_nkd_trail.py:260-276`](../../../../captain-online/captain_online/blocks/b7b_nkd_trail.py) (import) and line 805 (call site); tests at [`tests/test_b12_compliance_modify_check.py`](../../../../tests/test_b12_compliance_modify_check.py) | None | `pytest tests/test_b12_compliance_modify_check.py -v` |
| **C9** | TIME_EXIT NKD exemption in `b7_position_monitor.py`: skip the force-flatten branch when `asset=="NKD"` or `is_nkd_trail==True` | **DONE** | [`b7_position_monitor.py:316-319`](../../../../captain-online/captain_online/blocks/b7_position_monitor.py) — exemption in place (checks both `asset=="NKD"` and `is_nkd_trail`); tests at [`tests/test_b7_time_exit_nkd_exemption.py`](../../../../tests/test_b7_time_exit_nkd_exemption.py) | None | `pytest tests/test_b7_time_exit_nkd_exemption.py -v` |
| **C10** | `is_subscribed()` getter on `MarketStream`; `ensure_nkd_subscribed()` in `captain-online/main.py`; called from `scan_nkd_trails` every poll | **DONE** | [`shared/topstep_stream.py:318`](../../../../shared/topstep_stream.py) — `is_subscribed` getter; [`captain-online/main.py:46-72`](../../../../captain-online/captain_online/main.py) — `ensure_nkd_subscribed` defined + module-level export comment; [`b7b_nkd_trail.py:577-581`](../../../../captain-online/captain_online/blocks/b7b_nkd_trail.py) — call site; tests at [`tests/test_marketstream_nkd_persistence.py`](../../../../tests/test_marketstream_nkd_persistence.py) | None | `dco logs captain-online \| grep "NKD contract.*not in MarketStream"` (expect silence if subscription is retained) |
| **C11** | GUI panel columns: `current_phase`, `current_buffer`, `current_stop_price`, `jitter_j`, `modify_seq`; block-registry entry for `b7b_nkd_trail` | **DONE** | [`b2_gui_data_server.py:467-471`](../../../../captain-command/captain_command/blocks/b2_gui_data_server.py) — all five fields projected; [`captain-gui/src/constants/blockRegistry.js:14`](../../../../captain-gui/src/constants/blockRegistry.js) — `b7b_nkd_trail` entry | None (cosmetic: Phase B label "linear buffer" may change to "$1,000 step" after C14) | Open Trade panel, confirm phase/buffer/stop columns render |
| **C12** | `scripts/nkd_pivot_d26_override.py` + test; sets D26 `opportunity_weights={NY:0.10, LON:0.10, APAC:0.80}` | **DONE (script, not yet run)** | [`scripts/nkd_pivot_d26_override.py`](../../../../scripts/nkd_pivot_d26_override.py) — full script with dry-run support; weights literal at line 12; QuestDB insert at lines 124-139; verification at lines 141-148; tests at [`tests/test_nkd_pivot_d26_override.py`](../../../../tests/test_nkd_pivot_d26_override.py). **Not yet executed on any tower — requires explicit operator approval** | None | After operator approval + execution: `curl -s -G "http://127.0.0.1:9000/exec" --data-urlencode "query=SELECT opportunity_weights, cold_start, n_observations FROM p3_d26_hmm_opportunity_state LATEST ON last_updated"` — expect `{NY:0.10, LON:0.10, APAC:0.80}`, `cold_start=false`, `n_observations=60` |
| **C13** | Replay test `tests/test_nkd_replay_22h.py` against 2026-05-13 22h NKD trade | **FILE EXISTS (spec delta)** | [`tests/test_nkd_replay_22h.py`](../../../../tests/test_nkd_replay_22h.py) — file exists | **Post-C14/C15/C16:** assertions for Phase B must switch from linear-taper expectations to `$1,000` flat step; assertions for D_init must be `$1,025` (fixed) not OR-range derived; jitter-on-broker-prices assertions must be added for Isaac-tower fixture after C16 | `pytest tests/test_nkd_replay_22h.py -v` |

---

## Summary

| Category | Count | Commits |
|---|---|---|
| Fully DONE — no action needed | 7 | C1, C2, C5, C8, C9, C10, C11 |
| DONE with spec delta — amendment required | 4 | C3, C4, C6, C7 |
| Script exists but NOT YET RUN — operator approval gate | 1 | C12 |
| File exists, assertions need updating post-spec-fix | 1 | C13 |
| **Total** | **13** | C1–C13 |

### Three spec deltas that drive the day-2 work

1. **Phase math wrong (C7, C4, C13)** — `_PHASE_B_START_BASE_DOLLARS` is `1500` (should be `2000`), Phase B is a linear taper (should be discrete `$1,000` step), Phase C starts at `$4,000` (should be `$3,000`). Bootstrap JSON carries the same wrong boundary values.

2. **Initial SL wrong (C6, C4, C13)** — `snapped_d_init` is computed from `abs(entry - sl_level) * point_value` (OR-range derived), giving a variable dollar distance. Isaac requires **fixed `$1,025`** for all NKD trades regardless of opening range.

3. **Jitter surface wrong (C7, C3, C13)** — Jitter J only shifts phase-threshold *comparison* values (`1500+J`, `4000+J`). Isaac confirmed J must be added to the **broker-side dollar buffer** (SL) and the **TP target** ($4,450 + J). The `b7b_nkd_trail.py` docstring at lines 99-104 explicitly calls the broker-price interpretation "forbidden" — this must be inverted in C16.

### Commits not yet run on tower (require explicit operator action)

- **C12 (Intervention A)**: `cmd-run nkd_pivot_d26_override.py` — only after all code commits are verified safe on Nomaan tower AND operator explicitly approves.

### Pre-market checklist update

After C14–C16 land, update [`docs2/runbooks/apac-nkd-pre-market-checklist.md`](../../../../docs2/runbooks/apac-nkd-pre-market-checklist.md) to reflect:
- Expected `snapped_d_init` = `1025` (fixed, not OR-range)
- Phase B threshold = `$2,000` profit (not `$1,500`)
- Phase B buffer = `$1,000` (flat step, not linear taper)
- Phase C threshold = `$3,000` profit (not `$4,000`)
- Jitter J on Isaac tower shifts both SL broker prices AND TP bracket price
