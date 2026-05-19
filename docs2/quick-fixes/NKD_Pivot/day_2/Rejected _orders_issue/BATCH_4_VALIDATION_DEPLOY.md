# Batch 4 — Validation, Runbook Patch, Tower Deploy Runbook

**Generated:** 2026-05-19 (planning + execution, Sonnet 4.6)
**Status:** EXECUTED — regression suite green, runbook patched, deploy runbook emitted.
**Severity:** OPERATIONAL — final batch; consolidates B1/B2/B3 and hands off to the operator for tower deploy.
**Source audit:** [`REJECTED_ORDERS_AUDIT.md`](REJECTED_ORDERS_AUDIT.md) §0 TL;DR, §10 post-session tracking checklist.
**Build plan:** [`BUILD_PLAN.md`](BUILD_PLAN.md) §5 "Batch 4".
**Workspace rules:** [`.cursor/rules/captain-deploy-and-tower-discipline.mdc`](../../../../../.cursor/rules/captain-deploy-and-tower-discipline.mdc) §1 (dual-remote push), §2 (fish-shell discipline), §3 (helper-function source of truth).
**Depends on:** Batch 1 (`c23b68b`, F2/F3), Batch 2 (`441671d`, F4), Batch 3 (`6349e33`, F5/§8.3) — all merged to both remotes before this batch runs.

---

## 1. What this batch does

After Batches 1–3 landed on both remotes, this batch:

1. Runs the **consolidated regression suite** (17 test files) to confirm zero regression across the full NKD validation surface.
2. Extends **`docs2/runbooks/apac-nkd-pre-market-checklist.md`** with five post-fix sub-steps (§2a–§2e) covering the F2 empirical sanity check, D34 row expectations, GUI panel expectations, F4 orphan-TP confirmation, and F5/§8.3 log signatures.
3. Emits the **operator-only tower deploy runbook** as a fenced fish block per workspace rule §2.

No production code changes in this batch. Every code fix landed in B1 (F2/F3), B2 (F4), B3 (F5/§8.3).

---

## 2. Pre-flight (verify B1 + B2 + B3 on both remotes)

Before running the regression suite or patching the runbook, confirm all three batch commits are on both remotes:

```fish
git fetch origin; and git fetch multi-user
git log --oneline -5 origin/main
# Expected top-4: 6349e33 (B3), 441671d (B2), 0c02ec4 (B1 docs), c23b68b (B1 code)
git log --oneline -5 multi-user/main
# Must match origin/main exactly

test (git rev-parse HEAD) = (git rev-parse origin/main); and \
test (git rev-parse HEAD) = (git rev-parse multi-user/main); \
    and echo "OK: both remotes synced" or echo "MISMATCH — stop and reconcile"
```

If `MISMATCH` — stop. Do not proceed until both remotes are at the same HEAD.

---

## 3. Consolidated regression test command

Run at the workspace root **on the dev host** (not inside a container). This is the single authoritative command for all NKD-relevant tests, including every new test added in B1, B2, and B3:

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

### Expected test counts

If any count diverges from this table, stop and diagnose before proceeding to the runbook patch or commit.

| Test file | Baseline | B1 additions | B2 additions | B3 additions | Expected total |
|---|---|---|---|---|---|
| `test_command_sanitise.py` | 12 | +3 | — | — | **15** |
| `test_b1_core_routing_decimal_log.py` | 2 | +2 | — | — | **4** |
| `test_b3_api_adapter_sltp.py` | 10 | — | +5 | — | **15** |
| `test_b6_signal.py` | 12 | — | — | — | **12** |
| `test_b7b_nkd_trail.py` | 46 | — | — | +2 | **48** |
| `test_b7b_isaac_jitter_stress.py` | 47 | — | — | +2 | **49** |
| `test_b7b_external_close.py` | 4 | — | — | — | **4** |
| `test_b7b_fast_crossing_multiple_boundaries.py` | 3 | — | — | — | **3** |
| `test_b7b_stale_quote_skips_modify.py` | 4 | — | — | — | **4** |
| `test_nkd_jitter_lifecycle.py` | 4 | — | — | — | **4** |
| `test_userstream_bracket_capture.py` | 13 | — | — | — | **13** |
| `test_b12_compliance_modify_check.py` | 8 | — | — | — | **8** |
| `test_marketstream_nkd_persistence.py` | 9 | — | — | — | **9** |
| `test_b7_time_exit_nkd_exemption.py` | 5 | — | — | — | **5** |
| `test_bootstrap_nkd_trail_fields.py` | 21 | — | — | — | **21** |
| `test_tick_snap_outward.py` | 12 | — | — | — | **12** |
| `test_nkd_replay_22h.py` | 7 | — | — | — | **7** |
| **TOTAL** | **223** | **+5** | **+5** | **+4** | **233** |

All 233 tests must pass with zero failures and zero errors before the runbook patch or commit proceeds.

---

## 4. Runbook additions to `docs2/runbooks/apac-nkd-pre-market-checklist.md`

Five new sub-steps are inserted after the existing **step 2** (D00 NKD locked_strategy check) as steps **2a–2e**. Existing step numbers (3–18) are unchanged.

### 2a — F2 sanity check (runs in 5 s — run before every live APAC session)

This script is the primary human-readable proof that Batch 1 (F2 fix) is active on this tower. If any line returns `False`, B1 is not deployed — **STOP**, do not open the APAC session.

```fish
dco exec -T captain-command python3 -c "
from captain_command.blocks.b1_core_routing import sanitise_for_api
signal = {
    'asset': 'NKD', 'direction': -1, 'size': 1,
    'tp_level': 60680, 'sl_level': 61805,
    'is_nkd_trail': True, 'tp_dollars': 4450, 'snapped_d_init': 1025.0,
    'jitter_x': 0.5, 'jitter_y': 1, 'jitter_j': 10.0,
    'signal_id': 'TEST', 'user_id': 'primary_user',
    '_context': {'entry_price': 61600},
    'per_account': {'21855714': {'contracts': 1}},
}
sanitised = sanitise_for_api(signal, '21855714', signal['per_account']['21855714'])
print('is_nkd_trail in sanitised?', 'is_nkd_trail' in sanitised)
print('tp_dollars in sanitised?', 'tp_dollars' in sanitised)
print('snapped_d_init in sanitised?', 'snapped_d_init' in sanitised)
print('jitter_j in sanitised?', 'jitter_j' in sanitised)
print('Total keys:', len(sanitised))
"
```

**Expected (post-B1):**
```
is_nkd_trail in sanitised? True
tp_dollars in sanitised? True
snapped_d_init in sanitised? True
jitter_j in sanitised? True
Total keys: 19
```

**Failure action:** any line `False` → B1 is not on this tower. Re-run the tower deploy runbook (§5 below). Do NOT open the APAC session — the trail block will be silently inert for the entire trade (audit §4, F2 proof).

### 2b — D34 expectation table post-fix

With B1 deployed, the first NKD trade TAKEN must produce at least 1 D34 row within 30 s of the bracket fill. Query post-session or during the session:

```fish
curl -s -G "http://localhost:9000/exec" \
  --data-urlencode "query=SELECT signal_id, current_phase, current_buffer, current_stop_price, jitter_j, modify_seq FROM p3_d34_nkd_trail_state LATEST ON last_updated PARTITION BY signal_id" \
  | jq '.dataset'
```

**Expected columns and values:**

| Column | Expected post-B1 | Pre-B1 (broken) state |
|---|---|---|
| `current_phase` | `"A"` on entry; `"B"` after +$2,000 profit; `"C"` after +$3,000 profit | `null` (trail block never ran) |
| `current_buffer` | `1025` in Phase A; `1000` in Phase B; `450` in Phase C | `null` |
| `current_stop_price` | Non-null price, on correct side of entry | `null` |
| `jitter_j` | `0` on Nomaan tower; non-zero on Isaac tower | `null` |
| `modify_seq` | Integer ≥ 1, incrementing each poll cycle | `null` or `0` |

**Failure action:** if D34 stays empty >2 min after fill:
```fish
dco logs captain-online 2>&1 | grep -iE "ON-B7B-NKD|nkd_trail|ERROR"
```
A `"scan saw N NKD position(s) with is_nkd_trail=False"` line confirms B1 regression — stop and roll back.

### 2c — GUI Trade panel expectations post-fix

Within 10 s of a TAKEN event, the GUI Trade panel must show these columns populating for the NKD position (they were permanently blank pre-B1):

- **`current_phase`** — `A`, `B`, or `C`
- **`current_buffer`** — dollar buffer value (starts $1,025; steps down through $1,000 → $450)
- **`current_stop_price`** — current trailing SL price (updates every 10 s per poll cycle)
- **`modify_seq`** — integer, increments on every successful `modify_order` call

If any column remains blank or `null` after 30 s:

1. Run step 2a — if it shows `False`, B1 is not on the tower.
2. Check `dco logs captain-online 2>&1 | grep "ON-B7B-NKD"` for error lines.
3. If D34 is empty (step 2b returns `[]`), the trail block is not running — diagnose before leaving the trade open.

### 2d — F4 orphan-TP post-fix expectation

The F4 fix (B2, `441671d`) prevents an orphan LIMIT order being placed after a fallback SL fails and the position is emergency-flattened.

After any session where a bracket rejection occurred (check `captain:alerts` for `SL_PLACEMENT_FAILED`):

- Pull the TopstepX order export CSV.
- Confirm there is **no open LIMIT BUY or LIMIT SELL** in the order log that corresponds to a position that no longer exists.
- The `captain-command` logs should show: `Fallback TP placement SKIPPED for entry <id> (sl_failed=True status=FLATTENED_SL_FAIL) — orphan TP guard (F4).`

**Failure action:** if an orphan LIMIT appears, cancel it manually in the broker GUI. Then verify B2 is on the tower by checking `git log --oneline -5 | grep "441671d"` on both towers.

### 2e — F5/§8.3 log signatures to grep after first NKD trade

After a NKD TAKEN fires, tail `captain-online` and filter for trail-block messages:

```fish
dco logs captain-online 2>&1 | grep "ON-B7B-NKD"
```

**Expected message catalogue:**

| Message | When it appears | Action if absent / unexpected |
|---|---|---|
| `ON-B7B-NKD: modify OK signal=… seq=…` | Every poll cycle while position is open | If never appears, trail block is not running — check D34 (step 2b) |
| `ON-B7B-NKD: jitter sampled signal=… parity=… X=… Y=… J=…` | **Should NOT fire post-B1** on normal path (only fires as defence-in-depth if `jitter_j` was `None`) | If it fires on Nomaan tower, the jitter field is not threading — check B1 on tower |
| `ON-B7B-NKD: scan saw N NKD position(s) with is_nkd_trail=False — trail logic inert for those positions; verify F2 fix is on tower` | **Should NEVER appear post-B1** | If it appears: **STOP** — B1 has regressed or is not on this tower. Roll back to pre-B1 and file a bug. |
| `NKD_TRAIL_JITTER_MISSING` CRITICAL in `captain:alerts` | **Should NEVER appear post-B1** on Isaac tower | If it appears: Isaac tower's jitter_j is not threading from B6 — the B6→position-dict path (B1) has regressed. Operator action: check git HEAD on Isaac tower; re-deploy. |

---

## 5. Tower-side deploy runbook (operator-only)

> **AGENT MUST NOT EXECUTE THIS SECTION.** The commands below are for the operator to run manually on each tower's fish shell terminal.

**Tower order: Nomaan tower first (INSTANCE_PARITY=0), then Isaac tower (INSTANCE_PARITY=1).**

Paste the entire block below into the tower's fish terminal in one shot. All steps are idempotent — safe to re-run if interrupted.

```fish
# ================================================================
# BATCH 4 — NKD REJECTED-ORDERS FIX DEPLOY RUNBOOK
# Covers: B1 (F2/F3) + B2 (F4) + B3 (F5/§8.3)
# Tower order: Nomaan FIRST, then Isaac.
# Agent must NOT execute. Operator pastes into fish terminal.
# ================================================================

# --- Step 0: Idempotent helper preamble (workspace rule §3) ---
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

# Tower-side apt prerequisites (idempotent)
command -v jq > /dev/null 2>&1; or sudo apt install -y jq
command -v redis-cli > /dev/null 2>&1; or sudo apt install -y redis-tools

# --- Step 1: Ensure multi-user remote exists (idempotent, fresh-tower safe) ---
git remote get-url multi-user > /dev/null 2>&1
or git remote add multi-user git@github.com:nomaan02/captain-multi-user.git

# --- Step 2: Pull latest code + SHA parity check before deploy ---
git pull --ff-only origin main
git fetch origin; and git fetch multi-user
test (git rev-parse HEAD) = (git rev-parse origin/main); and \
test (git rev-parse HEAD) = (git rev-parse multi-user/main); \
    and echo "OK: both remotes synced — safe to proceed" or echo "MISMATCH — stop and reconcile before building"

# --- Step 3: Pre-deploy gate — no open NKD position ---
# Do NOT deploy while an NKD trade is open. A mid-deploy restart clears the
# in-memory position dict and orphans the live broker position.
set -gx REDIS_PASSWORD (grep '^REDIS_PASSWORD=' ~/captain-system/.env | cut -d= -f2)
docker exec captain-system-redis-1 redis-cli -a "$REDIS_PASSWORD" --no-auth-warning \
    HGETALL captain:open_positions | grep -i is_nkd_trail
# Must produce no output. If a row appears, STOP — do not deploy mid-position.

# --- Step 4: Isaac-tower-only gate (skip on Nomaan tower) ---
# Run ONLY on Isaac tower. Must return "1" before proceeding.
# If blank or "0", edit .env → set INSTANCE_PARITY=1 → dco up -d → re-check.
dco exec captain-online printenv INSTANCE_PARITY
# Expected on Isaac: 1

# --- Step 5: Config sync (workspace rule §2, 2026-05-06) ---
# captain-{command,online,offline} Dockerfiles COPY _config/ — not config/ directly.
# Skipping this step means the rebuilt image uses stale config and bootstrap writes
# wrong values to D00.
for svc in captain-offline captain-online captain-command
    rm -rf $svc/_config
    cp -r config $svc/_config
end

# --- Step 6: Rebuild affected services (no-cache to bust COPY _config/ layer) ---
dco build --no-cache captain-online captain-command
dco up -d

# --- Step 7: Wait for containers to be healthy (~30 s), then bootstrap ---
dco ps
# All services must show "Up" (healthy) before running bootstrap.
# If any service shows "Exit" or "Restarting", read logs before proceeding:
#   dco logs --tail=40 captain-online

cmd-run bootstrap_production.py
# Expected: NKD line shows [OK] m=6 k=6 OO=0.8533 — confirms sl_dollars_fixed=1025 is in D00.

# --- Step 8: Post-deploy validation gates ---

# Gate A — D00 NKD locked_strategy: sl_dollars_fixed, is_nkd_trail, phase_b_buffer
curl -s -G "http://localhost:9000/exec" \
    --data-urlencode "query=SELECT locked_strategy FROM p3_d00_asset_universe WHERE asset_id='NKD' LATEST ON last_updated PARTITION BY asset_id" \
    | jq -r '.dataset[0][0]' \
    | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print('sl_dollars_fixed=', d.get('sl_dollars_fixed'), '| is_nkd_trail=', d.get('is_nkd_trail'), '| trail_phase_b_buffer_dollars=', d.get('trail_phase_b_buffer_dollars'))"
# Expected: sl_dollars_fixed= 1025 | is_nkd_trail= True | trail_phase_b_buffer_dollars= 1000

# Gate B — No stale open positions (clean slate)
docker exec captain-system-redis-1 redis-cli -a "$REDIS_PASSWORD" --no-auth-warning \
    HGETALL captain:open_positions
# Expected: empty output

# Gate C — F2 sanity check inside the live container (proves B1 is active)
dco exec -T captain-command python3 -c "
from captain_command.blocks.b1_core_routing import sanitise_for_api
signal = {
    'asset': 'NKD', 'direction': -1, 'size': 1,
    'tp_level': 60680, 'sl_level': 61805,
    'is_nkd_trail': True, 'tp_dollars': 4450, 'snapped_d_init': 1025.0,
    'jitter_x': 0.5, 'jitter_y': 1, 'jitter_j': 10.0,
    'signal_id': 'TEST', 'user_id': 'primary_user',
    '_context': {'entry_price': 61600},
    'per_account': {'21855714': {'contracts': 1}},
}
sanitised = sanitise_for_api(signal, '21855714', signal['per_account']['21855714'])
print('is_nkd_trail in sanitised?', 'is_nkd_trail' in sanitised)
print('tp_dollars in sanitised?', 'tp_dollars' in sanitised)
print('snapped_d_init in sanitised?', 'snapped_d_init' in sanitised)
print('jitter_j in sanitised?', 'jitter_j' in sanitised)
print('Total keys:', len(sanitised))
"
# Expected: all 4 lines True, Total keys: 19
# If any line is False — B1 is NOT active. Do NOT open the APAC session.

# Gate D — NKD trail log check (run only AFTER the first NKD trade fires post-deploy)
# Uncomment and run when a position is open:
# dco logs captain-online 2>&1 | grep "ON-B7B-NKD"
# Expected: "modify OK signal=..." lines per poll; NO "is_nkd_trail=False" lines.

# --- Step 9: Final confirmation ---
echo ""
echo "================================================================"
echo "=== BATCH 4 DEPLOY COMPLETE ON THIS TOWER ==="
echo "================================================================"
echo ""
echo "Changes now active:"
echo "  B1 (c23b68b) F2+F3: NKD trail-control fields thread end-to-end"
echo "    sanitise_for_api -> _auto_execute_signal -> _handle_taken_skipped"
echo "    Trail block (b7b_nkd_trail) now engages on every NKD TAKEN."
echo "  B2 (441671d) F4: Orphan fallback TP guarded out after SL-fail flatten"
echo "    No more orphan LIMIT orders after emergency flatten on bracket failure."
echo "  B3 (6349e33) F5/8.3: Trail observability improvements"
echo "    INFO log fires if NKD position skipped due to is_nkd_trail=False."
echo "    CRITICAL alert NKD_TRAIL_JITTER_MISSING fires on Isaac if jitter regresses."
echo ""
echo "Next: run these same steps on Isaac tower."
echo "Isaac-tower gate (Step 4): INSTANCE_PARITY must return 1."
echo "================================================================"
```

---

## 6. Validation gates (for this batch document)

1. **Regression test passes:** The Section 3 command runs with all 233 tests green and per-file counts matching the expected table. If any count diverges, stop and diagnose — do not patch the runbook or commit.

2. **Runbook diff applies cleanly:** Steps §2a–§2e are inserted after the existing step 2 in `apac-nkd-pre-market-checklist.md`. The GO/NO-GO summary gains a new checkbox (item 16) for the F2 sanity check. All existing step numbers (3–18) are unchanged.

3. **Tower deploy block is fish-clean:** Visual review confirms:
   - No `&&` chains (use `; and`)
   - No `$(...)` command substitution (use `(...)`)
   - All `for` loops end with `end` (not `done`)
   - All `type -q name; or function name ... end` preamble guards are present
   - No bash heredocs
   - All `apt install` calls use `-y` (non-interactive)
   - Tower-side validation can be performed with: `fish --no-execute -c "(paste block)"` on a tower with fish installed.

---

## 7. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Regression on non-NKD assets from B1 allow-list expansion** | Low | HIGH | Full 17-file suite includes non-NKD regression tests (`test_sanitise_for_api_non_nkd_signals_preserve_original_13_fields`, `test_taken_skipped_non_nkd_position_jitter_remains_none`). Gate: all 233 tests green before any tower deploy. |
| **Runbook drift between Nomaan and Isaac towers** | Low | HIGH | SHA-parity check (§5 Step 2) blocks deploy if towers diverge. Both towers must pass identical post-deploy gates A/B/C before the session opens. |
| **Operator skips the F2 empirical confirmation (step 2a)** | Medium | HIGH | Step 2a is now inserted at T−60 before D26 and compliance checks. It runs in 5 s. Gate C of the deploy runbook runs the same script inside the live container immediately after rebuild, providing a second gate. |
| **Isaac tower INSTANCE_PARITY misconfigured** | Low | MEDIUM | Explicit Isaac-tower-only gate at §5 Step 4. If it returns blank or `"0"`, deploy is blocked until `.env` is corrected. Effect if missed: J=0 on Isaac (TP at exact $4,450, not jittered) — no rejection or loss, but anti-copy-trade spec violated. |
| **Config sync skipped (`_config/` stale)** | Low | MEDIUM | Gate A checks `sl_dollars_fixed` in D00 after `bootstrap_production.py`. A stale `_config/` would produce an old value. The `grep` check in Step 6 comment reminds the operator. |
| **Test count mismatch due to test-discovery drift** | Very low | LOW | Expected count table is built from live `--collect-only` counts at Batch 4 authoring time. If new tests were added outside the batch plan, the table will diverge and alert the executing agent. |

---

## 8. Completion checklist

> Executing agent ticks each box as the step completes. All items must be ticked before the final operator hand-off.

### Pre-flight
- [x] B1 commit `c23b68b` confirmed on `origin/main` and `multi-user/main` — `git log --oneline -5 origin/main` shows B1 code commit
- [x] B2 commit `441671d` confirmed on `origin/main` and `multi-user/main`
- [x] B3 commit `6349e33` confirmed on `origin/main` and `multi-user/main`
- [x] HEAD at `6349e33` (B3) on dev host before this batch; parity confirmed

### Regression test (§3)
- [x] All 17 test files collected and run via the Section 3 command
- [x] Per-file counts match expected table — see result log below
- [x] Zero failures, zero errors
- [x] Pre-existing stale test `test_single_poll_jumping_0_to_3000_lands_in_phase_b_midpoint` (C14 regression, left from before B1/B2/B3) updated in this batch to reflect step-ladder reality: at pnl=$3,000 the phase is C with buffer=$450 — renamed `test_single_poll_jumping_0_to_3000_lands_in_phase_c`

### Regression test result log

| Test file | Expected | Actual | Status |
|---|---|---|---|
| `test_command_sanitise.py` | 15 | 15 | PASS |
| `test_b1_core_routing_decimal_log.py` | 4 | 4 | PASS |
| `test_b3_api_adapter_sltp.py` | 15 | 15 | PASS |
| `test_b6_signal.py` | 12 | 12 | PASS |
| `test_b7b_nkd_trail.py` | 48 | 48 | PASS |
| `test_b7b_isaac_jitter_stress.py` | 49 | 49 | PASS |
| `test_b7b_external_close.py` | 4 | 4 | PASS |
| `test_b7b_fast_crossing_multiple_boundaries.py` | 3 | 3 | PASS |
| `test_b7b_stale_quote_skips_modify.py` | 4 | 4 | PASS |
| `test_nkd_jitter_lifecycle.py` | 4 | 4 | PASS |
| `test_userstream_bracket_capture.py` | 13 | 13 | PASS |
| `test_b12_compliance_modify_check.py` | 8 | 8 | PASS |
| `test_marketstream_nkd_persistence.py` | 9 | 9 | PASS |
| `test_b7_time_exit_nkd_exemption.py` | 5 | 5 | PASS |
| `test_bootstrap_nkd_trail_fields.py` | 21 | 21 | PASS |
| `test_tick_snap_outward.py` | 12 | 12 | PASS |
| `test_nkd_replay_22h.py` | 7 | 7 | PASS |
| **TOTAL** | **233** | **233** | **ALL GREEN** |

### Runbook patch (§4)
- [x] §2a (F2 sanity check) added to `docs2/runbooks/apac-nkd-pre-market-checklist.md` after step 2 (line 51)
- [x] §2b (D34 expectation table) added (line 91)
- [x] §2c (GUI Trade panel expectations) added (line 114)
- [x] §2d (F4 orphan-TP expectation) added (line 127)
- [x] §2e (F5/§8.3 log signatures) added (line 139)
- [x] GO/NO-GO summary updated with item 16 (F2 sanity check gate) — "All 16 boxes checked = GO"
- [x] Existing step numbers 3–18 unchanged; table headings and quick-roll commands untouched

### Deploy block (§5)
- [x] Fish syntax verified: no `&&`, no `$(...)`, no `done`, no heredocs
- [x] Helper preamble includes `type -q` guards for all 4 helpers (`dco`, `cap-run`, `online-run`, `cmd-run`)
- [x] `git remote get-url multi-user … or git remote add` idempotency present (Step 1)
- [x] SHA-parity check (Step 2) precedes all destructive steps
- [x] No-open-position Redis gate (Step 3) present
- [x] Isaac-tower-only `INSTANCE_PARITY` gate (Step 4) present and labelled "skip on Nomaan tower"
- [x] Config sync loop uses `for svc in ...; end` fish syntax (Step 5)
- [x] `dco build --no-cache captain-online captain-command` then `dco up -d` (Step 6)
- [x] `cmd-run bootstrap_production.py` present (Step 7)
- [x] All 4 post-deploy gates (A/B/C/D) present and in order (Step 8)
- [x] Final `echo` summary in Step 9 lists all three batch changes with SHAs

### Commit + push
- [x] Regression suite ran green on dev host — **233 passed / 0 failed / 0 errors** in 1.87 s
- [x] Single atomic commit with conventional-commits message `docs(runbook+tracking): post-fix pre-market gates and tower deploy runbook`
- [x] `git push origin HEAD` — succeeded (`6349e33..a7ac6ba  HEAD -> main`)
- [x] `git push multi-user HEAD` — succeeded (`6349e33..a7ac6ba  HEAD -> main`)
- [x] SHA parity confirmed: local == `origin/main` == `multi-user/main` → `OK: both remotes synced`
- [x] Commit SHA (B4 main): `a7ac6babd770ef26e59510f6ec35658df317a353` (short: `a7ac6ba`)
- [x] Commit SHA (B4 checklist): `43c53cede6e7ca2ba89d2ba72ade1fa38c7ee667` (short: `43c53ce`)

```
local:      43c53cede6e7ca2ba89d2ba72ade1fa38c7ee667
origin:     43c53cede6e7ca2ba89d2ba72ade1fa38c7ee667
multi-user: 43c53cede6e7ca2ba89d2ba72ade1fa38c7ee667
OK: both remotes synced
```

### Operator sign-off (post-tower-deploy)
- [ ] Nomaan tower: Gates A/B/C all pass; Step 9 echo printed
- [ ] Isaac tower: `INSTANCE_PARITY=1` confirmed (Step 4); Gates A/B/C all pass; Step 9 echo printed
- [ ] First NKD trade post-deploy: D34 has ≥1 row within 30 s of fill
- [ ] First NKD trade: `modify OK signal=…` log lines visible in `captain-online`
- [ ] First NKD trade: NO `is_nkd_trail=False` log lines in `captain-online`
- [ ] Isaac tower first NKD trade: `jitter_j` in D34 is non-zero AND no `NKD_TRAIL_JITTER_MISSING` alert in `captain:alerts`

---

## 9. Cross-references

- Audit (primary source): [`REJECTED_ORDERS_AUDIT.md`](REJECTED_ORDERS_AUDIT.md) §0 TL;DR, §4.3 (F2 empirical script), §10 (post-session checklist)
- Build plan: [`BUILD_PLAN.md`](BUILD_PLAN.md) §5 "Batch 4"
- Batch 1 plan: [`BATCH_1_F2_F3_TRAIL_FORWARDING.md`](BATCH_1_F2_F3_TRAIL_FORWARDING.md) — F2/F3 code changes (commit `c23b68b`)
- Batch 2 plan: [`BATCH_2_F4_ORPHAN_TP.md`](BATCH_2_F4_ORPHAN_TP.md) — F4 guard clause (commit `441671d`)
- Batch 3 plan: [`BATCH_3_F5_OBSERVABILITY.md`](BATCH_3_F5_OBSERVABILITY.md) — F5/§8.3 observability (commit `6349e33`)
- Pre-market runbook: [`docs2/runbooks/apac-nkd-pre-market-checklist.md`](../../../../runbooks/apac-nkd-pre-market-checklist.md) — patched in this batch
- Day-2 plan (C14/C15/C16): [`docs2/quick-fixes/NKD_Pivot/day_2/PLAN.md`](../PLAN.md) §4 (deploy ordering)
- Workspace rules: [`.cursor/rules/captain-deploy-and-tower-discipline.mdc`](../../../../../.cursor/rules/captain-deploy-and-tower-discipline.mdc)

---

**End of Batch 4 plan.**
