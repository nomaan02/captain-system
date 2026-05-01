# Captain System — Session Tracking Context

> **Purpose.** Rolling trail of records for cross-agent context handoff. New `/record` entries
> are **prepended** at the top of `## Records`. The newest entry is always the next agent's
> starting point. Older entries provide history.
>
> **How to use.** When you start a new agent chat, paste:
> *"Read `docs2/context/tracking_context.md` and pick up from the most recent record."*

---

## Active Issue

**NY traded, post-trade writeback CRASHED.** Trades fired correctly through the
full pipeline (B6 → Redis → Command → broker, multiple `ON-B6-SUMMARY built=1`
lines for ZN/ZB/M2K/MNQ; broker bracket order placement worked). On position
TP_HIT, `b7_position_monitor._write_trade_outcome` hit a NEW bug:
`psycopg2.DatabaseError: inconvertible types: DECIMAL(8,0) -> SYMBOL [from=cast,
to=account_id]`. Root cause: `shared/decimal_json.loads_decimal._coerce` over-
coerces every numeric-looking string to Decimal when reloading positions from
Redis — including `account_id="21855714"` which then trips the global psycopg2
DECIMAL cast adapter into emitting `cast('21855714' as DECIMAL(8,0))` against
the SYMBOL column. Patched at the boundary in `resolve_position` (str-coerce
account_id and mutate `pos["account"]` in-place). Tower must rebuild
captain-online to apply. NY OR window is over — rebuild safe now.

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


| Step 3.1 result                                           | Meaning                                                                                       |
| --------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| No matches at all                                         | APAC session was never scheduled — check `config/session_registry.json` for NKD's APAC entry. |
| `Phase B starting … session=3` but no further activity    | Session started but B1 returned zero assets — check D00 NKD `captain_status` (Step 5).        |
| `Phase B starting … session=3` AND `Phase B: generated …` | Pipeline ran. Check 3.2-3.4.                                                                  |



| Step 3.3 result                                                     | Meaning                                                                                               |
| ------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `ON-B6-SUMMARY user=primary_user session=3 recommended=0 built=0 …` | B5C/B5B filtered out NKD upstream — could be quality gate, circuit breaker, capacity, or correlation. |
| `recommended=N built=0` (N ≥ 1)                                     | Zero-contracts skip or unresolved direction — `ON-B6-SKIP` lines show which.                          |
| `recommended=N built=N` but step 3.4 shows `Failed to publish`      | Redis publish path broken.                                                                            |
| **No `ON-B6-SUMMARY` line at all when 3.1 confirms session ran**    | The diagnostic logging was never deployed to this tower. Pull and rebuild.                            |



| Step 3.5 result                             | Meaning                                                                       |
| ------------------------------------------- | ----------------------------------------------------------------------------- |
| `XLEN` = 0 even after 3.3 shows `built ≥ 1` | Stream key mismatch (consumer reading wrong key) OR publish silently no-op'd. |
| `XLEN` ≥ 1 with recent entry                | B6 worked → bug is on Command / GUI side. Move to Step 4.                     |


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

- Step 0 SHA parity confirmed
- Step 1 all containers Up
- Step 2 zero TypeError matches across the 3 pipeline containers
- Step 3.5 OR Step 5.3 shows ≥ 1 published signal in the last 24h (proof B6 is alive)
- `online-run dry_run_phase_a.py 1` produces `VERDICT: Phase A would produce signals.`
- `online-run dry_run_phase_a.py 3` produces the same for APAC (NKD)
- `cap-run verify_schema_drift.py` exits 0
- No tower has `M` (modified) tracked files in `git status`

If any of those is red, **do not enable AUTO_EXECUTE for the next session**.

---

## Records

### 2026-05-01 15:10 BST — NY traded; post-trade D03 writeback NEW crash on account_id Decimal-coercion

**Status:** Patching · CRITICAL · captain-online rebuild required

**What happened (good):**
- NY OR window 13:30–13:35 UTC fired correctly. B6 invoked for **M2K, ZN, ZB** with `ON-B6-SUMMARY user=primary_user session=1 recommended=1 built=1 below_threshold=0` per asset. `Phase B complete — all assets resolved`. Bracket orders placed at TopstepX. Yesterday's GUI silence and `_build_per_account` decimal bug are confirmed fixed in production.
- Shadow-monitor on the parity-split side resolved theoretical outcomes cleanly (ZN SL_HIT -$140.62, ZB SL_HIT -$125.00, MNQ TP_HIT +$181.50).

**What broke (bad — NEW bug, not in prior dashboard):**
- At 09:55:35 ET, the REAL position for account 21855714 (MNQ TP_HIT) tried to write back to D03. Crashed:
  ```
  psycopg2.DatabaseError: inconvertible types: DECIMAL(8,0) -> SYMBOL
  [from=cast, to=account_id]
  LINE 7: ...ECF8FD5BD6F', 'SIG-C07CAC7394C1', 'primary_user', cast('2185...
  ```
- Position monitor entered an **infinite retry loop** — every cycle re-attempts the same TP_HIT resolution and crashes (logs spam `Position monitor error: inconvertible types: DECIMAL(8,0) -> SYMBOL`).

**Root cause:**
- `shared/decimal_json.py:52-56` `loads_decimal._coerce`: aggressively wraps EVERY string in JSON output as `Decimal` if it parses as a number. Decision tree:
  - `"primary_user"` → letters → stays str ✓
  - `"SIG-C07CAC7394C1"`, `"TRD-..."` → letters → stays str ✓
  - **`"21855714"` (account_id) → all-numeric → becomes `Decimal("21855714")` ❌**
- Position dict goes through Redis (`captain:open_positions`) on creation and is read back when `monitor_positions` runs. Round-trip turns `account_id` from str into Decimal.
- `_write_trade_outcome` passes the Decimal account_id to `cur.execute(INSERT INTO p3_d03_trade_outcome_log)`.
- Global psycopg2 adapter at `shared/questdb_client.py:62-65` wraps every Decimal as `cast('<value>' as DECIMAL(<p>,<s>))`. account_id becomes `cast('21855714' as DECIMAL(8,0))`.
- D03's `account_id` column is **SYMBOL** type. QuestDB rejects: `inconvertible types: DECIMAL -> SYMBOL`.

**Trade implications:**
- ✅ MNQ broker order DID fill at TP — your $181.50 (gross) is in TopstepX.
- ❌ No D03 trade outcome row written for today's MNQ.
- ❌ No D16 capital silo update.
- ❌ No D23 circuit-breaker intraday update.
- ❌ No Redis stream publish to offline → Kelly / EWMA / DMA / BOCPD don't see the trade. **Learning loop starved for today's outcomes.**
- ❌ `open_positions` Redis cache never clears — orchestrator keeps trying to monitor an already-closed position.
- ⚠️ Tomorrow's NY SOD reconciliation may patch some of this from broker truth, but the regime/AIM context for today's trades is lost.

**What we DON'T yet know:**
- Whether `_update_capital_and_cb` and `_publish_trade_outcome` will also crash with the same shape after the boundary fix is applied (`_update_capital_and_cb` uses `account_id` as a SQL param at lines 535 + 580; `_publish_trade_outcome` passes `pos["account"]` into the Redis stream payload). Boundary fix mutates `pos["account"]` in-place so they should see the str — but unverified live.
- Whether other code paths read `account_id` from Redis and use it as a SYMBOL parameter elsewhere. Backlog: audit all call-sites of `pos.get("account")` and any consumer of `captain:open_positions`.
- Whether the orphaned positions in Redis cache will resolve cleanly on next monitor pass post-rebuild OR need manual cleanup.

**Where we're at:**
- Patch applied at `captain-online/captain_online/blocks/b7_position_monitor.py:328-336` (`resolve_position`): coerce `account_id` to str if it's not already, mutate `pos["account"]` in-place so downstream callees see str. 12-line diff.
- About to commit + push to both remotes, then operator rebuilds captain-online (NY OR is over — rebuild is safe).
- After rebuild, the next `monitor_positions` cycle should resolve the stuck MNQ position cleanly: D03 row written, D16 capital updated, D23 CB updated, Redis publish to offline succeeds.

**Next steps (sequential, immediate):**
1. Push fix to both remotes.
2. Tower operator: `git pull origin main --ff-only` then `dco up -d --build captain-online` (~2-3min downtime; safe — NY OR is past).
3. Watch captain-online logs for first successful `ON-B7: Position resolved — MNQ TP_HIT primary_user net_pnl=...` line. Confirms recovery.
4. Verify D03 row landed: `SELECT * FROM p3_d03_trade_outcome_log WHERE asset='MNQ' AND ts > dateadd('h', -2, now())`.
5. Verify Redis `open_positions` cache cleared: `XLEN captain:open_positions` (or HLEN — check hash type).
6. `/record` resolution.

**Backlog (post-market):**
- B8 (NEW): root-cause fix in `loads_decimal._coerce` — should NOT coerce all-numeric strings to Decimal. Either use a structural marker (`{"__type":"Decimal"}`) for round-trip Decimal fields, or whitelist known monetary keys.
- B9 (NEW): audit all call-sites of `pos.get("account")` and `pos["account"]` across captain-online + captain-command for the same Decimal-leak shape.
- B10 (NEW): `version_snapshot._enforce_max_versions:160` log spam — demote per-version line to DEBUG, keep summary at INFO.
- B11 (NEW): `UserStream TRADE/ORDER/POSITION: ...None None None` lines (from captain-online `__main__`) — broker payload parse failing? Same may explain `Commission data missing for account 21855714` warning. Investigate.
- (Plus all prior dashboard backlog: B1-B7.)

**Useful refs:**
- `captain-online/captain_online/blocks/b7_position_monitor.py:328-336` — patched site (12 new lines)
- `shared/decimal_json.py:32-59` — `loads_decimal` over-coercion site (root cause; backlog B8)
- `shared/questdb_client.py:62-65` — global Decimal psycopg2 adapter (works as designed; not the bug)

---

### 2026-05-01 13:35 BST — Bug-status dashboard for NY-open handoff

**Status:** Verifying · pipeline GO · live monitors armed · ~55m to NY OR

This entry is a single-read dashboard of every bug touched this session — what's
fixed, what's deployed, what's deferred. The next agent should read this first.

**FIXED + DEPLOYED to both towers (HEAD ≥ `2476d76`):**

| ID | Bug | Fix | File |
|----|-----|-----|------|
| F1 | `compute_d4` `TypeError: float() argument ... NoneType` on every weekly/monthly diagnostic — both ternary branches identical, no None-guard | route through `to_float`; `continue` on None | `captain-offline/.../b9_diagnostic.py:451-454` |
| F2 | Tower 1 missing `multi-user` remote — Step 0 SHA-parity check unusable | idempotent `git remote add multi-user …` documented in rule §5 | `.cursor/rules/captain-deploy-and-tower-discipline.mdc` |
| F3 | `redis-cli -a "$REDIS_PASSWORD"` AUTH-fail — fish shell doesn't inherit env | `set -gx REDIS_PASSWORD (grep …)` or `(docker exec … echo $REDIS_PASSWORD)` documented in rule §5 | (rule + lessons-learned) |

**FIXED but PATCH NOT YET LIVE on towers (HEAD `aeecf71`, towers should pull but NOT rebuild before NY close):**

| ID | Bug | Fix | File |
|----|-----|-----|------|
| F4 | `hmm_inference_block.py:94` — `prior_dict.get("last_session_slot_pnl", 0.0)` returns None if value explicitly set to None (vs key-absent); `float(None)` would crash HMM inference in B3 aggregation path | defensive raw-then-coerce | `captain-online/.../hmm_inference_block.py:94-95` |
| F5 | `b7_position_monitor.py:706` — D17 commission fallback `if row: float(row[0])` only checks row absence, not row[0] None | added `and row[0] is not None` | `captain-online/.../b7_position_monitor.py:705-706` |
| F6 | Decimal-boundary CI lint missed the `float(x) if not isinstance(x, T) else float(x)` no-op-ternary shape (the b9 bug pattern) | new `NOOP_TERNARY_RE` regex; catches `float()` and `Decimal()` variants with whitespace tolerance | `scripts/lint_decimal_boundary.py:58-72` |

**OPEN ISSUES — being monitored, not yet fixed:**

| ID | Bug | Status | When to revisit |
|----|-----|--------|-----------------|
| O1 | GUI signal cards never appeared yesterday during PRAC NY session despite trades placing on broker. Root cause attributed to `_build_per_account` Decimal/float crash now fixed in `1910f71`. Awaiting first live NY signal today for E2E validation. | Monitoring at NY OR window | NY OR window 13:30–13:35 UTC today |
| O2 | APAC silent overnight Apr 30 — B6 never invoked for `session_id=3`. P3-D17 has zero `signal_output_3_*` rows in 48h on either tower. Container recreates wiped relevant logs. Cannot reconstruct retroactively. | Deferred (user instruction: NY priority) | Tonight's APAC at 22:00 UTC — observe live |

**BACKLOG — ticketed, post-market priority order:**

| ID | Issue | Where | Risk |
|----|-------|-------|------|
| B1 | `B7→D03` trade-outcome writeback severed. F3 query confirms zero real Captain-placed trades in D03 in 48h on either tower (only synthetic `LEGACY-`, `BACKFILL-TEST-`, `SUM-` rows). | `b7_position_monitor` → `captain:trade_outcomes` → offline → D03 | Trades execute but post-trade learning starves |
| B2 | Captain-offline 12-file `float()` audit for None-safety: `b1_dma_update`, `b1_aim_lifecycle`, `b2_bocpd`, `b2_cusum`, `b3_pseudotrader`, `b4_injection`, `b5_sensitivity`, `b6_auto_expansion`, `b8_cb_params`, `b8_kelly_update`, `bootstrap`, `orchestrator` | (12 files) | Could crash post-trade learning loop on edge cases |
| B3 | `dry_run_command.py` false-negative — spawns new Python process via `docker exec`, inspects empty in-memory `_active_connections` instead of orchestrator's actual state | `captain-command/dry_run_command.py` | Misleads operators into believing adapter not registered |
| B4 | `B5C SOD not run` warnings persisted despite yesterday's `61f0ab2 fix(command): SOD reconciliation signature` claim. Fallback to live values is correct so non-blocking. | `captain-online/.../b5c_circuit_breaker.py` | Operational noise + L1/L2 fallback path |
| B5 | `b6_reports.py:272-273` — `float(aim_data.get("modifier", 1.0))` and `float(aim_data.get("dma_weight", 0))` unguarded against value-is-None | `captain-command/.../b6_reports.py` | Report-generation crash (operator-action only, not trading-path) |
| B6 | Container auto-restart this morning — captain-online + captain-command both restarted ~09:30-10:17 UTC today (no user action recalled). Cause unknown. Logs from prior life are gone. | `dco logs` history / journalctl | Could mask transient crashes |
| B7 | TSM live.json validation warning every startup (`Missing required field: starting_balance, max_drawdown_limit`). Documented as benign at `PRE_MARKET_VALIDATION.md:657` (live.json is for Live Funded accounts, current 150KTC auto-links to eval.json). | `b4_tsm_manager.load_all_tsm_files` | Operational noise |

**KEY COMMITS THIS SESSION:**

| SHA | Title | Files |
|-----|-------|-------|
| `0cfb4e8` | docs(context): tracking trail + /record skill + tower discipline rule | 3 (new) |
| `2476d76` | fix(b9_diagnostic): handle NULL pnl in compute_d4; doc tower lessons | 3 |
| `22d753b` | docs(context): NY-open clearance record — pipeline GO | 1 |
| `aeecf71` | fix(decimal): downstream None-safety patches + extend lint for no-op ternary | 4 |

**ENVIRONMENT SNAPSHOT (at handoff time):**

| Item | Value |
|------|-------|
| Local repo HEAD | `aeecf71` |
| `origin/main` | `aeecf71` (synced) |
| `multi-user/main` | `aeecf71` (synced) |
| Tower A image build SHA | `2476d76` (b9 fix) — needs pull but **no rebuild** before NY close |
| Tower B image build SHA | `2476d76` — same |
| AUTO_EXECUTE | `true` on both towers (LIVE 150KTC accounts) |
| Live monitors | 3 fish tabs/tower: online/command/redis-stream |
| GUI | Loaded in browser, WebSocket OPEN on both towers |

**Next steps (sequential, immediate):**
1. Tower operators: `cd ~/captain-system; git pull origin main --ff-only`. Verify `git rev-parse HEAD = aeecf71…`. **Do not rebuild containers.**
2. NY OR window 13:30–13:35 UTC: monitor 3 tabs + GUI on each tower per record `2026-05-01 13:10 BST` step ladder.
3. On first ON-B6-SUMMARY: paste tab-1/tab-2 lines + GUI screenshot status; `/record` the outcome (success or failure).
4. Post-NY-close: rebuild captain-online to load F4+F5 patches (`dco up -d --build captain-online`); re-run dry-runs to confirm; then start backlog B1→B7 in priority order.

**Useful refs:**
- `docs2/context/tracking_context.md` — this file (rolling trail)
- `.cursor/rules/captain-deploy-and-tower-discipline.mdc` — dual-remote push, tower scripts, lessons-learned protocol
- `.cursor/skills/record/SKILL.md` — `/record` skill
- `docs2/quick-fixes/fixing-decimal-errors/EXECUTION_SUMMARY.md` — Apr 30 commit map
- `docs2/quick-fixes/fixing-decimal-errors/TOWER_VALIDATION_RUNBOOK_FINAL.md` — full tower runbook
- `docs2/quick-fixes/pnl_miscalculations/PRE_MARKET_VALIDATION.md` — Tier 1/2/3 dry-run guide

---

### 2026-05-01 13:30 BST — Downstream-blocks decimal/None audit + 2 precautionary patches

**Status:** Patching · pushed to `main` both remotes · DO NOT REBUILD towers before NY close

**Trigger:** User flagged the b9 NULL-pnl traceback from last night's captain-offline log
(`2026-05-01 00:00:28 ERROR Monthly tasks error: float() argument must be a string or a real number, not 'NoneType'`)
and asked "are blocks downstream of B5C also covered? `dry_run_phase_a.py` only tests B1→B5C — what
else could be lurking?"

**What we know — confirmed:**
- The exact b9 traceback the user flagged is **already-fixed** by `2476d76`. Timestamp on the trace
  was 8 PM ET April 30, 11h before the patch landed; today's MONTHLY diagnostic ran clean
  (`overall=0.51-0.52, actions=17-18`).
- `dry_run_phase_a.py` covers B1→B5C in captain-online only. **B6, B7, B8 in captain-online; ALL of
  captain-command; ALL of captain-offline are not exercised by the dry-run.**
- The decimal-boundary lint guard (`scripts/lint_decimal_boundary.py`) catches the
  `r[N] or 0.0` antipattern but did **NOT** previously catch the `float(x) if not isinstance(x, T) else float(x)`
  no-op-ternary pattern that caused the b9 bug. **Now extended** to catch both shapes
  (`float()` and `Decimal()` variants, with whitespace tolerance).
- Repo-wide grep for `float(x) if not isinstance(x, …) else float(x)` returns **only the b9 site**
  (already fixed). The two other ternaries in this shape (`b4_kelly_sizing.py:168`, `b5_trade_selection.py:213`)
  have a different `else` branch (`else override` / `else pair`) and are **not** no-ops — they
  conditionally avoid redundant casting. Both are guarded by an upstream `if x is not None:` check.
- Repo-wide grep for unguarded `float(row[0])` against potentially-NULL columns: most call-sites
  ARE None-guarded (`if row and row[0] is not None`). Two trading-path edge cases were not:

| File | Line | Risk shape | Fixed |
|---|---|---|---|
| `captain-online/.../hmm_inference_block.py` | 94 | `float(prior_dict.get("last_session_slot_pnl", 0.0))` — `.get()` returns None if key set to None, not just on key-absent | ✅ defensive raw-then-coerce |
| `captain-online/.../b7_position_monitor.py` | 706 | `if row: return float(row[0]) * 2` — checks row absence, not row[0] None | ✅ `if row and row[0] is not None` |

**What we DON'T yet know:**
- Whether captain-offline blocks (b1_dma_update, b1_aim_lifecycle, b2_bocpd, b2_cusum, b3_pseudotrader,
  b4_injection, b5_sensitivity, b6_auto_expansion, b8_cb_params, b8_kelly_update) have similar
  unguarded `float()` calls. **Did not exhaustively audit** — outside the trading-path window for NY
  open. Backlog item: extend the audit to all 12 captain-offline files post-market.
- Whether the SOD-not-run warning has hidden monetary-coercion implications. Backlog.
- Whether the `_log_signal_output` consumer in captain-command has similar issues. The
  `b6_reports.py:272-273` site uses `float(aim_data.get("modifier", 1.0))` which crashes if the
  value is explicitly None. Report-generation only, not trading-path. Backlog.

**Where we're at:**
- `2 patches + lint extension` committed and pushed to BOTH remotes:
  - `captain-online/.../hmm_inference_block.py:94` defensive None-handling
  - `captain-online/.../b7_position_monitor.py:706` `is not None` check on D17 fallback
  - `scripts/lint_decimal_boundary.py` extended with `NOOP_TERNARY_RE` regex catching `float() if not isinstance() else float()` and Decimal variant
- `pytest tests/test_decimal_boundary_lint.py tests/test_decimal_boundary.py` → **28 passed**.
- Towers should `git pull origin main --ff-only` to receive the patches but **MUST NOT rebuild
  captain-online before NY close**. The dry-runs proved the current image is safe; rebuild
  introduces 2-3min downtime risk. Patches are precautionary against edge cases that have not
  fired in observed sessions.

**Next steps:**
1. Tower operators: `cd ~/captain-system; git pull origin main --ff-only` (no rebuild).
2. NY OR window 13:30-13:35 UTC: watch live monitors per record above.
3. Post-NY-close: rebuild captain-online to load the precautionary patches.
4. Post-NY-close backlog (priority order):
   - Comprehensive audit of all 12 captain-offline `float()` call-sites for None-safety
   - Fix `b6_reports.py:272-273` aim_data.get None-handling
   - Fix `dry_run_command.py` false-negative (use API endpoint, not new-process import)
   - Investigate APAC silent-overnight bug (separate orchestrator dispatch trace)
   - Investigate B7→D03 trade-outcome writeback gap
   - Investigate this morning's container auto-restart cause

**Useful refs:**
- `captain-online/.../hmm_inference_block.py:94-95` — patched site (used by HMM inference per `phase_10_execution.md` note: "Online persists inference after B3 aggregation")
- `captain-online/.../b7_position_monitor.py:705-706` — patched fallback fee path
- `scripts/lint_decimal_boundary.py:58-72` — `NOOP_TERNARY_RE` regex + comment
- `tests/test_decimal_boundary_lint.py` — CI gate (still 1 test, now also exercising the new regex)

---

### 2026-05-01 13:10 BST — NY open clearance: pipeline GO, monitors armed

**Status:** Verifying · ~1h 20m to NY open · live monitors running

**What we know — confirmed:**
- Both towers passed `online-run dry_run_phase_a.py {1,2,3}`. Session 1 (NY) verdict on both: `Phase A would produce signals. System ready to trade.` Tower A acct 21855714 sized {ZN, ZB:2, MYM:8, M2K:10, MNQ:5, MES:15}; Tower B acct 20258288 sized {ZN, ZB:3, MYM:7, M2K:10, MNQ:5, MES:15}. Session 2 (LON) sized MGC: 3 (Tower A) / 2 (Tower B). Session 3 (APAC) NKD = 0 contracts (Kelly 0.0003 → 0.1 raw → SKIP) — by design at current EWMA, user accepted as not-blocking.
- `cmd-run dry_run_command.py` reports `_active_connections is EMPTY — adapter_registered FAILED` on **both towers**. Initial alarm: false. **Captain-command logs prove the adapter IS registered:** `TopstepX CONNECTED: account=150KTC-V2-551001-86041837 (id=21855714), balance=150000.00, canTrade=True` on Tower A startup at 06:17 ET; `api_connections:{connected:1,total:1}` on `/api/health`. The dry_run_command script is a known false-negative — it spawns a fresh Python process inside the container via `docker exec`, which has its own empty in-memory `_active_connections`; it does NOT inspect the long-running orchestrator's state.
- TSM warning at command startup `topstep_150k_live.json has errors: ['Missing required field: starting_balance', 'Missing required field: max_drawdown_limit']` is benign and documented at `docs2/quick-fixes/pnl_miscalculations/PRE_MARKET_VALIDATION.md:657`. The current 150KTC-V2 account auto-links to `topstep_150k_eval.json` (which has correct values); the live.json file is for Live Funded accounts only.
- `B5C: L1/L2 falling back to live ... (SOD not run)` warnings present in both towers' dry-runs. SOD = Start-Of-Day reconciliation/circuit-breaker init. Yesterday's commit `61f0ab2 fix(command): SOD reconciliation signature` claimed to address this but warning persists. Fallback is to live values which are correct, so non-blocking. **Backlog item — investigate after market close.**
- User context (critical): yesterday ran on PRAC-V2 (paper-mode practice combine), trades were placed via auto-execute on the broker (confirmed visually on TopstepX), but no GUI cards (caused by decimal `_build_per_account` crash in B6 yielding type-mixed dicts that broke `sanitise_for_gui`). Today switched to 150KTC-V2 (real-money Trading Combine, EVAL stage) and validated the switch this morning. Decimal fix `1910f71` is now deployed on both towers; the same B6 path that broke yesterday is now type-pure.
- F3 D03 `trade_outcome_log` query returned only synthetic test rows (`LEGACY-`, `BACKFILL-TEST-`, `SUM-`, `TEST-MODELM-`) on both towers in 48h. **No real Captain-placed trade has ever written back to D03.** Yesterday's broker-side trades are not in the QuestDB record. Separate B7→D03 writeback bug, deferred (doesn't block trading).
- `dry_run_command.py` doesn't truly verify adapter state — it has a structural bug. **Backlog item — fix to inspect orchestrator state via API endpoint instead of new-process import.**

**What we DON'T yet know:**
- Whether the GUI WebSocket actually receives signal cards on the live `1910f71` build. Yesterday's bug claimed-fixed; not E2E-tested today. Will be observed live at first NY breakout.
- Why APAC was silent overnight (B6 never invoked for session_id=3). Container recreates around 09:30 UTC today wiped the relevant logs. **Backlog item — observe live during tonight's APAC at 22:00 UTC, capture full logs.**
- Whether the SOD-not-run warning has any second-order effects for live trading on a fresh-bootstrapped tower. Sizing looked correct in dry-runs; assume non-blocking and watch.
- Why captain-online + captain-command were both restarted ~09:30-10:17 UTC today (no user action recalled). Possibly auto-restart from a transient crash. **Backlog item — investigate restart cause from journal/syslog after market close.**

**Where we're at:**
- Both towers pulled `2476d76` (b9 fix + lessons-learned rule entries). All 6 services Up healthy on each.
- Live monitors running on each tower in 3 separate fish tabs:
  1. `dco logs -f captain-online` filtered for `Phase B|_run_b6|ON-B6|OR|TypeError|Traceback`
  2. `dco logs -f captain-command` filtered for `signal batch|sanitise_for_gui|broadcast|AUTO-EXECUTE|TopstepX|400|429|500`
  3. Redis `XREAD BLOCK` on `captain:signals:primary_user`
- GUI loaded in browser on each tower; WebSocket connection confirmed.
- Synthetic smoke-test (`XADD captain:signals:primary_user asset=SMOKE_TEST`) **deliberately skipped** — would land a TopstepX 400 on the live audit trail. Relying on first real NY breakout for E2E proof.

**Next steps:**
1. **At NY OR window 13:30–13:35 UTC (14:30–14:35 BST)** — watch all three monitor tabs + GUI. Expect:
   - Tab-1: `OR FORMING <asset>` → `OR COMPLETE <asset>` → `OR BREAKOUT <DIRECTION>: <asset>` → `_run_b6_for_user` → `ON-B6-SUMMARY built=N`
   - Tab-2: `signal batch received` → `sanitise_for_gui` → `AUTO-EXECUTE` → `TopstepX BRACKET PLACED` (or similar)
   - Tab-3: New stream entry with the signal payload
   - GUI: New signal card appearing with entry/TP/SL fields populated
2. **Immediately on first signal** — `/record` a new context entry with the actual log lines captured, success or failure.
3. **If anything in Tab-1/2/3 doesn't match expected pattern** — paste the exact divergent line back to this chat for live diagnosis.
4. **After NY closes** — investigate (a) APAC silent overnight, (b) SOD-not-run warning, (c) D03 writeback gap, (d) `dry_run_command.py` false-negative, (e) why containers auto-restarted this morning.

**Useful refs:**
- `docs2/quick-fixes/pnl_miscalculations/PRE_MARKET_VALIDATION.md:657` — TSM live.json benign warning explanation
- `captain-online/captain_online/blocks/b6_signal_output.py:303` — `_build_per_account` (yesterday's decimal crash site, now fixed in `1910f71`)
- `captain-command/captain_command/blocks/b1_core_routing.py` — `sanitise_for_gui` (yesterday's GUI-display path)
- `captain-command/captain_command/blocks/b3_api_adapter.py` — adapter registration (proven working)
- `.cursor/rules/captain-deploy-and-tower-discipline.mdc` §5 — lessons-learned entries (multi-user remote, REDIS_PASSWORD sourcing, b9 NULL pnl)

---

### 2026-05-01 12:35 BST — Tower 1 first-run findings: 3 blockers patched

**Status:** Patching · Tower 1 needs to pull then re-run Steps 2-3

**What we know — confirmed:**

- Tower 1 ran the Step 0 preamble. Output revealed three independent issues:
  1. `**captain-offline` is crashing** with `TypeError: float() argument must be a string or a real number, not 'NoneType'`. Source: `captain-offline/captain_offline/blocks/b9_diagnostic.py:451`. Original code `float(pnl) if not isinstance(pnl, Decimal) else float(pnl)` had identical ternary branches AND no `None` guard. P3-D03 has open-trade rows where `pnl IS NULL`, so every D4 dimension run crashed. **Fixed** in this session: routed through `shared.decimal_boundary.to_float` and `continue` on `None`.
  2. **Tower 1 doesn't have the `multi-user` remote configured** (`fatal: 'multi-user' does not appear to be a git repository`). The Step 0 SHA-parity check therefore can't compare against `multi-user/main`. **Fixed** by adding an idempotent `git remote add multi-user ...` line to the dependency preamble in this rule file's lessons-learned section.
  3. `**redis-cli -a "$REDIS_PASSWORD"` AUTH-failed** because the tower's fish shell doesn't inherit the env var the containers use. **Fixed** by prepending `set -gx REDIS_PASSWORD (grep '^REDIS_PASSWORD=' ~/captain-system/.env | cut -d= -f2)` before any `redis-cli` call.
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
5. **Mirror everything on Tower B.**
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
  - b3_pseudotrader) → `dbe550b` (CI lint guard).
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

