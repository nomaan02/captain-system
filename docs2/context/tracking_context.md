# Captain System — Session Tracking Context

> **Purpose.** Rolling trail of records for cross-agent context handoff. New `/record` entries
> are **prepended** at the top of `## Records`. The newest entry is always the next agent's
> starting point. Older entries provide history.
>
> **How to use.** When you start a new agent chat, paste:
> *"Read `docs2/context/tracking_context.md` and pick up from the most recent record."*

---

## Active Issue

**APAC NKD signal cards never appeared in the GUI overnight 2026-04-30 → 2026-05-01,
AND captain-offline is crashing on every weekly D4 diagnostic run with a NULL-pnl
TypeError that yesterday's decimal sweep missed.** Tower 1 confirmed three blockers:
(1) `captain-offline` `compute_d4` crashes on `float(None)` at `b9_diagnostic.py:451`
because both ternary branches were identical and neither handled `pnl IS NULL` rows
in P3-D03; (2) Tower 1 doesn't have the `multi-user` remote configured; (3) tower
shell doesn't inherit `$REDIS_PASSWORD` so `redis-cli -a` AUTH-fails. All three are
now patched and the rule file `.cursor/rules/captain-deploy-and-tower-discipline.mdc`
§5 has the lessons-learned entries. Tower 1 still needs to pull post-fix and re-run
Steps 2-3 of the investigation playbook.

---

## Investigation Playbook — Pre NY Open

Run these on **Tower A** first (fish shell), then mirror on **Tower B**. Every command
assumes the standard helpers are loaded (see `docs2/quick-fixes/pnl_miscalculations/PRE_MARKET_VALIDATION.md`
§Prerequisites). The **dependency-preamble** at the top of the first block installs anything
the tower might be missing.

### Step 0 — Dependency preamble (fish, idempotent)

```fish
# 0a. Confirm helpers are defined; if not, paste them now.
type -q dco; or function dco; docker compose -f docker-compose.yml -f docker-compose.local.yml $argv; end
type -q cap-run; or function cap-run; set -l s $argv[1]; set -l rest $argv[2..-1]; \
    docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T -e PYTHONPATH=/app captain-offline python /captain/scripts/$s $rest; end
type -q online-run; or function online-run; set -l s $argv[1]; set -l rest $argv[2..-1]; \
    docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T -e PYTHONPATH=/app captain-online python3 /app/$s $rest; end
type -q cmd-run; or function cmd-run; set -l s $argv[1]; set -l rest $argv[2..-1]; \
    docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T -e PYTHONPATH=/app captain-command python3 /app/$s $rest; end

# 0b. Tower-side prerequisites. None of these are interactive on second run.
command -v jq         > /dev/null 2>&1; or sudo apt update; and sudo apt install -y jq
command -v docker     > /dev/null 2>&1; or echo "docker missing — fix before continuing"
command -v redis-cli  > /dev/null 2>&1; or sudo apt install -y redis-tools
# ripgrep optional; the runbook uses POSIX grep -E so towers without rg still work.

# 0c. Confirm tower is current.
cd ~/captain-system
git fetch origin
git fetch multi-user
set -l current (git rev-parse HEAD)
set -l origin_head (git rev-parse origin/main)
echo "tower HEAD:      $current"
echo "origin/main:     $origin_head"
echo "multi-user/main: "(git rev-parse multi-user/main)
test "$current" = "$origin_head"; and echo "OK: tower is on origin/main"; or echo "STALE: pull required"
```

**Pass:** All three SHAs are identical AND match `6a11c39` (or whatever HEAD is the moment
you read this — confirm against the local push log).
**Fail:** SHAs differ → `git pull origin main --ff-only` then `dco up -d --build`.

---

### Step 1 — Container health + last 24h log volume

```fish
dco ps
echo "---"
# How much logging volume each container produced in the last 24h
for svc in captain-offline captain-online captain-command captain-gui
    set -l n (dco logs --since 24h $svc 2>&1 | wc -l)
    echo "$svc: $n lines (24h)"
end
```

**Pass:** All 9 services `Up` (or `Up (healthy)`). All four pipeline containers should
have non-trivial log volume.
**Fail:** A container `Restarting` → grab its last 200 lines and start your investigation
there. A container with 0 24h lines is hung; restart it.

---

### Step 2 — Hunt for fresh `TypeError` and decimal/float crashes (24h window)

```fish
# captain-online — the failure site of yesterday's NY/APAC open
dco logs --since 24h captain-online 2>&1 \
    | grep -iE "TypeError|decimal.*float|float.*decimal|unsupported operand|InvalidOperation|ConversionSyntax" \
    | head -40

# captain-command — reconciliation + auto-execute path
dco logs --since 24h captain-command 2>&1 \
    | grep -iE "TypeError|decimal.*float|RECONCILIATION_FAILURE|SIGNAL_PUBLISH_FAILED|AUTO-EXECUTE.*fail|400|429|500" \
    | head -40

# captain-offline — learning loop
dco logs --since 24h captain-offline 2>&1 \
    | grep -iE "TypeError|decimal.*float|unsupported operand" \
    | head -40
```

**Pass:** Zero matches across all three. Yesterday's fixes hold.
**Fail:** Any match — paste the traceback into the next `/record` entry, the error
location pinpoints the next bug.

---

### Step 3 — APAC-specific B6 forensics (the actual reported failure)

The APAC session evaluates at ~17:55 ET. NKD is the only APAC asset. Every B6 invocation
emits one `ON-B6-SUMMARY` line per user-session. If APAC ran but produced no signal,
exactly ONE of these things is true:

1. The session never even started — orchestrator skipped it (no `Phase B` line).
2. B8 OR-tracker never registered the OR window for NKD.
3. The OR window registered but never produced a breakout (price stayed inside OR).
4. B6 received recommended trades but skipped them (zero contracts, missing direction, etc.).
5. B6 published, but Redis stream is empty (publisher → consumer mismatch).

This sequence isolates which of the five is true:

```fish
# 3.1  Did APAC session even fire?
dco logs --since 24h captain-online 2>&1 \
    | grep -iE "session=3|session_id=3|APAC|NKD" \
    | head -40

# 3.2  Did the OR window register & complete for NKD?
dco logs --since 24h captain-online 2>&1 \
    | grep -iE "OR FORMING|OR COMPLETE|OR BREAKOUT|NKD" \
    | head -30

# 3.3  Did B6 fire? Look for the diagnostic summary the team added on Apr 28.
dco logs --since 24h captain-online 2>&1 \
    | grep -E "ON-B6-SUMMARY|ON-B6-SKIP|ON-B6:" \
    | head -40

# 3.4  Did B6 publish to Redis stream?
dco logs --since 24h captain-online 2>&1 \
    | grep -iE "SIGNAL_PUBLISH_FAILED|Failed to publish|XADD|stream:signals|captain:signals" \
    | head -30

# 3.5  What does Redis itself say about the APAC signal stream right now?
docker exec captain-system-redis-1 redis-cli -a "$REDIS_PASSWORD" --no-auth-warning \
    XLEN captain:signals:primary_user
docker exec captain-system-redis-1 redis-cli -a "$REDIS_PASSWORD" --no-auth-warning \
    XREVRANGE captain:signals:primary_user + - COUNT 5
```

**How to read this:**

| Step 3.1 result | Meaning |
|---|---|
| No matches at all | APAC session was never scheduled — check `config/session_registry.json` for NKD's APAC entry. |
| `Phase B starting … session=3` but no further activity | Session started but B1 returned zero assets — check D00 NKD `captain_status` (Step 5). |
| `Phase B starting … session=3` AND `Phase B: generated …` | Pipeline ran. Check 3.2-3.4. |

| Step 3.3 result | Meaning |
|---|---|
| `ON-B6-SUMMARY user=primary_user session=3 recommended=0 built=0 …` | B5C/B5B filtered out NKD upstream — could be quality gate, circuit breaker, capacity, or correlation. |
| `recommended=N built=0` (N ≥ 1) | Zero-contracts skip or unresolved direction — `ON-B6-SKIP` lines show which. |
| `recommended=N built=N` but step 3.4 shows `Failed to publish` | Redis publish path broken. |
| **No `ON-B6-SUMMARY` line at all when 3.1 confirms session ran** | The diagnostic logging was never deployed to this tower. Pull and rebuild. |

| Step 3.5 result | Meaning |
|---|---|
| `XLEN` = 0 even after 3.3 shows `built ≥ 1` | Stream key mismatch (consumer reading wrong key) OR publish silently no-op'd. |
| `XLEN` ≥ 1 with recent entry | B6 worked → bug is on Command / GUI side. Move to Step 4. |

---

### Step 4 — If signals reached Redis but never reached the GUI

```fish
# 4.1  Did command-block consume the stream?
dco logs --since 24h captain-command 2>&1 \
    | grep -iE "signal batch received|XREADGROUP|consumer group|signals:primary_user" \
    | head -30

# 4.2  Was the signal sanitised+broadcast on the GUI websocket?
dco logs --since 24h captain-command 2>&1 \
    | grep -iE "SIGNAL_GENERATED|sanitise_for_gui|broadcast_signal|websocket" \
    | head -30

# 4.3  Did the GUI websocket clients see anything? (React app SignalCards + dashboardStore)
dco logs --since 24h captain-gui 2>&1 | tail -100
```

If the signal reached Command but not the GUI, the bug is in `b1_core_routing.sanitise_for_gui`
or the GUI websocket. If Command never consumed the stream, the consumer-group offset
might be wrong.

---

### Step 5 — D00/D08 sanity for NKD specifically

These three queries (run in QuestDB web console at `http://<tower-ip>:9000`) prove NKD's
data preconditions are healthy:

```sql
-- 5.1  NKD must be ACTIVE for APAC and have point_value
SELECT asset_id, captain_status, session_hours, point_value, tick_size
FROM p3_d00_asset_universe
WHERE asset_id = 'NKD'
LATEST ON last_updated PARTITION BY asset_id;

-- Pass: captain_status = 'ACTIVE', session_hours JSON contains "APAC", point_value = 5

-- 5.2  TSM state for the trading account
SELECT account_id, name, classification, current_balance,
       starting_balance, max_drawdown_limit, current_drawdown,
       max_daily_loss, daily_loss_used
FROM p3_d08_tsm_state
LATEST ON last_updated PARTITION BY account_id;

-- Pass: numeric columns non-NULL, max_drawdown_limit > current_drawdown,
--       max_daily_loss > daily_loss_used.

-- 5.3  Most recent NKD signal log (if APAC published anything ever)
SELECT user_id, session_id, asset, direction, contracts, ts
FROM p3_d17_signal_output_log
WHERE asset = 'NKD'
ORDER BY ts DESC
LIMIT 5;
```

---

### Step 6 — Definition of "ready for NY open"

NY open is safe to enable when **all** of these are green on **both** towers:

- [ ] Step 0 SHA parity confirmed
- [ ] Step 1 all containers Up
- [ ] Step 2 zero TypeError matches across the 3 pipeline containers
- [ ] Step 3.5 OR Step 5.3 shows ≥ 1 published signal in the last 24h (proof B6 is alive)
- [ ] `online-run dry_run_phase_a.py 1` produces `VERDICT: Phase A would produce signals.`
- [ ] `online-run dry_run_phase_a.py 3` produces the same for APAC (NKD)
- [ ] `cap-run verify_schema_drift.py` exits 0
- [ ] No tower has `M` (modified) tracked files in `git status`

If any of those is red, **do not enable AUTO_EXECUTE for the next session**.

---

## Records

### 2026-05-01 12:35 BST — Tower 1 first-run findings: 3 blockers patched

**Status:** Patching · Tower 1 needs to pull then re-run Steps 2-3

**What we know — confirmed:**
- Tower 1 ran the Step 0 preamble. Output revealed three independent issues:
  1. **`captain-offline` is crashing** with `TypeError: float() argument must be a string or a real number, not 'NoneType'`. Source: `captain-offline/captain_offline/blocks/b9_diagnostic.py:451`. Original code `float(pnl) if not isinstance(pnl, Decimal) else float(pnl)` had identical ternary branches AND no `None` guard. P3-D03 has open-trade rows where `pnl IS NULL`, so every D4 dimension run crashed. **Fixed** in this session: routed through `shared.decimal_boundary.to_float` and `continue` on `None`.
  2. **Tower 1 doesn't have the `multi-user` remote configured** (`fatal: 'multi-user' does not appear to be a git repository`). The Step 0 SHA-parity check therefore can't compare against `multi-user/main`. **Fixed** by adding an idempotent `git remote add multi-user ...` line to the dependency preamble in this rule file's lessons-learned section.
  3. **`redis-cli -a "$REDIS_PASSWORD"` AUTH-failed** because the tower's fish shell doesn't inherit the env var the containers use. **Fixed** by prepending `set -gx REDIS_PASSWORD (grep '^REDIS_PASSWORD=' ~/captain-system/.env | cut -d= -f2)` before any `redis-cli` call.
- B8 OR-tracker is alive: `OR tracker registered: NKD (APAC) OR 18:00:00–18:05:00 on 2026-05-01` was logged at 05:55:01 UTC. So the orchestrator IS scheduling APAC for tonight.
- MGC OR window completed with `range=0.0000` (`high=4572.4000 low=4572.4000`, **only 1 tick captured in the 5-minute window**). MGC then triggered `OR BREAKOUT SHORT` because `4572.2000 < 4572.4000`. This is a separate concern: a degenerate OR with one tick and zero range. Not the cause of the APAC failure but worth flagging.

**What we DON'T yet know:**
- Whether the `compute_d4` crash was the actual root cause of last night's APAC silent failure, or whether it merely co-existed alongside it. The crash is in offline (learning loop), APAC signals come from online (B6) — they're independent processes. But if offline crashed during APAC evaluation, downstream learning state for the next session could be stale.
- Whether `captain-offline` was in a crash-restart loop for the entire APAC window.
- The actual `ON-B6-SUMMARY` content for last night's APAC session — Tower 1 still needs to run Step 3.3 after pulling the fix.
- Whether Tower 2 also lacks the `multi-user` remote (likely yes — same provisioning).

**Where we're at:**
- Patch committed to `main` and pushed to BOTH remotes.
- Cursor rule `.cursor/rules/captain-deploy-and-tower-discipline.mdc` §5 has the three new "Known failure modes" entries with corrected commands.
- Tower 1 (and Tower 2) need to (a) add the `multi-user` remote, (b) `git pull origin main --ff-only`, (c) `dco up -d --build captain-offline`, (d) re-run Step 2 to confirm no fresh `TypeError` after rebuild, then (e) Step 3 for APAC forensics on last night's session.

**Next steps:**
1. Tower-A operator runs the corrected preamble (with the `git remote add multi-user` and `set -gx REDIS_PASSWORD` lines from rule file §5).
2. `git pull origin main --ff-only` then `dco up -d --build captain-offline` to load the b9 fix.
3. Confirm the offline crash is gone: `dco logs --since 5m captain-offline 2>&1 | grep -iE "TypeError|compute_d4"` returns nothing.
4. Run Step 3 of investigation playbook against last night's APAC session.
5. Mirror everything on Tower B.
6. Run `online-run dry_run_phase_a.py 1` (NY) and `online-run dry_run_phase_a.py 3` (APAC) on both towers — both must print `VERDICT: Phase A would produce signals.` before NY open.

**Useful refs:**
- `captain-offline/captain_offline/blocks/b9_diagnostic.py:441-454` — the `compute_d4` D4 fix
- `.cursor/rules/captain-deploy-and-tower-discipline.mdc` §5 — three lessons-learned with corrected commands
- `shared/decimal_boundary.py:72` — `to_float(value, *, default=0.0)` (None-safe)
- Investigation playbook above (Steps 0-6)

---

### 2026-05-01 12:25 BST — Pre-NY-open consolidation triage (this session)

**Status:** Investigating · 2h to NY open · APAC silent overnight

**What we know — confirmed:**
- Yesterday (Apr 30) Phase 1-4 of decimal-boundary work landed on `main`:
  `03de644` (B8 OR-tracker WAITING expiry) → `1910f71` (boundary helpers + B6 type purity,
  the explicit fix for the NY/APAC `TypeError: decimal.Decimal - float` at
  `b6_signal_output._build_per_account`) → `9659b4c` (helper consolidation + closed
  silent reconciliation gap with CRITICAL log + GUI alert) → `5681fb6` (offline replay
  + b3_pseudotrader) → `dbe550b` (CI lint guard).
- Then `2169e7c` (B7 monitor + shadow monitor, "Bug C"), `8fa7a54` (e2e flow tests),
  `7b254bd` (rg→grep -E), `61f0ab2` (SOD reconciliation + GUI invalid-column queries),
  `a3c6063` (TSM auto-link Trading Combine fail-closed), `6a11c39` (D16 phase 2 account-switch
  detection — current HEAD).
- `origin/main` and `multi-user/main` are both at `6a11c39`. Local repo is at `6a11c39`.
- Local working tree shows `M` against `b6_signal_output.py` and `orchestrator.py` —
  **but `git diff --stat` is exactly 1487/1487 lines (every line "changed")**, which is
  pure LF↔CRLF line-ending churn from a non-LF editor opening the file. **NOT real code
  drift.** Confirm with `git diff -b -w | wc -l` returning 0 before discarding.
- The B6 ON-B6-SUMMARY diagnostic from memory entry `#3164` (commit `7da97e4`) is
  present in the local file (line 191) but `7da97e4` does not appear in `git log` of
  either remote. Most likely it was rolled into `1910f71` during the boundary fix. The
  log line IS deployed.

**What we DON'T yet know:**
- Whether last night's APAC NKD session actually ran B1→B5C at all (Step 3.1 above
  answers this).
- Whether NKD's D00 `captain_status` is ACTIVE for APAC (Step 5.1).
- Whether the towers actually pulled past `6a11c39` before the APAC evaluation (Step 0).
- Whether there is a second silent-skip path inside B6 for `recommended=0` cases that
  the Apr 28 diagnostic wired up but didn't cover (Step 3.3).
- Whether the consumer group on `captain:signals:primary_user` advanced beyond an old
  offset, causing Command to think there are no new entries (Step 4.1).

**Where we're at:**
- Investigation playbook above is the runbook for the next 2 hours.
- Run Steps 0-3 first. The branch point at Step 3.3 / 3.5 tells us which of five
  failure modes happened.
- After triage, fix forward, push to **both** remotes per
  `.cursor/rules/captain-deploy-and-tower-discipline.mdc`, towers pull, re-run dry runs.

**Next steps (sequential):**
1. Tower-A operator runs Step 0 → confirm SHA parity.
2. Run Steps 1-3 → identify which of the five failure modes triggered overnight.
3. Branch into Step 4 if signals reached Redis, or Step 5 if D00/D08 looks suspect.
4. Capture the exact log/SQL output that confirms root cause; paste into the next
   `/record` entry.
5. Patch on a fix branch → push to BOTH remotes → towers pull → re-run dry runs for
   sessions 1, 2, 3 → enable `AUTO_EXECUTE` for NY open.

**Useful refs:**
- `docs2/quick-fixes/fixing-decimal-errors/EXECUTION_SUMMARY.md` — Phase 1-4 commit map
- `docs2/quick-fixes/fixing-decimal-errors/TOWER_VALIDATION_RUNBOOK_FINAL.md` — full tower runbook
- `docs2/quick-fixes/pnl_miscalculations/PRE_MARKET_VALIDATION.md` — Tier 1/2/3 dry-run guide
- `captain-online/captain_online/blocks/b6_signal_output.py:191` — `ON-B6-SUMMARY` log
- `captain-online/captain_online/blocks/b6_signal_output.py:303` — `_build_per_account` (was the Apr 30 NY-open crash site)

---
