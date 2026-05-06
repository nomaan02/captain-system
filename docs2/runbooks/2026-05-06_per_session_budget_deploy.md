# Per-Session Budget Allocation — Tower Deploy Runbook (2026-05-06)

> Authoritative runbook for shipping the per-session budget allocation feature
> (8 feature commits + 1 docs commit) to **Tower A** and **Tower B**.
> All commands are **fish-shell native** per
> `.cursor/rules/captain-deploy-and-tower-discipline.mdc`.

---

## 0. Change scope

This deploy ships the per-session L_halt / E_daily_exposure budget split.
NY/LON/APAC each get their own slice of the SOD totals so a heavy NY day no
longer starves APAC's NKD via the `abs(L_t) > L_halt` cascade.

**Code commits** (oldest → newest):

| SHA       | Phase | What lands |
|-----------|-------|------------|
| `d158cc9` | 2     | B8 SOD writes `computed_sod.session.{NY,LON,APAC}`; `_reset_daily_counters` writes per-session zero rows; **`c=0.5 → c=1.0`** in `config/tsm/providers/topstep_150k_eval.json` |
| `249ffa9` | —     | docs(rules) — smarter `cmd-run` (`/captain/scripts/` first, `/app/` fallback) |
| `4e3c30b` | 3a    | Online orchestrator session-open hook `_initialize_session_budget` |
| `d69554d` | 3     | B7 writes per-session L_t (preserves `effective_l_halt`); per-(session, model_m) basket key |
| `8ec6aa0` | 4     | B5C reads per-session L_halt / E for L1 / L2 |
| `5891534` | 5     | B4 `_compute_topstep_daily_cap` reads per-session E |
| `3d561b3` | 6     | B5 `apply_hmm_session_allocation` observability-only |
| `2264871` | 7     | Replay engine per-session accumulators |
| `2a184df` | 8     | GUI TSM panel per-session breakdown |

**Schema migrations** (auto-applied by `init_questdb.py`):

- `M043_d23_add_session_id` — `ADD COLUMN session_id INT`
- `M044_d23_add_effective_l_halt` — `ADD COLUMN effective_l_halt DECIMAL(18,2)`
- `M045_d23_add_effective_e_exposure` — `ADD COLUMN effective_e_exposure DECIMAL(18,2)`
- `M046_d23_add_session_opened_at` — `ADD COLUMN session_opened_at TIMESTAMP`
- `M047_d23_dedup_include_session_id` — `DEDUP ENABLE UPSERT KEYS(last_updated, account_id, session_id)`

---

## 1. Pre-flight (run on the LOCAL DEV BOX before touching any tower)

Verify both remotes have the latest commits BEFORE starting tower work
(per rule §1 — dual-remote push is mandatory).

```fish
cd ~/captain-system

git fetch origin
git fetch multi-user

set -l LOCAL_HEAD (git rev-parse HEAD)
set -l ORIGIN_HEAD (git rev-parse origin/main)
set -l MULTI_HEAD  (git rev-parse multi-user/main)

echo "LOCAL  : $LOCAL_HEAD"
echo "ORIGIN : $ORIGIN_HEAD"
echo "MULTI  : $MULTI_HEAD"

test "$LOCAL_HEAD" = "$ORIGIN_HEAD"; \
    and test "$LOCAL_HEAD" = "$MULTI_HEAD"; \
    and echo "OK: both remotes synced to local HEAD"; \
    or echo "MISMATCH — push to whichever remote is behind, do not deploy yet"
```

If MULTI is behind:

```fish
git push multi-user HEAD
```

If ORIGIN is behind:

```fish
git push origin HEAD
```

Re-run the parity block until you see `OK: both remotes synced`. **Do not
proceed to any tower until both remotes match local HEAD.**

---

## 2. Tower preamble (run on EACH tower at the start of the session)

Paste this **once per tower shell session**. The `type -q` guards make it a
no-op if the helpers are already loaded from the user's `~/.config/fish/functions/`.

```fish
# Helpers (idempotent — no-op if already in ~/.config/fish/functions/)
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

# Tower-side packages (idempotent)
command -v jq        > /dev/null 2>&1; or sudo apt install -y jq
command -v redis-cli > /dev/null 2>&1; or sudo apt install -y redis-tools

# Multi-user remote (idempotent)
git remote get-url multi-user > /dev/null 2>&1; \
    or git remote add multi-user git@github.com:nomaan02/captain-multi-user.git

# REDIS_PASSWORD from the same .env the containers use
test -z "$REDIS_PASSWORD"; \
    and set -gx REDIS_PASSWORD (grep '^REDIS_PASSWORD=' ~/captain-system/.env | cut -d= -f2)
```

---

## 3. Deploy steps (run on EACH tower, A then B)

```fish
cd ~/captain-system

# Fetch from BOTH remotes and verify SHA parity (rule §1)
git fetch origin
git fetch multi-user

set -l ORIGIN_HEAD (git rev-parse origin/main)
set -l MULTI_HEAD  (git rev-parse multi-user/main)

echo "ORIGIN : $ORIGIN_HEAD"
echo "MULTI  : $MULTI_HEAD"

test "$ORIGIN_HEAD" = "$MULTI_HEAD"; \
    and echo "OK: remote SHAs match — safe to pull"; \
    or echo "MISMATCH — STOP, fix the local box and re-push before pulling"
```

If MISMATCH, **stop here**. Do NOT pull. Return to §1 on the dev box.

If OK, continue:

```fish
git pull --ff-only origin main

# Sanity: confirm we landed on the expected feature SHA
git log -1 --oneline   # expect: 9aefcb5 ... feat(shared): add qexecute helper

# CRITICAL: sync config/ -> each service's _config/ build context.
# Dockerfiles COPY _config/ /captain/config/, so changes to config/*.json
# (including this deploy's bump of c=0.5 -> c=1.0 in topstep_150k_eval.json)
# DO NOT reach the container unless this sync runs first. captain-start.sh
# does it automatically; raw `dco up -d --build` does not.
for svc in captain-offline captain-online captain-command
    rm -rf $svc/_config
    cp -r config $svc/_config
end

# Verify the bumped c=1.0 is present in all three build contexts
grep '"c":' captain-{command,online,offline}/_config/tsm/providers/topstep_150k_eval.json
# Expected: all three lines show "c": 1.0,

# Rebuild + restart (uses the dco helper). --no-cache on captain-command
# guarantees the refreshed _config/ layer is picked up.
dco down
dco build --no-cache captain-command
dco up -d --build
```

Wait ~30–60s for containers, then verify health:

```fish
dco ps

# Watch captain-command init logs for migration application
dco logs --tail 100 captain-command | grep -iE 'M04[3-7]|init_questdb'
```

Expected log lines (one per migration, all `[OK]` or `[SKIP]`):

```
  [OK] M043_d23_add_session_id
  [OK] M044_d23_add_effective_l_halt
  [OK] M045_d23_add_effective_e_exposure
  [OK] M046_d23_add_session_opened_at
  [OK] M047_d23_dedup_include_session_id
```

(`[SKIP]` is also valid on a re-run — `init_questdb.py` is idempotent.)

If you don't see the migration lines in `captain-command` logs (e.g. because
the entrypoint doesn't run `init_questdb.py`), force-apply:

```fish
cmd-run init_questdb.py
```

---

## 4. Schema migration verification (host curl + QuestDB /exec)

QuestDB does not ship `psql` in its image (rule §5, 2026-05-05 entry), so use
the host HTTP `/exec` endpoint on port 9000 (already bound in
`docker-compose.local.yml`).

### 4.1 Confirm the four new columns exist on D23

```fish
curl -s -G "http://localhost:9000/exec" \
    --data-urlencode "query=SHOW COLUMNS FROM p3_d23_circuit_breaker_intraday" \
    | jq -r '.dataset[] | .[0]' \
    | grep -E '^(session_id|effective_l_halt|effective_e_exposure|session_opened_at)$' \
    | sort
```

Expected output (exactly four lines):

```
effective_e_exposure
effective_l_halt
session_id
session_opened_at
```

If any are missing, re-run `cmd-run init_questdb.py` and check
`dco logs captain-command | grep -iE 'M04[3-7]'` for FAIL lines.

### 4.2 Confirm column types

```fish
curl -s -G "http://localhost:9000/exec" \
    --data-urlencode "query=SHOW COLUMNS FROM p3_d23_circuit_breaker_intraday" \
    | jq -r '.dataset[] | "\(.[0])\t\(.[1])"' \
    | grep -E '^(session_id|effective_l_halt|effective_e_exposure|session_opened_at)\b'
```

Expected (4 lines, types matter):

```
session_id              INT
effective_l_halt        DECIMAL
effective_e_exposure    DECIMAL
session_opened_at       TIMESTAMP
```

### 4.3 Confirm DEDUP keys include `session_id` (M047)

`SHOW CREATE TABLE` returns the full canonical DDL including the
`DEDUP UPSERT KEYS(...)` clause:

```fish
curl -s -G "http://localhost:9000/exec" \
    --data-urlencode "query=SHOW CREATE TABLE p3_d23_circuit_breaker_intraday" \
    | jq -r '.dataset[][]' \
    | grep -iE 'DEDUP|UPSERT'
```

Expected line (or substring):

```
DEDUP UPSERT KEYS(last_updated, account_id, session_id);
```

If the line still reads `DEDUP UPSERT KEYS(last_updated, account_id)` (i.e.
M047 didn't apply), force-reapply:

```fish
curl -s -G "http://localhost:9000/exec" \
    --data-urlencode "query=ALTER TABLE p3_d23_circuit_breaker_intraday DEDUP ENABLE UPSERT KEYS(last_updated, account_id, session_id)" \
    | jq .
```

Re-check with the previous block until you see `session_id` in the keys.

---

## 5. Force B8 SOD recompute (don't wait for 19:00 ET)

`run_daily_reconciliation` writes the `computed_sod.session.{NY,LON,APAC}`
map to `p3_d08_tsm_state.topstep_state`. The orchestrator only calls it at
19:00 ET, but the function itself is **not** time-gated — we can invoke it
directly via a short helper script.

### 5.1 Write the helper script (idempotent)

The repo `./scripts/` directory is bind-mounted into `captain-command` at
`/captain/scripts/` (per `docker-compose.local.yml`). Drop the helper there
once per tower — `cmd-run` will then resolve it:

```fish
bash -c "cat > ~/captain-system/scripts/force_sod_recompute.py <<'PY'
\"\"\"Force a B8 SOD per-session recompute outside the 19:00 ET window.

Use this AFTER deploying the per-session-budget feature so the
'computed_sod.session.{NY,LON,APAC}' map is populated immediately
instead of waiting for the next nightly reconciliation.

Calls run_daily_reconciliation() directly (which is NOT time-gated —
the time gate lives in the orchestrator's _check_reconciliation_trigger).
\"\"\"
import logging
import sys

sys.path.insert(0, '/app')

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')

from captain_command.blocks.b8_reconciliation import run_daily_reconciliation


def _stub_gui_push(user_id, msg):
    print(f'[gui_push] user={user_id} type={msg.get(\"type\", \"?\")} priority={msg.get(\"priority\", \"?\")}')


def _stub_notify(notif):
    print(f'[notify] {notif}')


if __name__ == '__main__':
    run_daily_reconciliation(
        gui_push_fn=_stub_gui_push,
        get_broker_status_fn=None,  # manual reconciliation; no broker pull
        notify_fn=_stub_notify,
    )
    print('FORCE_SOD_RECOMPUTE: complete')
PY"
```

> **Why backticks aren't escaped in the heredoc:** fish double-quotes pass
> backticks through verbatim (they're deprecated as command-substitution
> markers and never had effect inside `"..."` even when active), but a
> stray `\`` becomes a literal `\` + `` ` `` in the output, which Python
> flags as `SyntaxWarning: invalid escape sequence`. Plain single quotes
> around the JSON path keep the docstring clean.

### 5.2 Invoke it inside `captain-command`

```fish
cmd-run force_sod_recompute.py
```

Expected stdout includes the per-session log line emitted by
`_compute_sod_topstep_params`:

```
SOD Topstep params computed for 21855714: f(A)=0.xxxx N=NN E=NNNN.NN L_halt=NNNN.NN per-session L_halt: NY=NNN.NN LON=NNN.NN APAC=NNN.NN
...
Daily counters reset: D08.daily_loss_used=0 for 1 accounts; D23 zero rows written for 1 accounts × 3 sessions
FORCE_SOD_RECOMPUTE: complete
```

`L_halt` should now be roughly `~$1500` (since `c=1.0` and `e=0.01`,
`L_halt_total = 1.0 × 0.01 × 150000 = $1500`). The three per-session
values should each be `~$500` under the equal-cold-start split.

---

## 6. Verify D08 — `computed_sod.session` populated with non-zero values

`p3_d08_tsm_state.topstep_state` is a JSON string column. Read it via curl
then drill into the nested key:

```fish
curl -s -G "http://localhost:9000/exec" \
    --data-urlencode "query=SELECT account_id, last_updated, topstep_state FROM p3_d08_tsm_state LATEST ON last_updated PARTITION BY account_id" \
    | jq -r '.dataset[] | "ACCOUNT: \(.[0])\nLAST_UPDATED: \(.[1])\nCOMPUTED_SOD.SESSION:\n\(.[2] | fromjson | .computed_sod.session // "<null>" | tojson)\n---"'
```

Expected output (account `21855714`, primary_user, $150K Combine):

```
ACCOUNT: 21855714
LAST_UPDATED: 2026-05-06T...
COMPUTED_SOD.SESSION:
{"NY":{"L_halt":"500.00","E_daily_exposure":"500.00","N_max_trades":NN,"share":"0.333333"},"LON":{"L_halt":"500.00","E_daily_exposure":"500.00","N_max_trades":NN,"share":"0.333333"},"APAC":{"L_halt":"500.00","E_daily_exposure":"500.00","N_max_trades":NN,"share":"0.333333"}}
---
```

**Pass criteria:**

- `computed_sod.session` is **not** `<null>`
- Three keys present: `NY`, `LON`, `APAC`
- Each key has `L_halt > 0` and `E_daily_exposure > 0`
- `share` values sum to ~1.0 (each ≈ 0.333333 in cold-start)

If `computed_sod.session` is `<null>`, B8 didn't run successfully — re-check
§5.2 stdout for tracebacks, and look at:

```fish
dco logs --tail 200 captain-command | grep -iE 'SOD Topstep|RECONCILIATION'
```

Also verify the source field tells you which weighting mode produced the shares:

```fish
curl -s -G "http://localhost:9000/exec" \
    --data-urlencode "query=SELECT account_id, topstep_state FROM p3_d08_tsm_state LATEST ON last_updated PARTITION BY account_id" \
    | jq -r '.dataset[] | .[1] | fromjson | .computed_sod.session_shares_source'
```

Expected: `EQUAL_COLD_START` until HMM has accumulated ≥20 observations.

---

## 7. Verify D23 — zero-rows-per-session written by `_reset_daily_counters`

The reset block now writes one zero row per `(account_id, session_id)` where
`session_id ∈ {1=NY, 2=LON, 3=APAC}` (per
`shared.sod_session_budget.TRADING_DAY_SESSION_ORDER`).

```fish
curl -s -G "http://localhost:9000/exec" \
    --data-urlencode "query=SELECT account_id, session_id, l_t, n_t, effective_l_halt, effective_e_exposure, session_opened_at, last_updated FROM p3_d23_circuit_breaker_intraday LATEST ON last_updated PARTITION BY account_id, session_id" \
    | jq -r '.dataset[] | "ac=\(.[0]) sid=\(.[1]) l_t=\(.[2]) n_t=\(.[3]) eff_L_halt=\(.[4]) eff_E=\(.[5]) opened_at=\(.[6]) last_updated=\(.[7])"'
```

Expected rows for account `21855714` (3 rows, one per session_id 1/2/3):

| account_id | session_id | l_t   | n_t | effective_l_halt | effective_e_exposure | session_opened_at | last_updated |
|------------|------------|-------|-----|------------------|----------------------|-------------------|--------------|
| 21855714   | 1          | 0.00  | 0   | (null)           | (null)               | (null)            | 2026-05-06T... |
| 21855714   | 2          | 0.00  | 0   | (null)           | (null)               | (null)            | 2026-05-06T... |
| 21855714   | 3          | 0.00  | 0   | (null)           | (null)               | (null)            | 2026-05-06T... |

**Pass criteria:**

- 3 rows for the live account, one per `session_id` in `{1, 2, 3}`
- All have `l_t = 0`, `n_t = 0`
- All have `effective_l_halt = NULL` and `effective_e_exposure = NULL`
  (these get populated by the orchestrator at the next session-open — see §8)
- All have `session_opened_at = NULL`

If you see only one row per account (e.g. with `session_id = NULL`),
`_reset_daily_counters` ran in legacy mode — re-check that the
captain-command image actually rebuilt with the Phase 2 changes:

```fish
dco exec -T captain-command grep -n 'TRADING_DAY_SESSION_ORDER' /app/captain_command/blocks/b8_reconciliation.py
```

Expected: a hit around the `_reset_daily_counters` body (line ~515 in current code).

---

## 8. First-session smoke test (after the next LON / NY / APAC open)

The Online orchestrator session-open hook (`_initialize_session_budget` at
`captain-online/captain_online/blocks/orchestrator.py:816`) inserts a fresh
D23 row for the opening session with `effective_l_halt`,
`effective_e_exposure`, and `session_opened_at` populated.

Wait until the next session-open (LON 03:00 ET, NY 09:30 ET, or APAC 18:00
ET, whichever lands first).

### 8.1 Confirm the orchestrator log line fires

```fish
dco logs --tail 500 captain-online 2>&1 | grep -E 'ON-Orch: session (LON|NY|APAC) init for'
```

Expected (one line, fired at the session-open minute):

```
ON-Orch: session NY init for 21855714 — eff_L_halt=NNN.NN eff_E=NNN.NN (SOD share=0.NNNN, completed=N earlier sessions, carryover=NN.NN)
```

If you don't see it, the orchestrator's session-open path didn't call the
hook — verify with:

```fish
dco exec -T captain-online grep -n '_initialize_session_budget' /app/captain_online/blocks/orchestrator.py
```

Expected: hits at the call site (around line 263) and the definition
(around line 816).

### 8.2 Confirm the D23 row was updated for the opening session

Replace `<SID>` below with `1` (NY), `2` (LON), or `3` (APAC) — whichever
just opened.

```fish
set -l SID 1   # 1=NY 2=LON 3=APAC

curl -s -G "http://localhost:9000/exec" \
    --data-urlencode "query=SELECT account_id, session_id, l_t, n_t, effective_l_halt, effective_e_exposure, session_opened_at, last_updated FROM p3_d23_circuit_breaker_intraday WHERE session_id = $SID LATEST ON last_updated PARTITION BY account_id, session_id" \
    | jq -r '.dataset[] | "ac=\(.[0]) sid=\(.[1]) l_t=\(.[2]) n_t=\(.[3]) eff_L_halt=\(.[4]) eff_E=\(.[5]) opened_at=\(.[6]) last_updated=\(.[7])"'
```

**Pass criteria for the opening session:**

- `l_t = 0` and `n_t = 0` (clean slate at open)
- `effective_l_halt > 0` (no longer NULL — orchestrator wrote it)
- `effective_e_exposure > 0`
- `session_opened_at` is a recent timestamp (within ~5 minutes of session-open)

For non-opening sessions on the same day, the row should still be the
zero-row from §7 (`effective_l_halt = NULL`, `session_opened_at = NULL`)
until that session opens.

### 8.3 Confirm B5C reads per-session L_halt for circuit-breaker decisions

Once a trade signal fires for an asset whose primary session is the open
one, B5C will log its per-session L_halt read:

```fish
dco logs --tail 200 captain-online 2>&1 | grep -iE 'B5C.*(L_halt|effective_l_halt|session)'
```

Expected: log lines showing the `effective_l_halt` value being compared to
`abs(l_t) + rho_j` per the L1 formula.

---

## 9. Rollback (if anything breaks before market opens)

If a tower won't come up healthy, OR D08 / D23 verification fails after
60 minutes of debugging, OR session-open hooks don't fire at the next
session boundary — roll back the **8 feature commits** (keep the docs
commit `249ffa9` since it improves `cmd-run`).

### 9.1 On the LOCAL DEV BOX — revert + dual-push

Revert in REVERSE chronological order so each diff applies cleanly:

```fish
cd ~/captain-system

# Newest first → walks backward; --no-edit auto-generates "Revert ..." messages
git revert --no-edit \
    2a184df \
    2264871 \
    3d561b3 \
    5891534 \
    8ec6aa0 \
    d69554d \
    4e3c30b \
    d158cc9

git log --oneline -10   # confirm 8 "Revert ..." commits at the top

# Push to BOTH remotes (rule §1)
git push origin HEAD
git push multi-user HEAD

# Verify SHA parity
git fetch origin
git fetch multi-user

set -l LOCAL_HEAD  (git rev-parse HEAD)
set -l ORIGIN_HEAD (git rev-parse origin/main)
set -l MULTI_HEAD  (git rev-parse multi-user/main)

test "$LOCAL_HEAD" = "$ORIGIN_HEAD"; \
    and test "$LOCAL_HEAD" = "$MULTI_HEAD"; \
    and echo "OK: rollback synced to both remotes"; \
    or echo "MISMATCH — investigate before pulling on towers"
```

> **NOTE 1.** The revert undoes the `c=0.5 → c=1.0` bump in
> `config/tsm/providers/topstep_150k_eval.json` (it was inside Phase 2,
> commit `d158cc9`). After rollback you are back on `c=0.5`, which means
> `L_halt = $750` and the original "any 4-ES NY trade trips L1" problem
> returns. If the original c-value was the tripping issue, do **NOT** roll
> back — patch forward instead.
>
> **NOTE 2.** Schema migrations M043–M047 are **NOT reverted** — they're
> additive `ALTER TABLE` statements baked into the live QuestDB tables.
> The new columns become inert (legacy code never reads them). The DEDUP
> key change (M047) is also not reverted; it is backwards-compatible
> because legacy inserts pass `session_id = NULL` and dedup will collapse
> on `(last_updated, account_id, NULL)`, which is functionally equivalent
> to the pre-M047 behaviour.

### 9.2 On EACH tower — pull rollback + rebuild

```fish
cd ~/captain-system

git fetch origin
git fetch multi-user

set -l ORIGIN_HEAD (git rev-parse origin/main)
set -l MULTI_HEAD  (git rev-parse multi-user/main)

test "$ORIGIN_HEAD" = "$MULTI_HEAD"; \
    and echo "OK: remote SHAs match — safe to pull"; \
    or echo "MISMATCH — STOP"

git pull --ff-only origin main
git log -1 --oneline   # expect: top of log shows the most recent "Revert ..."

dco down
dco up -d --build
```

### 9.3 Manual D23 zero-out (legacy-compatible row insert)

After the rollback, legacy B5C code reads
`LATEST ON last_updated PARTITION BY account_id` (no `session_id` filter).
The per-session zero rows from §7 are still in D23, so legacy code will
read whichever has the latest `last_updated`. Insert a single
`session_id = NULL` row per account so legacy code sees a clean state:

```fish
set -gx NOW (date -u +"%Y-%m-%dT%H:%M:%S.000000Z")

# Hard-coded primary_user account 21855714 per CLAUDE.md current state.
# If you have multiple topstep_optimisation accounts, repeat this block
# for each account_id.
curl -s -G "http://localhost:9000/exec" \
    --data-urlencode "query=INSERT INTO p3_d23_circuit_breaker_intraday(account_id, session_id, l_t, n_t, l_b, n_b, effective_l_halt, effective_e_exposure, session_opened_at, last_updated) VALUES('21855714', NULL, 0, 0, '{}', '{}', NULL, NULL, NULL, '$NOW')" \
    | jq .
```

Confirm the legacy-compatible row is now the LATEST:

```fish
curl -s -G "http://localhost:9000/exec" \
    --data-urlencode "query=SELECT account_id, session_id, l_t, n_t, last_updated FROM p3_d23_circuit_breaker_intraday LATEST ON last_updated PARTITION BY account_id" \
    | jq '.dataset'
```

Expected: one row per account with `session_id = null`, `l_t = "0.00"`,
`n_t = 0`, and `last_updated` matching `$NOW`.

### 9.4 Verify rollback parity

After both towers pull the revert, confirm both run the same SHA:

```fish
# Run on EACH tower; values must match across A and B
git rev-parse HEAD
```

---

## 10. Known failure modes & troubleshooting

### 10.1 `psql: command not found` inside `captain-system-questdb-1`

The QuestDB Docker image does not ship `psql`. Use the host curl + `/exec`
endpoint pattern shown throughout this runbook (port 9000 is bound in
`docker-compose.local.yml`).

**Wrong:**

```fish
docker exec captain-system-questdb-1 sh -c \
    "psql -h localhost -p 8812 -U admin -d qdb -c 'SELECT ...'"
```

**Right:**

```fish
curl -s -G "http://localhost:9000/exec" \
    --data-urlencode "query=SELECT ..." \
    | jq .
```

### 10.2 `online-run: command not found` (or `cmd-run: command not found`)

The fish helpers were not loaded into this shell. Either:

1. Open a fresh fish shell — `~/.config/fish/functions/{dco,cap-run,online-run,cmd-run}.fish`
   auto-load on startup, OR
2. Re-paste the §2 preamble block into the current shell, OR
3. If the function files are missing entirely, re-create them with `funcsave`:

```fish
function dco
    docker compose -f docker-compose.yml -f docker-compose.local.yml $argv
end
funcsave dco

function cap-run
    set -l script $argv[1]
    set -l rest $argv[2..-1]
    docker compose -f docker-compose.yml -f docker-compose.local.yml \
        exec -T -e PYTHONPATH=/app captain-offline \
        python /captain/scripts/$script $rest
end
funcsave cap-run

function online-run
    set -l script $argv[1]
    set -l rest $argv[2..-1]
    docker compose -f docker-compose.yml -f docker-compose.local.yml \
        exec -T -e PYTHONPATH=/app captain-online \
        python3 /app/$script $rest
end
funcsave online-run

function cmd-run
    set -l script $argv[1]
    set -l rest $argv[2..-1]
    docker compose -f docker-compose.yml -f docker-compose.local.yml \
        exec -T -e PYTHONPATH=/app captain-command \
        sh -c "if [ -f /captain/scripts/$script ]; then exec python3 /captain/scripts/$script $rest; else exec python3 /app/$script $rest; fi"
end
funcsave cmd-run
```

### 10.3 `cmd-run force_sod_recompute.py` → `No such file or directory`

The script wasn't written under `~/captain-system/scripts/`, OR the user's
`cmd-run` is the older version that only checks `/app/`.

**Check:** does the file exist on the host?

```fish
ls -l ~/captain-system/scripts/force_sod_recompute.py
```

If yes, but the error persists, the user's `cmd-run` is the legacy version.
Re-install the smarter helper (see §10.2 above).

### 10.4 `git pull` → `'multi-user' does not appear to be a git repository`

The tower was cloned from origin only. Add the missing remote:

```fish
git remote get-url multi-user > /dev/null 2>&1; \
    or git remote add multi-user git@github.com:nomaan02/captain-multi-user.git

git fetch multi-user
```

### 10.5 `redis-cli` AUTH failed: `WRONGPASS`

`REDIS_PASSWORD` not in this fish shell. Source from `.env`:

```fish
set -gx REDIS_PASSWORD (grep '^REDIS_PASSWORD=' ~/captain-system/.env | cut -d= -f2)
docker exec captain-system-redis-1 redis-cli -a "$REDIS_PASSWORD" --no-auth-warning XLEN captain:signals:primary_user
```

### 10.6 `cat >> ~/.config/fish/config.fish <<'TAG'` → `Expected a string, but found a redirection`

Fish does not support bash heredocs. For multi-line file writes, use
`bash -c "cat > path <<'TAG' ... TAG"` (see §5.1). For function persistence,
use `funcsave <name>` (see §10.2).

### 10.7 Migration `[FAIL] M047_d23_dedup_include_session_id`

QuestDB sometimes rejects DEDUP key changes if the table has live WAL
writes in flight. Stop the writers and re-apply:

```fish
dco stop captain-online captain-offline captain-command

curl -s -G "http://localhost:9000/exec" \
    --data-urlencode "query=ALTER TABLE p3_d23_circuit_breaker_intraday DEDUP ENABLE UPSERT KEYS(last_updated, account_id, session_id)" \
    | jq .

dco start captain-online captain-offline captain-command
```

Re-verify with §4.3.

### 10.8 `_initialize_session_budget` log line never fires at session open

The orchestrator's session-open detector lives at
`captain-online/captain_online/blocks/orchestrator.py:162` and calls
`_initialize_session_budget` at line 263. If neither fires:

```fish
# Confirm Phase 3a code is in the running container
dco exec -T captain-online grep -nC2 '_initialize_session_budget' /app/captain_online/blocks/orchestrator.py | head -40
```

If `grep` returns nothing, the image was rebuilt from a stale layer cache.
Force a no-cache rebuild:

```fish
dco build --no-cache captain-online
dco up -d captain-online
```

### 10.9 `effective_l_halt` is `NULL` after session opened (smoke test §8.2 fails)

Either the orchestrator hook ran but bailed inside the per-account loop
(e.g. `computed_sod` was empty for that account), OR the run completed
but the row insert was rejected by QuestDB (e.g. type mismatch).

Diagnose:

```fish
dco logs --tail 500 captain-online 2>&1 | grep -E 'ON-Orch: (session|account)'
```

Common path: `ON-Orch: account 21855714 has no computed_sod — skipping`
indicates §5 (`force_sod_recompute.py`) wasn't run, or B8 ran but failed.
Re-run §5.2 and check D08 (§6) before the next session-open boundary.

---

## Appendix — Commit references

For audit trail, the 9 commits reachable from `main` and not from `4dac522`:

```
2a184df feat(per-session-budget) Phase 8: GUI TSM panel per-session breakdown
2264871 feat(per-session-budget) Phase 7: replay engine per-session accumulators
3d561b3 feat(per-session-budget) Phase 6: B5 apply_hmm_session_allocation observability-only
5891534 feat(per-session-budget) Phase 5: B4 _compute_topstep_daily_cap per-session
8ec6aa0 feat(per-session-budget) Phase 4: B5C circuit breaker per-session reads
d69554d feat(per-session-budget) Phase 3: B7 writes per-session D23 + per-(session,m) basket
4e3c30b feat(per-session-budget) Phase 3a: orchestrator session-open budget hook
249ffa9 docs(rules): smarter cmd-run + record /app vs /captain/scripts path mismatch
d158cc9 feat(per-session-budget) Phase 2: B8 SOD per-session writes + reset bug fix + c=1.0
```

8 are `feat(per-session-budget)` (the rollback target); 1 is
`docs(rules)` (preserve through any rollback).
