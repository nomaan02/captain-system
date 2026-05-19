# NKD Rejected-Orders Build Plan

**Generated:** 2026-05-19
**Source audit:** [`REJECTED_ORDERS_AUDIT.md`](REJECTED_ORDERS_AUDIT.md) (same folder)
**Authoritative day-2 plan:** [`docs2/quick-fixes/NKD_Pivot/day_2/PLAN.md`](../PLAN.md)
**Workspace rules:** [`.cursor/rules/captain-deploy-and-tower-discipline.mdc`](../../../../../.cursor/rules/captain-deploy-and-tower-discipline.mdc) (dual-remote push, fish-shell discipline)
**Status:** READY-TO-EXECUTE — paste each batch's prompts into a fresh agent session in order.

---

## 0. TL;DR

The audit identified **5 findings** plus 2 follow-up items in §8. They are batched below to maximise atomicity, preserve context window per session, and keep the most expensive model (Opus 4.7) reserved for the highest-stakes commit.

| Batch | Findings | Severity | Model | Estimated effort | Dependency |
|---|---|---|---|---|---|
| **1** | F2 + F3 — Trail-control field forwarding (`sanitise_for_api` + `route_command` + `_handle_taken_skipped`) | **CRITICAL BLOCKER** | **Opus 4.7** | M (3 files, ~30 LOC, multi-test) | none — go first |
| **2** | F4 — Orphan TP placed after SL-fail flatten | MEDIUM | Sonnet 4.6 | S (1 file, 1 guard clause) | independent of B1 |
| **3** | F5 + §8.3 — Jitter symmetry confirmation + trail-block silent-skip observability | LOW | Sonnet 4.6 | S (1 file, 1 log line + 1 alert path) | depends on B1 |
| **4** | Validation suite, runbook patch, tower deploy runbook | OPERATIONAL | Sonnet 4.6 | S (docs + test runs + tower fish commands) | depends on B1, B2, B3 |

§8.4 (fallback SL slippage robustness) is intentionally **out of scope** for this build plan; defer to a future day-3 audit if the C15 $1,025 SL distance ever proves insufficient against extreme slippage.

### Critical path

```
Batch 1 (Opus, CRITICAL) → Batch 2 (Sonnet) → Batch 3 (Sonnet) → Batch 4 (Sonnet, deploy)
```

Batch 2 can technically run in parallel with Batch 1 (different files, different concern) but **don't** — it muddies the post-mortem and the dual-remote SHA parity check. Run sequentially.

---

## 1. Pre-flight (run before Batch 1)

These checks belong to whichever session opens Batch 1; reproduced here for visibility.

1. **No open NKD position** (mid-position rollover risk):
   ```fish
   set -gx REDIS_PASSWORD (grep '^REDIS_PASSWORD=' ~/captain-system/.env | cut -d= -f2)
   docker exec captain-system-redis-1 redis-cli -a "$REDIS_PASSWORD" --no-auth-warning HGETALL captain:open_positions | grep -i is_nkd_trail
   # Must produce no output. If a row exists, STOP and ask Nomaan.
   ```

2. **Both remotes synced at C16** (the F2 fix builds on top of C14/C15/C16):
   ```fish
   git fetch origin; and git fetch multi-user
   test (git rev-parse HEAD) = (git rev-parse origin/main); and \
   test (git rev-parse HEAD) = (git rev-parse multi-user/main); \
       and echo "OK: both remotes synced" or echo "MISMATCH"
   ```

3. **D00 NKD locked_strategy carries `sl_dollars_fixed: 1025`** (proves C15 bootstrap landed):
   ```fish
   command -v jq > /dev/null 2>&1; or sudo apt install -y jq
   curl -s -G "http://localhost:9000/exec" \
     --data-urlencode "query=SELECT locked_strategy FROM p3_d00_asset_universe WHERE asset_id='NKD' LATEST ON last_updated PARTITION BY asset_id" \
     | jq -r '.dataset[0][0]' \
     | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print('sl_dollars_fixed=', d.get('sl_dollars_fixed'), '| trail_phase_b_buffer_dollars=', d.get('trail_phase_b_buffer_dollars'))"
   # Expected: sl_dollars_fixed= 1025 | trail_phase_b_buffer_dollars= 1000
   ```

If any check fails, **STOP** before opening Batch 1.

---

## 2. Batch 1 — F2 + F3: Trail-Control Field Forwarding [CRITICAL]

| Field | Value |
|---|---|
| Severity | **CRITICAL BLOCKER** — without this, the entire NKD trail block is inert |
| Model | **Opus 4.7** |
| Audit refs | §0 F2/F3, §4 (full proof), §7 Option B (3-file fix), §8.2 (jitter symmetry) |
| Files in scope | `captain-command/captain_command/blocks/b1_core_routing.py` (both `sanitise_for_api` AND `route_command` TAKEN_SKIPPED branch); `captain-command/captain_command/blocks/orchestrator.py` (`_auto_execute_signal` TAKEN_SKIPPED publish at lines 666-704); `captain-online/captain_online/blocks/orchestrator.py` (`_handle_taken_skipped` at lines 1232-1244) |
| New tests | `test_sanitise_for_api_preserves_nkd_trail_fields`, `test_route_command_taken_preserves_nkd_trail_fields`, `test_taken_skipped_threads_jitter_to_position_dict`, plus 1 end-to-end signal-to-position-dict test |
| Checklist artefact | `BATCH_1_F2_F3_TRAIL_FORWARDING.md` (created by planning agent in this folder) |

### What's broken (1 paragraph)

B6 builds NKD trail-control fields (`is_nkd_trail`, `tp_dollars`, `snapped_d_init`, `jitter_x`, `jitter_y`, `jitter_j`) at the top level of every NKD signal. `sanitise_for_api` (b1_core_routing.py:131-153) returns an explicit allow-list dict that **omits all 6 NKD keys**. Downstream, `_auto_execute_signal` (orchestrator.py:701-703) tries to forward 3 of those keys via `sanitised_order.get(...)` but reads `None` because they were stripped. Online's `_handle_taken_skipped` (orchestrator.py:1238-1240) hard-codes `jitter_x/y/j = None` instead of reading from the stream message. End result: every NKD position lands with `is_nkd_trail=False`, and `b7b_nkd_trail.scan_nkd_trails` silently `continue`s past every NKD position at line 533. The trail never engages. The same gap exists in `route_command` (b1_core_routing.py:204-229) for the manual GUI TAKEN path.

### Planning prompt (paste into a fresh Opus 4.7 session)

--- BEGIN PLANNING PROMPT ---

You are batch 1 (PLANNING ONLY) of the NKD rejected-orders fix series. The fix unblocks the trailing-stop ratchet that has been silently inert on every NKD trade since C6 landed. This is an absolute priority.

Read in this order, in full:

1. `docs2/quick-fixes/NKD_Pivot/day_2/Rejected _orders_issue/REJECTED_ORDERS_AUDIT.md` — focus §0 (TL;DR), §4 (F2 critical proof), §7 Option B (the 3-file fix), §8.2 (jitter symmetry once F2 lands).
2. `docs2/quick-fixes/NKD_Pivot/day_2/Rejected _orders_issue/BUILD_PLAN.md` — section "Batch 1".
3. `captain-command/captain_command/blocks/b1_core_routing.py` lines 100-230 (focus `sanitise_for_api` lines 131-153 AND `route_command` TAKEN_SKIPPED branch lines 196-229).
4. `captain-command/captain_command/blocks/orchestrator.py` lines 580-715 (focus `_auto_execute_signal` TAKEN_SKIPPED publish at lines 666-704).
5. `captain-online/captain_online/blocks/orchestrator.py` lines 1180-1300 (focus `_handle_taken_skipped` lines 1232-1244 — note `as_money_or_none` and `bool(...)` coercions).
6. `captain-online/captain_online/blocks/b6_signal_output.py` lines 100-200 (where the 6 NKD fields are built — confirm the exact key names).
7. `captain-online/captain_online/blocks/b7b_nkd_trail.py` lines 510-575 (the silent-skip site at line 533) and lines 655-680 (first-poll jitter sampler — leave logic intact, but understand it for §8.2 risk).
8. `tests/test_command_sanitise.py` — pattern for sanitise tests.
9. `tests/test_nkd_jitter_lifecycle.py`, `tests/test_b7b_isaac_jitter_stress.py` — patterns for jitter tests.

Your job: write a detailed implementation plan to `docs2/quick-fixes/NKD_Pivot/day_2/Rejected _orders_issue/BATCH_1_F2_F3_TRAIL_FORWARDING.md`. The plan MUST include:

- 1-paragraph summary of F2 + F3 (cite line numbers)
- Exact before/after diffs for each of the 4 edit sites (3 files; b1_core_routing.py is touched twice)
- The 6 NKD field names with their target types after coercion (`is_nkd_trail` → bool, `tp_dollars`/`snapped_d_init`/`jitter_j`/`jitter_x` → Decimal via `as_money_or_none`, `jitter_y` → int or None)
- New tests: file paths, test method names, exact assertions (use the `_make_signal` helper pattern from `test_command_sanitise.py`)
- Validation gates: (a) audit §4.3 empirical confirmation script, (b) full NKD pytest suite, (c) regression assertion that non-NKD signals still produce the original 13-key sanitised dict
- Risk register: regression on non-NKD assets, Decimal coercion edge cases, GUI manual-TAKEN payload that may not yet ship the 6 NKD keys (route_command must be defensive — None defaults required)
- Completion checklist (markdown checkboxes, all unchecked)

Hard rules:
- READ-ONLY this session — no code edits, no test runs, no commits.
- If any audit detail is ambiguous, STOP and ask Nomaan.
- Reference findings by ID (F2, F3, §8.2 etc.) throughout the plan.
- Do not suggest changes outside the 3 named files.

Deliverable: absolute path of `BATCH_1_F2_F3_TRAIL_FORWARDING.md` and a 5-line summary of the proposed edits.

--- END PLANNING PROMPT ---

### Execution prompt (paste into a fresh Opus 4.7 session AFTER the planning agent has finished)

--- BEGIN EXECUTION PROMPT ---

You are batch 1 (EXECUTION) of the NKD rejected-orders fix series. The plan you must follow lives at `docs2/quick-fixes/NKD_Pivot/day_2/Rejected _orders_issue/BATCH_1_F2_F3_TRAIL_FORWARDING.md`.

Workflow:

1. Re-read the plan, the audit's §4 + §7 Option B, and `.cursor/rules/captain-deploy-and-tower-discipline.mdc` §1 (dual-remote push) and §2 (fish discipline).
2. **Pre-flight gate** — verify no open NKD position:
   ```fish
   set -gx REDIS_PASSWORD (grep '^REDIS_PASSWORD=' ~/captain-system/.env | cut -d= -f2)
   docker exec captain-system-redis-1 redis-cli -a "$REDIS_PASSWORD" --no-auth-warning HGETALL captain:open_positions | grep -i is_nkd_trail
   ```
   Must be empty. If not, STOP.
3. Make edits in this exact order: (a) `sanitise_for_api` (add 6 keys, defaulting to None), (b) `route_command` TAKEN_SKIPPED branch (add 6 keys with `data.get(...)` for None defaults), (c) `_auto_execute_signal` TAKEN_SKIPPED publish (forward `jitter_x`/`jitter_y`/`jitter_j` from `sanitised_order` — already forwards 3 of the 6), (d) `_handle_taken_skipped` (replace hard-coded `None` with `as_money_or_none(data.get(...))` for jitter_x/jitter_j and explicit None-or-int for jitter_y). Tick the checklist as you go.
4. Add the 4 new tests per the plan. Run them in isolation first.
5. Run the audit §4.3 empirical confirmation script inside captain-command — confirm `is_nkd_trail`, `tp_dollars`, `snapped_d_init`, `jitter_j` ALL appear in the sanitised dict.
6. Run regression suite:
   ```bash
   PYTHONPATH=./:./captain-online:./captain-offline:./captain-command \
     python3 -m pytest tests/test_command_sanitise.py tests/test_b6_signal.py \
       tests/test_b7b_nkd_trail.py tests/test_b7b_isaac_jitter_stress.py \
       tests/test_nkd_jitter_lifecycle.py tests/test_userstream_bracket_capture.py \
       tests/test_b1_core_routing_decimal_log.py -v
   ```
   Update checklist with pass/fail counts per file.
7. Commit with conventional message (single atomic commit covering F2 + F3):
   ```
   fix(b1+command+online): forward NKD trail-control fields end-to-end (F2/F3)

   sanitise_for_api now preserves is_nkd_trail, tp_dollars, snapped_d_init,
   jitter_x, jitter_y, jitter_j. route_command TAKEN_SKIPPED branch and
   _auto_execute_signal both forward all six. _handle_taken_skipped reads
   jitter_x/y/j from the stream message instead of forcing None. Result:
   b7b_nkd_trail.scan_nkd_trails no longer silently skips every NKD
   position; trailing-stop ratchet engages on first poll.

   Refs: docs2/quick-fixes/NKD_Pivot/day_2/Rejected _orders_issue/REJECTED_ORDERS_AUDIT.md
         §4 (proof), §7 Option B (3-file fix), §8.2 (jitter symmetry)
   ```
8. Push to BOTH remotes:
   ```fish
   git push origin HEAD; and git push multi-user HEAD
   git fetch origin; and git fetch multi-user
   test (git rev-parse HEAD) = (git rev-parse origin/main); and \
   test (git rev-parse HEAD) = (git rev-parse multi-user/main); \
       and echo "OK: both remotes synced" or echo "MISMATCH"
   ```
9. Update the checklist file with: 4 file:line citations, 4 test pass/fail counts, commit SHA, dual-remote SHA-parity confirmation, empirical-confirmation script output.

Hard rules:
- Do NOT deploy to towers — that is Batch 4's operator-gated step.
- Do NOT bundle commits. F2 + F3 share one commit because they're the same architectural fix.
- Do NOT use `--force` on either remote.
- If any test fails, STOP, update checklist with diagnosis, do not push.
- The empirical-confirmation output MUST show all 4 NKD keys present in the sanitised dict, otherwise the fix is incomplete.

When done: report SHA + dual-remote parity + per-file test summary + empirical-confirmation output, all written into the checklist file.

--- END EXECUTION PROMPT ---

---

## 3. Batch 2 — F4: Orphan TP After SL-Fail Flatten [MEDIUM]

| Field | Value |
|---|---|
| Severity | MEDIUM — only fires on the rare bracket-failure + fallback-SL-failure path that C15 makes much less likely; but produced an orphan limit BUY at `60665` last night that the operator had to cancel manually at 23:22:43 |
| Model | **Sonnet 4.6** |
| Audit refs | §0 F4, §1 row #4, §3.4, §8.1 |
| Files in scope | `captain-command/captain_command/blocks/b3_api_adapter.py` (lines 474-510 — the fallback TP placement block) |
| New tests | `test_fallback_tp_skipped_when_sl_failed`, `test_fallback_tp_placed_when_sl_succeeded` (additions to `tests/test_b3_api_adapter_sltp.py`) |
| Checklist artefact | `BATCH_2_F4_ORPHAN_TP.md` |

### What's broken (1 paragraph)

`b3_api_adapter.send_signal` falls back to separate-orders when the atomic bracket fails. It places the entry market order, then attempts the SL. If the SL fails, it logs CRITICAL, calls `close_position` to emergency-flatten, and sets `result["sl_failed"] = True`. **It then runs the TP placement block unconditionally** (lines 474-510), placing a working LIMIT order against a now-flat position. The exchange accepts it (a working order does not require an underlying position) and it sits there as an orphan until the operator manually cancels it. C15's $1,025 SL distance makes this path much less likely to fire, but the bug is real and produced a real orphan last night.

### Planning prompt (paste into a fresh Sonnet 4.6 session)

--- BEGIN PLANNING PROMPT ---

You are batch 2 (PLANNING ONLY) of the NKD rejected-orders fix series. The fix prevents an orphan LIMIT TP from being placed after a fallback SL placement fails and the position is emergency-flattened.

Read in this order:

1. `docs2/quick-fixes/NKD_Pivot/day_2/Rejected _orders_issue/REJECTED_ORDERS_AUDIT.md` — focus §0 F4, §1 row #4, §3.4, §8.1.
2. `docs2/quick-fixes/NKD_Pivot/day_2/Rejected _orders_issue/BUILD_PLAN.md` — section "Batch 2".
3. `captain-command/captain_command/blocks/b3_api_adapter.py` lines 270-525 (full `send_signal` body — confirm flow: bracket attempt → fallback entry → fallback SL → emergency flatten → fallback TP).
4. `tests/test_b3_api_adapter_sltp.py` — pattern for SL/TP placement mocking and assertions.

Your job: write the plan to `docs2/quick-fixes/NKD_Pivot/day_2/Rejected _orders_issue/BATCH_2_F4_ORPHAN_TP.md`. Plan MUST include:

- 1-paragraph summary citing the exact CSV row from the audit (order #4 limit BUY @ 60665 placed at 23:08:07, cancelled manually at 23:22:43)
- Before/after diff for the single guard clause. The fix is to gate the TP block on `sl_failed != True AND result["status"] not in ("FLATTENED_SL_FAIL", "EMERGENCY_UNPROTECTED")`. Suggested form:
  ```python
  sl_failed_or_flattened = (
      result.get("sl_failed") is True
      or result.get("status") in ("FLATTENED_SL_FAIL", "EMERGENCY_UNPROTECTED")
  )
  if tp_price is not None and not sl_failed_or_flattened:
      tp_resp = self._client.place_limit_order(...)
      ...
  ```
  but the planning agent must verify the exact `result.status` strings in the surrounding code (lines 445-455).
- New test cases (use the mocking pattern in `test_b3_api_adapter_sltp.py`):
  - `test_fallback_tp_skipped_when_sl_failed_and_flattened` — SL `place_stop_order` returns success=False, `close_position` succeeds, assert `place_limit_order` is **NOT** called and `result["tp_order_id"] is None`.
  - `test_fallback_tp_skipped_when_emergency_unprotected` — SL fails AND `close_position` raises, status becomes `EMERGENCY_UNPROTECTED`, assert TP not placed.
  - `test_fallback_tp_placed_when_sl_succeeded` — regression: SL succeeds, TP placed normally.
  - `test_bracket_path_unaffected` — when bracket succeeds, neither fallback SL nor fallback TP is touched (already covered, but assert it stays green).
- Validation gates: `pytest tests/test_b3_api_adapter_sltp.py -v` plus a manual eyeball of the audit's order log to confirm the orphan path.
- Risk register: do NOT change behaviour when SL succeeds (regression risk); ensure the guard is `result.get("sl_failed") is True` not truthy-test (the field is only set when the SL ATTEMPT failed, not when it was never attempted).
- Completion checklist with markdown checkboxes.

Hard rules:
- READ-ONLY this session.
- The fix must be a single guard clause — do not refactor the surrounding fallback flow.
- If `sl_price is None` (no SL was attempted), the TP block must still run as before (e.g. user explicitly opted out of SL — not relevant for NKD, but preserve behaviour).
- If any audit detail is ambiguous, STOP and ask Nomaan.

Deliverable: absolute path of `BATCH_2_F4_ORPHAN_TP.md` and a 3-line summary of the guard clause.

--- END PLANNING PROMPT ---

### Execution prompt (paste into a fresh Sonnet 4.6 session AFTER the planning agent has finished)

--- BEGIN EXECUTION PROMPT ---

You are batch 2 (EXECUTION) of the NKD rejected-orders fix series. The plan you must follow lives at `docs2/quick-fixes/NKD_Pivot/day_2/Rejected _orders_issue/BATCH_2_F4_ORPHAN_TP.md`. Batch 1 must be merged to both remotes before you start.

Workflow:

1. Re-read the plan + audit §8.1 + `.cursor/rules/captain-deploy-and-tower-discipline.mdc` §1.
2. Verify Batch 1's commit is on both remotes (`git log --oneline -1 origin/main` and `multi-user/main` should match the local HEAD).
3. Make the single guard-clause edit in `b3_api_adapter.py`. Tick the checklist.
4. Add the 4 test cases per plan. Run `pytest tests/test_b3_api_adapter_sltp.py -v` — must be all green.
5. Commit:
   ```
   fix(b3_api_adapter): skip fallback TP placement after SL-fail flatten (F4)

   When the bracket order falls through to the separate-orders path and
   the standalone SL placement fails, b3 emergency-flattens the position
   via close_position. Previously the TP block ran unconditionally
   afterwards, leaving an orphan working LIMIT order against a flat
   position (observed 2026-05-18 APAC: order 2994362566 limit BUY @
   60665 cancelled manually 14 minutes later). Guard the TP block on
   sl_failed/status so it skips when the fallback SL was rejected.

   Refs: docs2/quick-fixes/NKD_Pivot/day_2/Rejected _orders_issue/REJECTED_ORDERS_AUDIT.md
         §1 row #4, §3.4, §8.1
   ```
6. Push to BOTH remotes; verify SHA parity (same procedure as Batch 1 step 8).
7. Update the checklist with: file:line, test pass/fail, commit SHA, dual-remote parity confirmation.

Hard rules:
- Do NOT deploy to towers.
- Do NOT touch the bracket success path or the emergency-flatten log lines.
- Do NOT change error-message strings (alerts have downstream consumers).
- If any test fails, STOP and update checklist with diagnosis.

When done: SHA + dual-remote parity + 4-test pass/fail summary in the checklist.

--- END EXECUTION PROMPT ---

---

## 4. Batch 3 — F5 + §8.3: Jitter Symmetry Confirmation + Trail-Block Observability [LOW]

| Field | Value |
|---|---|
| Severity | LOW — F5 is automatically resolved by Batch 1 (jitter_j now threads from B6 to position dict, so the first-poll defence-in-depth becomes a no-op for the normal path). §8.3 adds observability that would have flagged F2 on the first NKD trade. |
| Model | **Sonnet 4.6** |
| Audit refs | §0 F5, §4.2, §5.2 (Isaac jitter row), §8.2, §8.3 |
| Files in scope | `captain-online/captain_online/blocks/b7b_nkd_trail.py` (lines ~510-555 for the silent-skip log; lines 654-675 for the first-poll jitter defence-in-depth) |
| New tests | `test_scan_logs_when_nkd_position_skipped` (NKD position with `is_nkd_trail=False` produces an INFO log line per poll cycle); `test_first_poll_critical_alert_when_jitter_missing_on_isaac` (Isaac tower position dict has `jitter_j=None` → trail block logs CRITICAL + emits NKD_TRAIL_JITTER_MISSING alert before re-sampling) |
| Checklist artefact | `BATCH_3_F5_OBSERVABILITY.md` |

### What's broken (1 paragraph)

After Batch 1 lands, F5 is structurally fixed — B6 samples J once, threads it through the signal payload to the position dict, and the trail block reads it on every poll without re-sampling. **But** the defence-in-depth re-sampling at `b7b_nkd_trail.py:660-669` will still fire if `jitter_j` is missing for any reason (replay test bypassing B6, position rehydrated from a pre-Batch-1 Redis hash, or — most importantly — the F2 fix has regressed). On Isaac tower (`INSTANCE_PARITY=="1"`) that produces a J ≠ J_a (the J B6 used for the TP bracket), violating Isaac's "one signed J per trade" spec. §8.3 is independent: today, `scan_nkd_trails` silently `continue`s past every NKD position when `is_nkd_trail=False` — there is zero log evidence that the trail was inert. The fix for §8.3 is a single INFO log per poll cycle when at least one NKD position was seen but all skipped.

### Planning prompt (paste into a fresh Sonnet 4.6 session)

--- BEGIN PLANNING PROMPT ---

You are batch 3 (PLANNING ONLY) of the NKD rejected-orders fix series. This batch tightens up two observability gaps that would have flagged Batch 1's bug on the first NKD trade. Batches 1 and 2 must already be merged to both remotes before this runs.

Read in this order:

1. `docs2/quick-fixes/NKD_Pivot/day_2/Rejected _orders_issue/REJECTED_ORDERS_AUDIT.md` — focus §0 F5, §4.2, §5.2 (Isaac jitter row), §8.2, §8.3.
2. `docs2/quick-fixes/NKD_Pivot/day_2/Rejected _orders_issue/BUILD_PLAN.md` — section "Batch 3".
3. `docs2/quick-fixes/NKD_Pivot/day_2/Rejected _orders_issue/BATCH_1_F2_F3_TRAIL_FORWARDING.md` — confirm what Batch 1 changed in `_handle_taken_skipped`.
4. `captain-online/captain_online/blocks/b7b_nkd_trail.py` lines 510-700 (focus the per-position loop at 532-555, the first-poll jitter defence at 654-680, the existing alert helper `_emit_alert`).
5. `tests/test_b7b_isaac_jitter_stress.py` and `tests/test_nkd_jitter_lifecycle.py` — patterns for jitter assertions.
6. `tests/test_b7b_nkd_trail.py` — patterns for `scan_nkd_trails` behaviour.

Your job: write the plan to `docs2/quick-fixes/NKD_Pivot/day_2/Rejected _orders_issue/BATCH_3_F5_OBSERVABILITY.md`. Plan MUST include:

- 1-paragraph summary of (a) §8.3 silent-skip log and (b) F5 + §8.2 Isaac-tower CRITICAL-on-missing-jitter
- Exact diff for the §8.3 fix: counter for skipped NKD positions, single INFO log at the end of `scan_nkd_trails` if `skipped > 0`. Suggested form:
  ```python
  skipped_inert = 0
  for pos in (open_positions or []):
      if not pos.get("is_nkd_trail"):
          if (pos.get("asset") or "").upper() == "NKD":
              skipped_inert += 1
          continue
      ...
  if skipped_inert > 0:
      logger.info(
          "ON-B7B-NKD: scan saw %d NKD position(s) with is_nkd_trail=False — "
          "trail logic inert for those positions; verify F2 fix is on tower",
          skipped_inert,
      )
  ```
  but the planning agent must verify exact log-format conventions in the surrounding module.
- Exact diff for the F5 / §8.2 fix: when `first_poll is True` AND `parity_env == "1"`, emit `NKD_TRAIL_JITTER_MISSING` CRITICAL alert via `_emit_alert(...)` BEFORE re-sampling. Then sample as today (defence-in-depth still wins over an unprotected position).
- New tests:
  - `test_scan_logs_when_nkd_position_skipped` — inject 1 NKD position with `is_nkd_trail=False`, capture log, assert the new INFO line fires with `skipped=1`.
  - `test_scan_does_not_log_when_no_nkd_positions` — empty list / non-NKD positions only — assert no new INFO line.
  - `test_first_poll_critical_alert_when_jitter_missing_on_isaac` — `parity_env="1"`, position with `jitter_j=None` — assert `_emit_alert` called with `priority="CRITICAL"` and `event_type="NKD_TRAIL_JITTER_MISSING"`, then assert re-sampling still produces a non-zero J.
  - `test_first_poll_no_alert_on_nomaan` — `parity_env=""`, position with `jitter_j=None` — assert no CRITICAL alert (Nomaan tower's J is always 0 by design, so missing J is benign).
- Validation gates: `pytest tests/test_b7b_nkd_trail.py tests/test_b7b_isaac_jitter_stress.py tests/test_nkd_jitter_lifecycle.py -v`.
- Risk register: log spam if many positions are skipped (mitigated by single aggregate log line per scan); test for `_emit_alert` mock signature must match existing `_emit_alert` calls in the file.
- Completion checklist with markdown checkboxes.

Hard rules:
- READ-ONLY this session.
- Do NOT remove the first-poll re-sampling — it is defence-in-depth that protects against unprotected positions even if B6 / Batch 1 fail.
- Do NOT change phase-math or ratchet logic.
- If any audit detail is ambiguous, STOP and ask Nomaan.

Deliverable: absolute path of `BATCH_3_F5_OBSERVABILITY.md` and a 3-line summary.

--- END PLANNING PROMPT ---

### Execution prompt (paste into a fresh Sonnet 4.6 session AFTER the planning agent has finished)

--- BEGIN EXECUTION PROMPT ---

You are batch 3 (EXECUTION) of the NKD rejected-orders fix series. The plan you must follow lives at `docs2/quick-fixes/NKD_Pivot/day_2/Rejected _orders_issue/BATCH_3_F5_OBSERVABILITY.md`. Batches 1 and 2 must be merged to both remotes before you start.

Workflow:

1. Re-read the plan + audit §8.2 + §8.3 + `.cursor/rules/captain-deploy-and-tower-discipline.mdc` §1.
2. Verify Batches 1 and 2 are on both remotes (`git log --oneline -3 origin/main` should show both commits and HEAD; same for multi-user/main).
3. Make the two edits per plan (silent-skip log + Isaac-tower CRITICAL-on-missing-jitter alert). Tick the checklist.
4. Add the 4 test cases. Run `pytest tests/test_b7b_nkd_trail.py tests/test_b7b_isaac_jitter_stress.py tests/test_nkd_jitter_lifecycle.py -v` — must be all green.
5. Commit:
   ```
   feat(b7b_nkd_trail): observability for inert trail + missing-jitter (F5/§8.3)

   Adds an INFO aggregate log line per scan_nkd_trails poll when one or
   more NKD positions are skipped due to is_nkd_trail=False (would have
   flagged F2 on the first NKD trade). Adds a CRITICAL alert
   NKD_TRAIL_JITTER_MISSING when the first-poll defence-in-depth
   sampler fires on Isaac tower (parity_env="1") — that path indicates
   B6→position-dict threading has regressed. Defence-in-depth
   re-sampling is preserved so the position is never unprotected.

   Refs: docs2/quick-fixes/NKD_Pivot/day_2/Rejected _orders_issue/REJECTED_ORDERS_AUDIT.md
         §4.2, §8.2, §8.3
   ```
6. Push to BOTH remotes; verify SHA parity.
7. Update the checklist with: file:line citations, test pass/fail, commit SHA, parity confirmation.

Hard rules:
- Do NOT deploy to towers.
- Do NOT remove or weaken the first-poll re-sampling — only add the alert.
- Do NOT change `_emit_alert` signature.
- If any test fails, STOP and update checklist with diagnosis.

When done: SHA + dual-remote parity + 4-test pass/fail summary + sample log line + sample alert payload in the checklist.

--- END EXECUTION PROMPT ---

---

## 5. Batch 4 — Validation, Runbook Patch, Tower Deploy Runbook [OPERATIONAL]

| Field | Value |
|---|---|
| Severity | OPERATIONAL — confirms all of B1/B2/B3 are healthy, updates the pre-market runbook to reflect F2/F3/F4/F5/§8.3 changes, and emits the operator-only fish commands for the tower-side deploy. The agent does NOT run the deploy commands; the operator does. |
| Model | **Sonnet 4.6** |
| Audit refs | §0 TL;DR, §10 (post-session tracking checklist), all of §7 |
| Files in scope | `docs2/runbooks/apac-nkd-pre-market-checklist.md` (additions only — no other files edited) |
| Test scope | full NKD validation suite (11 test files) — PLUS the new tests added in B1/B2/B3 |
| Checklist artefact | `BATCH_4_VALIDATION_DEPLOY.md` |

### What this batch does (1 paragraph)

After Batches 1-3 are merged to both remotes, this batch (a) runs the consolidated regression suite to confirm zero regression, (b) extends `apac-nkd-pre-market-checklist.md` with the F2/F3 sanity checks (empirical confirmation script, expected log lines from the new INFO + CRITICAL paths, bracket-children Redis key check), and (c) emits the tower-side deploy runbook as a fenced fish-shell block per workspace rule §2 (helper preamble, idempotent, no bash-isms). The agent must not SSH into either tower or run any deploy commands itself.

### Planning prompt (paste into a fresh Sonnet 4.6 session)

--- BEGIN PLANNING PROMPT ---

You are batch 4 (PLANNING ONLY) of the NKD rejected-orders fix series. This is the final batch: regression sweep, runbook patch, and tower deploy runbook. Batches 1, 2, 3 must already be merged to both remotes before this runs.

Read in this order:

1. `docs2/quick-fixes/NKD_Pivot/day_2/Rejected _orders_issue/REJECTED_ORDERS_AUDIT.md` — focus §0 TL;DR + §10 post-session tracking checklist.
2. `docs2/quick-fixes/NKD_Pivot/day_2/Rejected _orders_issue/BUILD_PLAN.md` — section "Batch 4".
3. `docs2/quick-fixes/NKD_Pivot/day_2/Rejected _orders_issue/BATCH_1_F2_F3_TRAIL_FORWARDING.md`, `BATCH_2_F4_ORPHAN_TP.md`, `BATCH_3_F5_OBSERVABILITY.md` — confirm what was changed in each.
4. `docs2/runbooks/apac-nkd-pre-market-checklist.md` — current pre-market runbook.
5. `.cursor/rules/captain-deploy-and-tower-discipline.mdc` — §1 dual-remote push, §2 fish-shell discipline, §3 helper-function source of truth.
6. `docs2/quick-fixes/NKD_Pivot/day_2/PLAN.md` §4 — existing tower deploy ordering.

Your job: write the plan to `docs2/quick-fixes/NKD_Pivot/day_2/Rejected _orders_issue/BATCH_4_VALIDATION_DEPLOY.md`. Plan MUST include:

- Regression test command (consolidated, runs every NKD-relevant test in one invocation, including the new ones added in B1/B2/B3):
  ```bash
  PYTHONPATH=./:./captain-online:./captain-offline:./captain-command \
    python3 -m pytest tests/test_command_sanitise.py \
      tests/test_b1_core_routing_decimal_log.py \
      tests/test_b3_api_adapter_sltp.py \
      tests/test_b6_signal.py \
      tests/test_b7b_nkd_trail.py \
      tests/test_b7b_isaac_jitter_stress.py \
      tests/test_b7b_external_close.py \
      tests/test_b7b_fast_crossing_multiple_boundaries.py \
      tests/test_b7b_stale_quote_skips_modify.py \
      tests/test_nkd_jitter_lifecycle.py \
      tests/test_userstream_bracket_capture.py \
      tests/test_b12_compliance_modify_check.py \
      tests/test_marketstream_nkd_persistence.py \
      tests/test_b7_time_exit_nkd_exemption.py \
      tests/test_bootstrap_nkd_trail_fields.py \
      tests/test_tick_snap_outward.py \
      tests/test_nkd_replay_22h.py -v
  ```
- Section additions to `docs2/runbooks/apac-nkd-pre-market-checklist.md`:
  - **F2 sanity check** (empirical confirmation from audit §4.3 — runs in 5 seconds on the tower)
  - **D34 expectation table** post-fix (now expect at least 1 row per NKD trade; columns to inspect: `current_phase`, `current_buffer`, `current_stop_price`, `jitter_j`, `modify_seq`)
  - **GUI Trade panel expectation** post-fix (`current_phase`, `current_buffer`, `current_stop_price`, `modify_seq` columns now populate within 10 s of TAKEN)
  - **F4 orphan-TP** post-fix expectation (no orphan limit BUY/SELL after a fallback SL fail — confirm via order log)
  - **F5/§8.3 log signatures** to grep for after first NKD trade:
    - Expected on every poll cycle: `ON-B7B-NKD: jitter sampled signal=… parity=…` (only on first poll), then per-poll `ON-B7B-NKD: modify OK signal=…` lines
    - Expected if F2 has regressed: `ON-B7B-NKD: scan saw N NKD position(s) with is_nkd_trail=False` — operator action: stop and roll back B1
    - Expected if Isaac jitter has regressed: `NKD_TRAIL_JITTER_MISSING` CRITICAL alert
- Tower-side deploy runbook (operator-only, **agent must NOT execute**), as a fenced fish block following workspace rule §2 conventions:
  - Idempotent dependency preamble (`type -q dco; or function dco …`, `type -q cmd-run; or function cmd-run …` etc.)
  - `git remote get-url multi-user … or git remote add multi-user …` for fresh towers
  - SHA-parity check before deploy
  - `for svc in captain-offline captain-online captain-command; rm -rf $svc/_config; cp -r config $svc/_config; end` config sync
  - `dco build --no-cache captain-online captain-command`, then `dco up -d`
  - `cmd-run bootstrap_production.py` (idempotent — re-applies D00 NKD locked_strategy delta if any)
  - Post-deploy gates: D00 query for `sl_dollars_fixed`, `redis-cli HGETALL captain:open_positions` (expect empty), `dco logs captain-online | grep "ON-B7B-NKD"` (only after first NKD trade)
  - **Tower order: Nomaan tower first, then Isaac tower** (per workspace convention)
  - Pre-deploy Isaac-tower-only gate: `dco exec captain-online printenv INSTANCE_PARITY` must return `1`
- Validation gates: pytest pass; runbook diff applies cleanly; tower deploy block is fish-clean (`fish --no-execute -c "(paste block here)"` or visual review of `; and` chains).
- Risk register: regression on non-NKD assets caught by full pytest suite; runbook drift between Nomaan and Isaac towers (mitigated by SHA-parity gate); operator skipping the empirical confirmation script.
- Completion checklist with markdown checkboxes.

Hard rules:
- READ-ONLY this session.
- Do NOT propose changes to any production code (B1/B2/B3 already shipped them).
- Do NOT propose tower-side execution by the agent — the deploy runbook is operator-only.
- The deploy block MUST satisfy workspace rule §2: fish-compatible, idempotent, helper preamble at the top.
- If any audit detail is ambiguous, STOP and ask Nomaan.

Deliverable: absolute path of `BATCH_4_VALIDATION_DEPLOY.md` and a 5-line summary (test command, runbook sections to add, deploy block structure).

--- END PLANNING PROMPT ---

### Execution prompt (paste into a fresh Sonnet 4.6 session AFTER the planning agent has finished)

--- BEGIN EXECUTION PROMPT ---

You are batch 4 (EXECUTION) of the NKD rejected-orders fix series. The plan you must follow lives at `docs2/quick-fixes/NKD_Pivot/day_2/Rejected _orders_issue/BATCH_4_VALIDATION_DEPLOY.md`. Batches 1, 2, 3 must be merged to both remotes before you start.

Workflow:

1. Re-read the plan + `.cursor/rules/captain-deploy-and-tower-discipline.mdc` §1, §2, §3.
2. Verify Batches 1, 2, 3 are on both remotes (`git log --oneline -4 origin/main` and `multi-user/main` should match local HEAD with B1+B2+B3 commits visible).
3. Run the consolidated regression suite per plan. Update checklist with per-file pass/fail counts. If anything is red, STOP and report.
4. Apply the runbook diff to `docs2/runbooks/apac-nkd-pre-market-checklist.md` per plan. Tick the checklist.
5. Verify the tower-deploy fish block parses without error (read it back, confirm `; and` chains and helper preamble are intact — do NOT execute).
6. Commit:
   ```
   docs(runbook+tracking): post-fix pre-market gates and tower deploy runbook

   Adds the F2 empirical-confirmation script, the post-fix D34/GUI/log
   expectations, and the operator-only tower deploy fish block per
   workspace rule §2. No production code changes — those landed in
   F2/F3 (B1), F4 (B2), and F5/§8.3 (B3).

   Refs: docs2/quick-fixes/NKD_Pivot/day_2/Rejected _orders_issue/BUILD_PLAN.md §5
   ```
7. Push to BOTH remotes; verify SHA parity (per workspace rule §1).
8. Update the checklist with: full pytest summary (pass/fail per file), runbook diff applied (yes/no), tower deploy block sanity-checked (yes/no), commit SHA, dual-remote parity confirmation.
9. **Final hand-off**: emit a single markdown block with the operator's tower deploy command list, ready to paste into the operator's terminal session. Note explicitly: "Run on Nomaan tower first, then Isaac tower."

Hard rules:
- Do NOT deploy to towers — emit the runbook only.
- Do NOT touch any production code in this batch.
- Do NOT modify the audit `REJECTED_ORDERS_AUDIT.md` or the build plan.
- If pytest is red, STOP and report — do NOT proceed to runbook patch or commit.

When done: pytest pass summary + runbook diff confirmation + tower deploy block (fenced fish) + SHA + dual-remote parity, all written into the checklist.

--- END EXECUTION PROMPT ---

---

## 6. Final completion / sign-off matrix

After all four batches close out, this matrix should be all green. Operator (Nomaan) ticks each row only after both the per-batch checklist file confirms it AND the operator has eyeballed the evidence.

| Audit finding | Severity | Resolved by | Acceptance criterion | Operator sign-off |
|---|---|---|---|---|
| **F1** — Pre-C15 OR-range SL collapse | RESOLVED PRE-PLAN | C14/C15/C16 (already merged) | No `Invalid stop loss ticks` rejection on next NKD trade | [ ] |
| **F2** — `sanitise_for_api` strips NKD trail fields → trail block inert | CRITICAL | Batch 1 | Empirical confirmation script returns `True` for all 6 NKD keys; first NKD trade after deploy produces ≥1 D34 row within 30 s | [ ] |
| **F3** — `route_command` TAKEN_SKIPPED branch has same gap (manual GUI TAKEN) | HIGH | Batch 1 (same commit as F2) | New `test_route_command_taken_preserves_nkd_trail_fields` green | [ ] |
| **F4** — Orphan TP placed after fallback SL fail + flatten | MEDIUM | Batch 2 | New `test_fallback_tp_skipped_when_sl_failed_*` cases green; no orphan limit order on next bracket-failure event | [ ] |
| **F5** — Jitter sampled twice on Isaac tower | LOW (auto-resolved by F2 fix) | Batch 1 (structural) + Batch 3 (alert if regression) | First NKD trade on Isaac tower: `pos["jitter_j"] != 0` AND no `NKD_TRAIL_JITTER_MISSING` alert in `captain:alerts` | [ ] |
| **§8.3** — Trail block silently skips, no observability | LOW | Batch 3 | INFO log line with skipped count appears in `captain-online` logs if any NKD position has `is_nkd_trail=False` | [ ] |
| Runbook drift | OPERATIONAL | Batch 4 | `docs2/runbooks/apac-nkd-pre-market-checklist.md` includes the F2 empirical script + post-fix D34/GUI expectations | [ ] |
| Tower deploy parity | OPERATIONAL | Batch 4 + operator | Both towers at the same HEAD; D00 NKD `sl_dollars_fixed=1025` + `trail_phase_b_buffer_dollars=1000` on both; `INSTANCE_PARITY=1` confirmed on Isaac tower only | [ ] |

§8.4 (fallback SL slippage robustness) is intentionally deferred and is NOT part of this plan's sign-off.

---

## 7. Appendix

### A. Model selection rationale

| Batch | Model | Why |
|---|---|---|
| **1** | Opus 4.7 | Touches 3 files across the Command + Online boundary. Requires holding the full B6 → sanitise → TAKEN_SKIPPED → `_handle_taken_skipped` → b7b pipeline in head while making 4 coordinated edits. Regression risk on non-NKD assets is real (the allow-list pattern means missing a default could break ES/MES). End-to-end test design is non-trivial. |
| **2** | Sonnet 4.6 | Single file, single guard clause, mechanical. The audit even quotes the suggested fix verbatim. Test pattern already exists in `test_b3_api_adapter_sltp.py`. |
| **3** | Sonnet 4.6 | Single file, two narrow additions (counter+log, alert+log). No phase-math or ratchet edits. Test patterns exist in `test_b7b_isaac_jitter_stress.py`. |
| **4** | Sonnet 4.6 | Docs + test runs only. Zero production code edits. The complexity is in following workspace rule §2 (fish-shell discipline) precisely — Sonnet can handle pattern-following at this scope. |

### B. File map

| File | Touched by | Purpose |
|---|---|---|
| `captain-command/captain_command/blocks/b1_core_routing.py` | Batch 1 | `sanitise_for_api` (F2) and `route_command` TAKEN_SKIPPED branch (F3) |
| `captain-command/captain_command/blocks/orchestrator.py` | Batch 1 | `_auto_execute_signal` TAKEN_SKIPPED publish — forward jitter_x/y/j |
| `captain-online/captain_online/blocks/orchestrator.py` | Batch 1 | `_handle_taken_skipped` — read jitter_x/y/j from stream, not None |
| `captain-command/captain_command/blocks/b3_api_adapter.py` | Batch 2 | Fallback TP guard clause (F4) |
| `captain-online/captain_online/blocks/b7b_nkd_trail.py` | Batch 3 | Silent-skip log + Isaac CRITICAL-on-missing-jitter (F5/§8.3) |
| `docs2/runbooks/apac-nkd-pre-market-checklist.md` | Batch 4 | Post-fix runbook section additions |
| `tests/test_command_sanitise.py` | Batch 1 | Add NKD-field preservation tests |
| `tests/test_b1_core_routing_decimal_log.py` | Batch 1 | Add manual TAKEN forwarding tests |
| `tests/test_b3_api_adapter_sltp.py` | Batch 2 | Add SL-fail/orphan-TP tests |
| `tests/test_b7b_nkd_trail.py` + `test_b7b_isaac_jitter_stress.py` + `test_nkd_jitter_lifecycle.py` | Batches 1, 3 | Cross-cutting jitter/observability tests |

### C. Cross-references

- Day-2 plan (C14/C15/C16): [`docs2/quick-fixes/NKD_Pivot/day_2/PLAN.md`](../PLAN.md)
- Day-2 completion checklist: [`docs2/quick-fixes/NKD_Pivot/day_2/COMPLETION_CHECKLIST.md`](../COMPLETION_CHECKLIST.md)
- Day-2 passover prompt (already executed for C14/C15/C16): [`docs2/quick-fixes/NKD_Pivot/day_2/PASSOVER_PROMPT.md`](../PASSOVER_PROMPT.md)
- Pre-market runbook: [`docs2/runbooks/apac-nkd-pre-market-checklist.md`](../../../../runbooks/apac-nkd-pre-market-checklist.md)
- Workspace rules: [`.cursor/rules/captain-deploy-and-tower-discipline.mdc`](../../../../../.cursor/rules/captain-deploy-and-tower-discipline.mdc)
- Project guide: [`CLAUDE.md`](../../../../../CLAUDE.md)

---

**End of build plan.** Each batch's planning prompt creates the per-batch checklist `.md` file in this same folder; each batch's execution prompt updates that checklist as it works. The audit `REJECTED_ORDERS_AUDIT.md` and this `BUILD_PLAN.md` itself remain unchanged across all four batches.
