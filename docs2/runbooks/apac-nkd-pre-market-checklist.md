# APAC NKD Pre-Market Checklist
**Use before every APAC session open (18:00 ET) when NKD trailing-stop is active.**
**APAC OR window: 18:00–18:05 ET. Signal fires at 18:05 ET.**

Run every command in order. Each has an **expected output** and a **failure action**.
A ❌ at any step means stop and fix before proceeding.

---

## T−60 min: One-off deploy steps (only on first run after NKD pivot deploy)

These are idempotent — safe to re-run every session, but only strictly needed once.

### 1 — Push NKD trail fields into D00 (both towers)

The `bootstrap_production.py` update from C4 adds `is_nkd_trail`, `tp_dollars`, and trail
phase thresholds to the NKD `locked_strategy` JSON in `p3_d00_asset_universe`. Without this,
B6 will not include `is_nkd_trail=True` in the signal and the trail block will never activate.

```fish
cmd-run bootstrap_production.py
```

**Expected** — NKD line shows:
```
[OK] NKD: m=6, k=6, OO=0.8533, pv=5.0, margin=8400
```
No `[NEW]` (row already exists — this is an update). All phases should show `[SKIP]` or `[OK]`.

**Failure action:** If phase 1 errors, run `cmd-run bootstrap_production.py --dry-run` first
to see what it would write, then check QuestDB connectivity (`curl http://localhost:9000/exec?query=SELECT+1`).

### 2 — Confirm D00 NKD locked_strategy has trail fields (both towers)

```fish
curl -s -G "http://localhost:9000/exec" \
    --data-urlencode "query=SELECT locked_strategy FROM p3_d00_asset_universe WHERE asset_id='NKD' ORDER BY last_updated DESC LIMIT 1" \
    | jq -r '.dataset[0][0]' | python3 -c "import sys,json; s=json.load(sys.stdin); print('is_nkd_trail:', s.get('is_nkd_trail')); print('tp_dollars:', s.get('tp_dollars')); print('trail_step_dollars:', s.get('trail_step_dollars'))"
```

**Expected:**
```
is_nkd_trail: True
tp_dollars: 4450
trail_step_dollars: 500
```

**Failure action:** Re-run step 1. If still missing, check `scripts/bootstrap_production.py`
line 49 that `P2_STRATEGIES["NKD"]` has these keys.

### 2a — F2 sanity check: verify trail-control fields thread through sanitise_for_api (both towers)

This is the **primary human-readable proof that Batch 1 (F2 fix) is active** on this tower.
Runs in 5 s. A failure here means the trail block will be silently inert for the entire trade.
**If any line returns `False`, STOP — do not open the APAC session.**

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

**Expected (post-B1 deploy):**
```
is_nkd_trail in sanitised? True
tp_dollars in sanitised? True
snapped_d_init in sanitised? True
jitter_j in sanitised? True
Total keys: 19
```

**Failure action:** any line `False` → B1 is not on this tower. Re-run the tower deploy runbook at
`docs2/quick-fixes/NKD_Pivot/day_2/Rejected _orders_issue/BATCH_4_VALIDATION_DEPLOY.md` §5.
Do NOT open the APAC session (audit §4 proof: trail block silently skips every NKD position).

### 2b — D34 expectation table post-fix (check after first NKD trade fills)

With Batch 1 deployed, D34 must have ≥1 row within 30 s of the first NKD bracket fill.

```fish
curl -s -G "http://localhost:9000/exec" \
  --data-urlencode "query=SELECT signal_id, current_phase, current_buffer, current_stop_price, jitter_j, modify_seq FROM p3_d34_nkd_trail_state LATEST ON last_updated PARTITION BY signal_id" \
  | jq '.dataset'
```

**Expected column values (post-B1):**
- `current_phase` — `"A"` on entry; advances to `"B"` at +$2,000 profit, `"C"` at +$3,000 profit
- `current_buffer` — `1025` in Phase A; `1000` in Phase B; `450` in Phase C
- `current_stop_price` — non-null price on the correct side of entry
- `jitter_j` — `0` on Nomaan tower; non-zero on Isaac tower
- `modify_seq` — integer ≥ 1, increments each poll cycle

**Failure action:** if D34 stays empty >2 min after fill:
```fish
dco logs captain-online 2>&1 | grep -iE "ON-B7B-NKD|nkd_trail|ERROR"
```
A `"scan saw N NKD position(s) with is_nkd_trail=False"` line confirms B1 regression — stop and roll back.

### 2c — GUI Trade panel expectations post-fix (check within 10 s of TAKEN)

With Batch 1 deployed, these columns must populate in the GUI Trade panel within 10 s of TAKEN
(they were permanently blank/null pre-B1):

- `current_phase` — `A`, `B`, or `C`
- `current_buffer` — dollar buffer value (starts $1,025; steps to $1,000 at Phase B, $450 at Phase C)
- `current_stop_price` — current trailing SL price (updates every 10 s per poll cycle)
- `modify_seq` — integer, increments on each successful `modify_order` call

**Failure action:** columns still blank after 30 s → run step 2a to confirm B1 is active.
If 2a passes but GUI is blank, check `dco logs captain-online 2>&1 | grep "ON-B7B-NKD"` for errors.

### 2d — F4 orphan-TP confirmation (check if a bracket rejection ever fires)

Batch 2 (F4) prevents orphan LIMIT orders after a fallback SL fails and the position is flattened.
This was the root cause of order `2994362566` (Limit BUY @ 60665, 2026-05-18, cancelled 14 min later).

If `captain:alerts` shows a `SL_PLACEMENT_FAILED` event, check the TopstepX order export:
- There must be **no open LIMIT BUY or SELL** without a corresponding open position.
- The `captain-command` logs should show: `Fallback TP placement SKIPPED for entry <id> (sl_failed=True status=FLATTENED_SL_FAIL) — orphan TP guard (F4).`

**Failure action:** if an orphan LIMIT appears, cancel it manually in the broker GUI.
Verify B2 is on the tower: `git log --oneline -5 | grep 441671d` must return a result.

### 2e — F5/§8.3 log signatures to grep after first NKD trade

```fish
dco logs captain-online 2>&1 | grep "ON-B7B-NKD"
```

**Expected message catalogue:**

| Message | Expected frequency | Action if unexpected |
|---|---|---|
| `ON-B7B-NKD: modify OK signal=… seq=…` | Every poll cycle while position open | If never appears, trail block not running — check D34 (step 2b) |
| `ON-B7B-NKD: jitter sampled signal=… parity=… X=… Y=… J=…` | **Should NOT fire** on normal post-B1 path | If fires, jitter_j not threading from B6 — check B1 on tower |
| `ON-B7B-NKD: scan saw N NKD position(s) with is_nkd_trail=False — trail logic inert for those positions; verify F2 fix is on tower` | **NEVER after B1** | **STOP** — B1 regressed or not on this tower. Roll back. |
| `NKD_TRAIL_JITTER_MISSING` CRITICAL in `captain:alerts` | **NEVER after B1** (Isaac tower only) | Isaac jitter threading regressed — check git HEAD, re-deploy B1. |

---

## T−30 min: Containers and execution mode

### 3 — All containers healthy

```fish
dco ps
```

**Expected:** All 9 services show `Up` (not `Exit` or `Restarting`).
Key containers: `captain-online`, `captain-command`, `captain-offline`, `questdb`, `redis`.

**Failure action:** `dco logs captain-online | tail -30` to see crash reason. Restart with
`dco up -d captain-online` if crashed; `dco up -d --build captain-online` if code issue.

### 4 — AUTO_EXECUTE is true on this tower

```fish
dco exec -T captain-command sh -c 'echo AUTO_EXECUTE=$AUTO_EXECUTE'
```

**Expected:**
```
AUTO_EXECUTE=true
```

**Failure action:** Edit `.env` — set `AUTO_EXECUTE=true` — then `dco up -d` (no rebuild needed
for env-only changes). Do NOT set to `true` if any compliance flag is false (see step 5).

### 5 — Compliance gate in AUTO mode

```fish
dco exec -T captain-command python3 -c "
import sys; sys.path.insert(0, '/app')
from captain_command.blocks.b12_compliance_gate import check_compliance_gate
import json; print(json.dumps(check_compliance_gate(), indent=2))
"
```

**Expected:**
```json
{
  "allowed": true,
  "execution_mode": "AUTO",
  "unsatisfied": [],
  "total_requirements": 11
}
```

**Failure action:** If `execution_mode: "MANUAL"` — check `config/compliance_gate.json` inside
the container: all 11 `rts6_*` flags must be `true`, AND `AUTO_EXECUTE=true` in `.env` (step 4).

---

## T−20 min: Data layer

### 6 — D26 HMM weights show APAC-heavy allocation

```fish
curl -s -G "http://localhost:9000/exec" \
    --data-urlencode "query=SELECT opportunity_weights, n_observations, cold_start FROM p3_d26_hmm_opportunity_state ORDER BY last_updated DESC LIMIT 1" \
    | jq '.dataset[0]'
```

**Expected:**
```json
["{\"NY\": 0.1, \"LON\": 0.1, \"APAC\": 0.8}", 60, false]
```

**Failure action:** Run the D26 override (C12):
```fish
cmd-run nkd_pivot_d26_override.py
```
Then re-check.

### 7 — D34 trail table exists and is accessible

```fish
curl -s -G "http://localhost:9000/exec" \
    --data-urlencode "query=SELECT count() FROM p3_d34_nkd_trail_state" \
    | jq '.dataset[0][0]'
```

**Expected:** `0` (no trail events yet) or any integer ≥ 0 if a prior APAC session ran.

**Failure action:** `0` means table exists but empty — that is correct. If the query errors
(`table not found`), re-run `cmd-run init_questdb.py` to apply M048.

### 8 — No stale open NKD positions in Redis

```fish
set -gx REDIS_PASSWORD (grep '^REDIS_PASSWORD=' ~/captain-system/.env | cut -d= -f2)
docker exec captain-system-redis-1 redis-cli -a "$REDIS_PASSWORD" --no-auth-warning \
    HGETALL captain:open_positions
```

**Expected:** Empty output (no open positions pre-session). If last session had a TP/SL hit,
all positions will have been removed automatically.

**Failure action:** If stale NKD positions exist from a crashed session, manually remove:
```fish
docker exec captain-system-redis-1 redis-cli -a "$REDIS_PASSWORD" --no-auth-warning \
    HDEL captain:open_positions <signal_id>
```
Only do this if the position is confirmed closed in the broker UI.

### 9 — No stale bracket:pending entries

```fish
docker exec captain-system-redis-1 redis-cli -a "$REDIS_PASSWORD" --no-auth-warning \
    KEYS "bracket:pending:*"
```

**Expected:** Empty list. `bracket:pending` entries have a 10-second TTL (set by B3), so
stale entries expire automatically. If any exist, wait 10 seconds and re-check.

---

## T−10 min: Connectivity

### 10 — TopstepX authentication succeeds

```fish
dco exec -T captain-online python3 -c "
import sys; sys.path.insert(0, '/app')
from shared.topstep_client import get_topstep_client
c = get_topstep_client()
tok = c.authenticate()
print('AUTH OK — token prefix:', tok[:12] if tok else 'NONE')
"
```

**Expected:** `AUTH OK — token prefix: eyJhbGciOi` (or similar JWT prefix). No exception.

**Failure action:** Check `TOPSTEP_API_KEY` and `TOPSTEP_USERNAME` in `.env`. If network error,
check VPN/internet. If 401, the API key may have rotated — update `.env` and `dco up -d`.

### 11 — INSTANCE_PARITY is correct for this tower

```fish
dco exec -T captain-online sh -c 'echo INSTANCE_PARITY=$INSTANCE_PARITY'
```

**Expected:**
- Tower A (Nomaan): `INSTANCE_PARITY=0`
- Tower B (Isaac): `INSTANCE_PARITY=1`

If blank/empty, behaviour is single-instance (takes all signals — fine for tower A if
tower B is offline, but verify intent).

**Failure action:** Set correct value in `.env` and `dco up -d captain-online`.

---

## T−5 min: Live readiness

### 12 — captain-online logs are clean (no ERROR in last 60 lines)

```fish
dco logs --tail=60 captain-online | grep -iE "ERROR|CRITICAL|exception|traceback" | tail -10
```

**Expected:** No output (zero matches).

**Failure action:** Read the full error context: `dco logs --tail=100 captain-online`. Fix
the root cause — common sources: missing Redis key, QuestDB connection refused, import error
after deploy.

### 13 — captain-command logs are clean

```fish
dco logs --tail=60 captain-command | grep -iE "ERROR|CRITICAL|exception|traceback" | tail -10
```

**Expected:** No output.

### 14 — NKD trail block is importable (guards against Python syntax error)

```fish
dco exec -T captain-online python3 -c "
import sys; sys.path.insert(0, '/app')
from captain_online.blocks.b7b_nkd_trail import scan_nkd_trails, compute_nkd_phase, sample_isaac_jitter
print('b7b_nkd_trail import OK')
"
```

**Expected:** `b7b_nkd_trail import OK`

**Failure action:** A Python error here means a code/deploy problem. Rebuild and redeploy:
```fish
for svc in captain-offline captain-online captain-command
    rm -rf $svc/_config; cp -r config $svc/_config
end
dco build --no-cache captain-online && dco up -d captain-online
```

---

## At 18:00 ET: Session open monitoring

These are **watch** steps — run once, then monitor output.

### 15 — Tail captain-online for APAC session open

```fish
dco logs -f captain-online 2>&1 | grep -iE "APAC|NKD|trail|b7b|scan_nkd|is_nkd_trail|phase_a|TAKEN"
```

**Expected sequence (18:00–18:10 ET):**
```
ON-B9: APAC session open triggered
ON-B1: NKD data ingested
ON-B2: NKD regime computed
ON-B4: NKD kelly_contracts=1 (or similar)
ON-B6: NKD signal generated is_nkd_trail=True tp_dollars=4450
ON-B7B-NKD: snapped_d_init=1025.00 phase=A
```
*(C15: snapped_d_init is fixed at $1025, NOT OR-range derived. Phase B starts at $2000 profit.)*

### 16 — Confirm signal includes trail fields (after B6 fires)

```fish
set -gx REDIS_PASSWORD (grep '^REDIS_PASSWORD=' ~/captain-system/.env | cut -d= -f2)
docker exec captain-system-redis-1 redis-cli -a "$REDIS_PASSWORD" --no-auth-warning \
    XREVRANGE captain:signals:primary_user + - COUNT 1 \
    | grep -E "is_nkd_trail|tp_dollars|snapped_d_init"
```

**Expected:** All three keys present in the latest signal:
```
is_nkd_trail    True
tp_dollars      4450
snapped_d_init  1025.0
```
*(C15: snapped_d_init = 1025.0 fixed. On Isaac tower (parity=1) the signal also contains `jitter_j`, `jitter_x`, `jitter_y` and `tp_level` is placed at `4450 + J` — C16.)*

**Failure action:** If `is_nkd_trail` is absent or `False`, D00 bootstrap (step 1–2) didn't
complete. The trail block will not activate. Manually stop the trade if a position was taken.

### 17 — Confirm bracket order IDs captured (after TAKEN)

Once the GUI shows TAKEN (or `captain:commands` channel shows a TAKEN message), check that
bracket order IDs arrived via UserStream:

```fish
docker exec captain-system-redis-1 redis-cli -a "$REDIS_PASSWORD" --no-auth-warning \
    HGETALL captain:open_positions \
    | grep -E "sl_order_id|tp_order_id|is_nkd_trail"
```

**Expected:** `sl_order_id` and `tp_order_id` are integers (real broker order IDs), NOT the
string `"BRACKET"` (placeholder before UserStream resolution).

**Failure action:** If still `"BRACKET"` after 30 seconds, UserStream bracket capture (C5)
may not have resolved. Check `dco logs --tail=30 captain-online | grep -i bracket`.

### 18 — Trail block actively modifying (after position fills)

After the entry fills and trail block starts, D34 should populate within 30 seconds:

```fish
curl -s -G "http://localhost:9000/exec" \
    --data-urlencode "query=SELECT signal_id, phase, current_stop_price, modify_seq, last_updated FROM p3_d34_nkd_trail_state ORDER BY last_updated DESC LIMIT 5" \
    | jq '.dataset'
```

**Expected:** Rows appearing with `phase=A`, `modify_seq` incrementing, `current_stop_price`
stepping upward as NKD price climbs.

**Failure action:** If D34 is still empty 2 minutes after fill, check:
```fish
dco logs --tail=50 captain-online | grep -iE "ON-B7B|scan_nkd|nkd_trail"
```
A silent error in the trail loop (caught by `except Exception as e: logger.error(...)`) would
appear here.

---

## GO / NO-GO summary

| Check | Status |
|-------|--------|
| 1. bootstrap_production.py ran | ☐ |
| 2. D00 NKD has trail fields | ☐ |
| 3. All containers Up | ☐ |
| 4. AUTO_EXECUTE=true | ☐ |
| 5. Compliance gate AUTO | ☐ |
| 6. D26 APAC=0.8 | ☐ |
| 7. D34 table accessible | ☐ |
| 8. No stale open positions | ☐ |
| 9. No stale bracket:pending | ☐ |
| 10. TopstepX auth OK | ☐ |
| 11. INSTANCE_PARITY correct | ☐ |
| 12. captain-online logs clean | ☐ |
| 13. captain-command logs clean | ☐ |
| 14. b7b_nkd_trail importable | ☐ |
| 15. Isaac tower: INSTANCE_PARITY=1 confirmed (C16 jitter active) | ☐ |
| 16. F2 sanity check: all 4 fields `True`, Total keys 19 (step 2a — both towers) | ☐ |

All 16 boxes checked = **GO**. Any ❌ = fix before 18:00 ET.

> **C16 Isaac tower gate (§14 new):** Run inside captain-online on Isaac tower:
> ```fish
> dco exec captain-online printenv INSTANCE_PARITY
> # Must return "1"; if blank or "0" jitter J=0 (safe but anti-copy-trade disabled)
> ```
> Phase B now starts at $2000 profit (flat $1000 buffer). Phase C starts at $3000 ($450 buffer).
> Initial SL = **$1025 fixed** (41 NKD ticks = 1025 / (5 × 5)).
> Isaac tower: broker SL buffer = 1000 + J, TP bracket = 4450 + J (sampled once per trade).

---

## Quick-roll commands (if anything needs a restart)

```fish
# Env-only change (AUTO_EXECUTE, INSTANCE_PARITY) — no rebuild
dco up -d

# Code change already on disk — rebuild a single service
for svc in captain-offline captain-online captain-command
    rm -rf $svc/_config; cp -r config $svc/_config
end
dco build --no-cache captain-online && dco up -d captain-online

# Full restart of all trading services (no rebuild)
dco restart captain-online captain-command captain-offline

# Emergency MANUAL mode (stops all new order placement mid-session)
# Edit config/compliance_gate.json — set any one rts6_* flag to false
# OR set AUTO_EXECUTE=false in .env and dco up -d
```

---

## Revert D26 override (if you want to restore equal 1/3 session weights)

```fish
cmd-run nkd_pivot_d26_override.py --revert
```

Takes effect at next SOD compute cycle (~19:00 ET) without requiring a service restart.
