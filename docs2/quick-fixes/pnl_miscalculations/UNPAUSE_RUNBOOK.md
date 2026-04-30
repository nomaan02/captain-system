# Bug A Unpause Runbook — 2026-04-29

**Branch:** `fix/b7-pnl-multiplier-tier1`
**Affected commit base:** parent of `c4c08ad` (`migration/decimal-phase-c` tip)

## Pre-conditions (must all be true)

- [ ] Both towers paused (no AUTO_EXECUTE active anywhere).
- [ ] No open positions on the broker side (`Account/positions` empty for the active account).
- [ ] You have the live `TOPSTEP_*` env vars set so the recompute script can reach `Account/search`.
- [ ] You've reviewed the diff on `fix/b7-pnl-multiplier-tier1` against `migration/decimal-phase-c` (parent).
- [ ] Tests pass:
  ```fish
  PYTHONPATH=./:./captain-online:./captain-offline:./captain-command \
    python3 -B -m pytest tests/test_b7_pnl_per_symbol.py -v
  ```
  Expected: **27 passed**.

## Path A — Minimum to resume trading TODAY

This is the critical path. Skip Path B until trading is restored.

### A1. Merge the fix to your operating branch

```bash
# On Tower A
cd ~/captain-system
git fetch origin   # or whichever remote hosts the branch
git checkout migration/decimal-phase-c   # your current operational branch
git merge --no-ff fix/b7-pnl-multiplier-tier1
git rev-parse HEAD   # record this — Tower B must match
```

Replicate exactly on Tower B. Confirm `git rev-parse HEAD` matches before proceeding.

### A2. Build & deploy

Per `MONETARY_DECIMAL_MERGE_VALIDATION.md` §4.1:

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml down
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.local.yml ps   # all healthy
```

No new migrations are needed — schema is unchanged.

### A3. Sanity-check the patched module loaded

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T \
  -e PYTHONPATH=/app captain-online python -c \
  "from captain_online.blocks import b7_position_monitor as b7; \
   print('helper present:', hasattr(b7, '_resolve_point_value')); \
   print('cache type:', type(b7._POINT_VALUE_CACHE)); \
   print('error class:', b7.PointValueResolutionError.__name__)"
```

Expected:
```
helper present: True
cache type: <class 'dict'>
error class: PointValueResolutionError
```

### A4. Reset capital state to broker truth

Dry-run first to inspect the proposed delta:

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T \
  -e PYTHONPATH=/app captain-offline python /captain/scripts/reset_capital_state_to_broker_truth.py \
  --user primary_user --account 20319811
```

Carefully read the output. The "current total_capital" should be ~$91K (the corrupted value). The "proposed total_capital" should be the broker's actual balance (~$147K depending on the actual −$2.7K cumulative).

If the delta looks correct, apply:

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T \
  -e PYTHONPATH=/app captain-offline python /captain/scripts/reset_capital_state_to_broker_truth.py \
  --user primary_user --account 20319811 --apply
```

This writes:
- D16 `total_capital` = broker balance (clears silo drawdown alarm)
- D08 `current_balance` and `current_drawdown` (TSM checks resume on truth)
- D23 row with `l_t=0`, `n_t=0`, `l_b={}`, `n_b={}` (intraday CB clean)

The script will refuse if `|delta| < $1000` (sanity guard — pass `--inflation-threshold 0` only if you really mean it).

Verify via QuestDB web console (port 9000):
```sql
SELECT total_capital FROM p3_d16_user_capital_silos
WHERE user_id='primary_user'
LATEST ON last_updated PARTITION BY user_id;

SELECT l_t, n_t FROM p3_d23_circuit_breaker_intraday
WHERE account_id='20319811'
LATEST ON last_updated PARTITION BY account_id;
```

### A5. Repeat A1–A4 on Tower B

Capital state is per-user, NOT per-tower — so Tower B sees the same QuestDB and the writes from A4 affect both. Tower B only needs the code deployment (A1–A3) and a sanity check.

### A6. Canary trade

Before opening the full universe, trade only ES (the asset that was unaffected by Bug A — coincidentally the only one where the buggy default 50 matches D00):

```bash
# Edit config/compliance_gate.json to allow only ES, OR
# Use D00 captain_status to narrow the universe to ES briefly.
# Confirm AUTO_EXECUTE=true in env.
```

Trade 1 ES position. Watch:
1. The position appears in B7's open_positions (logs).
2. On TP/SL/Time exit, D03 row is written with correct gross_pnl.
3. D16 total_capital adjusts by the correct $50/point amount.
4. Telegram notification arrives with sane PnL.

If anything looks off, stop and investigate before opening other instruments.

### A7. Restore full universe

Once ES canary passes, restore the active universe and resume.

### A8. Telegram correction notice

Send a manual notice retracting the false 39.2% drawdown alert:

> CORRECTION: The 2026-04-29 silo drawdown alert was caused by a PnL multiplier bug in B7 that inflated non-ES trade PnL by 5×–100×. Actual cumulative drawdown was ~1.8% / -$2,700, well within tolerance. Bug A patch deployed; trading resumed.

---

## Path B — Historical D03 backfill (NOT critical for trading; do this AFTER Path A)

D03's historical PnL is still inflated for every non-ES trade. This affects:
- Reports (RPT-04 / RPT-12 show wrong numbers)
- Learner inputs (DMA / EWMA / Kelly / β_b will retrain on wrong data over time)
- Audit / compliance reads of D03

**Do NOT run this until you've audited every D03 reader (see the BLOCKING SAFETY GATE section of `scripts/backfill_d03_pnl_inflation.py`).** The current readers do raw `SUM(pnl)` and would double-count the corrected rows.

### B1. Generate the correction proposal

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T \
  -e PYTHONPATH=/app captain-offline python /captain/scripts/backfill_d03_pnl_inflation.py \
  --user primary_user \
  --proposal-out /captain/docs2/quick-fixes/pnl_miscalculations/backfill_proposal.md
```

Review the proposal markdown carefully. Cross-check the per-asset Σ delta against your TopstepX trade history export.

### B2. Audit the readers

Either:

- **Option B2a (recommended):** Update each reader listed in the script's
  BLOCKING SAFETY GATE to use `LATEST ON ts PARTITION BY trade_id` semantics.
  Roughly 10 file edits — non-trivial. Open a separate branch
  (`fix/d03-readers-latest-on`).

- **Option B2b:** Stop all D03 consumers (offline learners, reports, GUI),
  apply the backfill, then manually trigger a clean re-train of the learners
  on the corrected data before bringing consumers back up. Riskier.

- **Option B2c (alternative):** Pivot to backfill strategy 3.3-E
  (UPSERT in place + parallel `p3_d03_corrections_log` audit table). Requires
  a small script change. Avoids reader fallout entirely. Recommended over
  B2a if time pressure is a factor — flag this and I'll write the variant.

### B3. Apply the backfill

Only after B2 is complete:

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T \
  -e PYTHONPATH=/app captain-offline python /captain/scripts/backfill_d03_pnl_inflation.py \
  --user primary_user --apply --readers-audited
```

### B4. Recompute downstream learners (in dependency order)

After the backfill, the learners need to re-fit on corrected data:

```
D03 (corrected) → D02 DMA       (Off B1)
                → D04 BOCPD     (Off B2)
                → D05 EWMA      (Off B8) → D12 Kelly (Off B8)
                → D25 β_b       (Off B8)
```

Trigger Off B1, B2, B8 on the corrected D03 rows. (No script for this yet — flag if you want a `recompute_learners_after_backfill.py` driver.)

---

## Rollback

If anything goes wrong during A4 (capital reset):

1. The original D16 / D08 / D23 rows are NOT deleted — the new rows are
   appended with a fresh `last_updated` timestamp. To revert, manually
   insert another row with the OLD values and a fresh timestamp:

   ```sql
   -- Get the prior values from the second-latest row:
   SELECT * FROM p3_d16_user_capital_silos
   WHERE user_id = 'primary_user'
   ORDER BY last_updated DESC LIMIT 2;
   ```

2. The b7 code patch is non-destructive: a `git revert` on the merge commit
   restores the old behaviour. (You'd be reverting back to the bug — only
   useful if the patch itself is somehow wrong.)

## Open follow-ups (after trading restored)

1. **Tier 2 hardening** — add `point_value` to `sanitise_for_api`'s returned dict.
2. **Tier 3 hardening** — replace remaining `50.0` defaults across the codebase
   with loud failures (b4_kelly_sizing, b5c_circuit_breaker, replay_engine,
   signal_replay, trade_source).
3. **Tier 4 startup validator** — `verify_d00_pricing.py` to halt startup if
   D00 is mis-bootstrapped.
4. **Bug B fix** — User Hub `GatewayUserTrade` → `actual_exit_price` enrichment
   (separate branch `fix/b7-exit-price-broker-fill`).
5. **D03 reader audit** — update SUM/SELECT readers to LATEST-ON semantics so
   the backfill (Path B) becomes safe.
