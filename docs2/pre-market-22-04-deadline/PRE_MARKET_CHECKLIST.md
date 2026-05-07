---
title: Pre-Market Readiness — Wed 22 Apr 2026 (NY Open 09:30 ET)
date: 2026-04-22
author: Claude (Opus 4.7)
session_basis: Session 8 (post-amendment-plan execution + replay verification)
status: GATE — DO NOT enable AUTO_EXECUTE on either tower until §6 Go/No-Go passes
audience: Nomaan (tower 1) + Isaac (tower 2)
target: both towers automatically trading from NY open today, all DBs populating, all offline jobs healthy
---

# Pre-Market Readiness Checklist — 2026-04-22

> **One-line state:** *the code is in good shape; the data plane and the operational gates around it are not yet proven for today.* The amendment-plan code surgery (Phases 1–7) is shipped and pushed; Phase 8 (end-to-end replay verification) is **in progress and not yet signed off**. We have an unverified replay run, two known data-quality risks (ZB/ZN tiny SL, eval-TSM defaults firing silently), and an untested live-execution leg (broker round-trip, WS reconnect, PEL recovery). Going live without §3 + §4 done is a real risk of either (a) the system trading nothing, or (b) the system trading the wrong sizes on treasuries.

---

## 1. Current commit state (both towers must match)

Latest pushed to `origin/main` and `multi-user/main`: **`5df5041`** — *fix(replay+gui): stop duplicate signal stacking in panel*.

Run on **both** towers and confirm:

```fish
cd ~/captain-system
git fetch --all --prune
git log -1 --oneline
# expected: 5df5041 fix(replay+gui): stop duplicate signal stacking in panel
git status
# expected: clean (no local changes)
```

Tower-1 branch must equal tower-2 branch exactly. If the towers diverge **stop here** — equal binaries are a precondition for `INSTANCE_PARITY` mode to give the deterministic alternation it claims.

---

## 2. What is VERIFIED working (do not retest)

These ten items have explicit in-session evidence, are committed, and are **not in scope for further validation** today:

| Area | Commit(s) | Evidence |
|------|-----------|----------|
| TopstepX REST bar-key compatibility (`o`/`h`/`l`/`c`/`v`/`t` short keys) | `d7ed724`, `ae46806` | Patched in `b1_features.py`, `b1_data_ingestion.py`, `b7_position_monitor.py`. Live REST calls now consume short-key payloads. |
| ProjectX endpoint alignment (Position close, Order modify, search_trades, /History/retrieveBars, /Contract/search) | `1944933`, `b63508b` | Topstep client reshaped to match ProjectX gateway spec. |
| `topstep_params` + `topstep_state` propagation chain (B8 SOD → D08 → B1 → B4/B5C) | `7185e4e`, `b5aa811` | Phase-1 fixes from amendment plan F-01/F-02/F-03. |
| B5C `L_halt` and `E_daily_exposure` SOD-freeze enforcement | `b5aa811` | F-07/F-08 from amendment plan. |
| B5C Layer 0 live `current_open_micros` from `open_positions` | `f412b20` | F-09 from amendment plan. |
| B2 regime-neutral log noise suppression | `c3b5baa` | F-05 from amendment plan. |
| Replay harness consolidation onto canonical B5C | `5b45702` | F-06/F-11/F-12 from amendment plan. |
| Eval TSM defaults documented + audit-logged | `31ab4d3` | F-14 from amendment plan. |
| Kelly SL unification via `shared.sizing_helpers.resolve_sizing_sl` (B4 ↔ B5C agreement on `rho_j`) | `f0ff19f`, `abff635`, `a185f4e` | Phase-2 of plan; SQL filter for non-null `or_range_first_m_min` confirmed by Isaac's diagnostic for all 8 assets. |
| Replay signal-batch cumulative-stacking + GUI dedup by `signal_id` | `5df5041` | This-session fix; replay-only on the backend, defense-in-depth on GUI for live B6 retries / PEL recovery. |

---

## 3. OUTSTANDING — must close before NY open (BLOCKING)

Ordered by criticality. Each item has an explicit pass condition.

### 3.1 — Re-run the full replay end-to-end with signal-stacking fix in place ⚠️ BLOCKING

**Why:** Phase-8 of the amendment plan is the final gate. It has not been completed cleanly. The previous run was contaminated by the cumulative-batch bug; we don't actually know yet whether the post-`5df5041` pipeline produces 5 distinct signals (one per OR breakout) with correct sizes.

**Run on tower 2:**

```fish
cd ~/captain-system
git pull origin main
cd captain-gui; npm run build; cd ..

# Whichever Python invocation the earlier diagnostic worked under:
set -x PYTHONPATH (pwd):(pwd)/captain-online
python scripts/replay_full_pipeline.py --date 2026-04-21 --session NY 2>&1 | tee /tmp/session8_replay_v3.log
```

**Pass conditions** (all must hold):

- [ ] Each `Signal batch received` line in the log shows exactly `1 signal(s)` — not 2, 3, 4, or 5.
- [ ] Distinct assets total ≤ 5 (one batch per OR breakout for the active asset set).
- [ ] No `DEFAULT_SL_POINTS=4.0` warnings from `resolve_sizing_sl` for any of the 8 assets.
- [ ] No `No pettersson_threshold for X` warnings (Phase-5 silenced these for `REGIME_NEUTRAL` assets).
- [ ] `tsm["topstep_state"]["computed_sod"]["L_halt"]` shows in B5C log lines for the trading account, **non-zero**, **not** `750` (the cold-start default for $150k × 0.5 × 0.01).
- [ ] B4 contracts logged for at least one micro asset; sizing not zero across the board.
- [ ] B6 publishes ≥1 distinct signal end-to-end to Redis stream:signals.

If any condition fails — **stop, do not enable `AUTO_EXECUTE`**. Paste the failing log lines and we triage.

### 3.2 — Verify D29 `or_range_first_m_min` is populated for every active asset ⚠️ BLOCKING

**Why:** Phase-2 of the plan made `resolve_sizing_sl` depend on this column. If a live session opens with no historical OR range for an asset, B4 falls through to `strategy.threshold` then `4.0` and silently mis-sizes (potentially 2–10× wrong).

```fish
docker compose exec questdb curl -s \
  "http://localhost:9000/exec?query=SELECT+asset_id%2C+or_minutes%2C+count(*)+as+n%2C+count(or_range_first_m_min)+as+n_with_range%2C+min(ts)%2C+max(ts)+FROM+p3_d29_opening_volumes+WHERE+or_range_first_m_min+IS+NOT+NULL+AND+or_range_first_m_min+%3E+0+GROUP+BY+asset_id%2C+or_minutes+ORDER+BY+asset_id" \
  | python3 -m json.tool
```

**Pass conditions:**

- [ ] Every asset_id traded today (ES, MES, NQ, MNQ, M2K, MYM, ZB, ZN — confirm against `config/contract_ids.json`) appears in the result.
- [ ] Each asset has **≥ 5 non-null, positive** `or_range_first_m_min` rows for `or_minutes=5` (matches `get_or_window_minutes` default and `bootstrap_opening_volumes._get_or_minutes`).
- [ ] `max(ts)` is within the last 30 days (otherwise the historical avg is stale relative to current vol regime).

If an asset is missing or has < 5 rows — re-run `scripts/bootstrap_opening_volumes.py` for that asset before market open. **Do not** trade an asset whose D29 history is empty.

### 3.3 — Resolve the ZB/ZN micro-SL anomaly ⚠️ BLOCKING for treasuries (can defer if treasuries excluded)

**Why:** Post-Phase-2 verification on tower 2 showed `resolved_sl` values of **0.0058 pts (ZB)** and **0.0030 pts (ZN)**. These imply per-contract dollar risk of cents, which would explode Kelly contracts on those assets if traded live.

Two outcomes:

**Option A — investigate today (preferred if time permits):**

```fish
# Query raw D29 values for ZB/ZN
docker compose exec questdb curl -s \
  "http://localhost:9000/exec?query=SELECT+ts%2C+or_minutes%2C+or_range_first_m_min%2C+volume_first_m_min+FROM+p3_d29_opening_volumes+WHERE+asset_id+IN+('ZB','ZN')+AND+or_range_first_m_min+IS+NOT+NULL+ORDER+BY+ts+DESC+LIMIT+30" \
  | python3 -m json.tool
```

Expected ZB/ZN OR ranges from real bar data should be on the order of **0.1–0.5 points** (treasuries quote in 32nds; one tick ≈ $15.625 for ZB / $7.8125 for ZN). If the stored values are 100× smaller than expected, the bootstrap is storing fractional 32nds as decimal points without conversion. Fix the ingestion path in `bootstrap_opening_volumes.py` and re-bootstrap ZB/ZN.

**Option B — exclude treasuries from today (fast, safe):**

Set ZB and ZN to `captain_status = 'INACTIVE'` in `p3_d00_asset_universe` for today; trade only the equity micros + ES/NQ:

```fish
docker compose exec questdb curl -s \
  "http://localhost:9000/exec?query=UPDATE+p3_d00_asset_universe+SET+captain_status%3D'INACTIVE'+WHERE+asset_id+IN+('ZB','ZN')"
```

Re-enable after the ingestion fix is verified post-market.

- [ ] Decision recorded (A or B), action taken.

### 3.4 — Verify TopstepX live REST/WS handshake on both towers ⚠️ BLOCKING

**Why:** All of the above is academic if the broker session can't actually open. None of the recent commits exercised the live REST or WebSocket lifecycle — replay seeds the quote cache directly.

```fish
# On EACH tower, after captain-online container is up:
docker compose -f docker-compose.yml -f docker-compose.local.yml logs --tail 200 captain-online \
  | grep -iE "topstep|projectx|auth|jwt|reconnect|websocket|marketstream|userstream"
```

**Pass conditions:**

- [ ] One `Auth token acquired` (or equivalent) log line within the last 30 min.
- [ ] One `MarketStream subscribed` and one `UserStream subscribed` line.
- [ ] Zero `auth failed`, `403`, `connection refused`, or `reconnect backoff exhausted` lines in the most recent restart cycle.
- [ ] `scripts/verify_topstep_integration.py` exits 0 (this validates contract IDs against /Contract/search live).

```fish
~/.venv-captain/bin/python3 scripts/verify_topstep_integration.py
```

If auth fails — the new `default ProjectX live flag to False` change in `250e8c6` may need `TRADING_ENVIRONMENT=live` re-confirmed in `.env`.

### 3.5 — Confirm `computed_sod` is populated in `p3_d08_tsm_state` for the trading account ⚠️ BLOCKING

**Why:** F-01/F-02/F-03 are shipped, but the only proof that the SOD job actually wrote `computed_sod` is in production-like data, not unit tests. Without it, B5C's `L_halt` / `E_daily_exposure` fall back to the `c × e × A` recomputation path (F-07/F-08 fallback branch), which works but is no longer SOD-frozen.

```fish
docker compose exec questdb curl -s \
  "http://localhost:9000/exec?query=SELECT+account_id%2C+last_updated%2C+topstep_state+FROM+p3_d08_tsm_state+WHERE+account_id+IN+('20319784')+ORDER+BY+last_updated+DESC+LIMIT+1" \
  | python3 -m json.tool
```

**Pass conditions:**

- [ ] `topstep_state` is non-null and parses as JSON.
- [ ] `topstep_state.computed_sod` exists and contains `L_halt > 0`, `E_daily_exposure > 0`, `N_max_trades`, `f_A`.
- [ ] `last_updated` timestamp is from the most recent SOD reconciliation (within last 24h, after Captain Command B8 last ran).

If `computed_sod` is missing — Captain Command's B8 reconciliation hasn't fired yet for this account, or is firing but the F-03 row-rewrite is still mis-targeted. Force a manual B8 SOD run and re-query.

### 3.6 — Compliance gate config sanity ⚠️ BLOCKING

**Why:** `config/compliance_gate.json` is the last line of defense in front of `b3_api_adapter.send_signal`. If it's misconfigured (e.g., empty allow-list, blanket block), nothing trades; if it's permissive (no daily-loss block, no contract cap), bad fills go through.

```fish
cat config/compliance_gate.json
```

**Pass conditions:**

- [ ] All 8 (or 6 if treasuries excluded per 3.3-B) trading symbols are in the allow-list.
- [ ] Per-account daily loss limit ≤ TSM `max_drawdown_limit` (i.e. $4,500 for the 150k eval).
- [ ] Total contract cap ≤ TSM `max_contracts` (15 for the 150k eval).
- [ ] No stale "block-all" entry from a prior incident.

### 3.7 — Both towers' `INSTANCE_PARITY` correctly set ⚠️ BLOCKING (multi-instance only)

```fish
grep '^INSTANCE_PARITY=' .env
```

- [ ] Tower 1: `INSTANCE_PARITY=0`
- [ ] Tower 2: `INSTANCE_PARITY=1`
- [ ] After the first session of the day, tail one PARITY CHECK line from each tower's captain-command logs and verify the `key=` field is identical for the same batch (e.g. `key='2026-05-07|4|primary_user|NKD'`) — both towers must compute the same content-hash key, with opposite `signal_parity` values, so exactly one of them takes the batch (`orchestrator._check_parity_skip`). The legacy `captain:signal_counter:{date}` Redis key was retired in May 2026 — the partition is now drift-proof via content hashing of (date, session_id, user_id, sorted-asset-set).

If `INSTANCE_PARITY` is empty on both, both towers will execute every signal — **double the size, double the slippage**. If set to the same value on both, half the signals will be dropped on both towers — zero trades.

### 3.8 — Cron services + VIX freshness ⚠️ BLOCKING

```fish
systemctl is-active cron
crontab -l | head -10

# VIX must be today's date (or last business day on Mon)
tail -3 ~/captain-system/data/vix/vix_daily_close.csv
tail -3 ~/captain-system/data/vix/vxv_daily_close.csv
```

- [ ] `cron` is `active`.
- [ ] VIX/VXV files have today's date.
- [ ] If stale: `bash ~/captain-system/scripts/update_vix_data.sh` and re-check.

If VIX is stale, AIM-04 / AIM-11 modifiers are computed against last-week's volatility regime — sizing will be miscalibrated.

---

## 4. PROVISIONAL — accept the risk OR mitigate today (HIGH but not BLOCKING)

These don't necessarily stop trading but should be either consciously accepted in writing or mitigated.

### 4.1 — `L_halt = $750` on cold start may be unworkably tight on multi-contract entries

Documented in amendment plan F-10. With `c=0.5, e=0.01` on $150k, even **4 ES contracts at the realised SL** trips L1. After Phase-2 fixes the realised per-contract risk is closer to spec, so L1 will fire less often than the original audit suggested — but expect some legitimate signals to be blocked at L1 today.

**Mitigation options:**

- Accept and observe (recommended for first live day). L1 is doing exactly what spec says.
- Tune `c` upward in `config/tsm/providers/topstep_150k_eval.json` (e.g. `c=0.75`). Requires a TSM reload + B8 SOD re-run to propagate to `computed_sod.L_halt`. Don't touch this on day 1 unless the L1-block rate is so high (>50% of signals) the system trades nothing.

- [ ] Decision recorded.

### 4.2 — Eval account silent defaults: `pass_probability`, `evaluation_end_date`, `max_daily_loss`

Phase-7 (`31ab4d3`) added `_notes` documentation in `topstep_150k_eval.json` and B4 now logs INFO when each default fires. Read those INFO lines once at session open today; if any default fires for the wrong reason (e.g., `pass_probability=0.85` because no Pseudotrader data exists yet — correct; vs. fired because a JSON load error wiped the field — wrong), catch it before market open.

```fish
docker compose logs captain-online | grep -i "ON-B4: .*default"
```

- [ ] Defaults fire for the documented reasons only.

### 4.3 — `OR_window_minutes` legacy 5-vs-15 mismatch

The `abff635` fix aligned `get_or_window_minutes` to default 5 (matching `bootstrap_opening_volumes._get_or_minutes`). If an asset's `locked_strategy.strategy_params.OR_window_minutes` is explicitly `15`, Phase-2's tolerant fallback in `_get_historical_or_range` will pick the bucket with the most non-null rows — usually the 5-min bucket. Side-effect: B6's `or_range` features will still be measured over the strategy's declared 15-min window in live, but B4's risk denominator will be sized off the 5-min historical avg. Same shape as the original F-04 divergence, smaller magnitude.

- [ ] If any asset has `OR_window_minutes != 5`, document it. Otherwise no-op.

### 4.4 — `signal_id` dedup applies only to fresh GUI loads after `npm run build`

The cached old bundle in any open browser tab will still run pre-`5df5041` `addSignal` (no dedup). After `npm run build`, every connected GUI must hard-reload (Ctrl+Shift+R) before market open to pick up the new bundle. Otherwise the symptom recurs visually, even with the backend correct.

- [ ] All operator browsers hard-reloaded.

---

## 5. NOT IN SCOPE for today — known limitations being lived with

These are deliberately deferred and should not block go-live.

| Item | Why deferred | Risk if it bites today |
|------|--------------|------------------------|
| Pseudotrader-driven retune of `c`, `e`, `lambda` (F-10 grid search) | Needs ≥30 days of live trade data; cannot compute from cold | L1 may be too tight; observable, recoverable next session |
| D33 `session_date` STRING-vs-TIMESTAMP cleanup | Audit-flagged, no functional impact today | None |
| Multi-instrument `phi` selection in B8 SOD (currently uses ES default) | Eval account trades multiple instruments; `phi` is a fee/slippage proxy | SOD math slightly conservative for non-ES instruments — under-sizes by single-digit % |
| F-13 / Q-01 — `p2_d07_regime_models` separate table | All assets are `REGIME_NEUTRAL` for V1 by design (P2 confirmed) | None today |
| Live PEL recovery test (kill Command mid-batch, verify replay-on-restart) | Destructive; rehearse outside market hours | If Command crashes during live trading, recovery path is untested. The retry/PEL drain code at `orchestrator.py:185-197` exists but hasn't been exercised end-to-end on this branch. |

---

## 6. Go / No-Go gate (run at T-15 minutes before NY open)

All BLOCKING items in §3 must be checked off. Provisional items in §4 must be either checked off or have an explicit accepted-risk decision.

```fish
# Quick green-light check on each tower
echo "=== git ===";          git log -1 --oneline
echo "=== containers ===";   docker compose -f docker-compose.yml -f docker-compose.local.yml ps
echo "=== cron ===";         systemctl is-active cron
echo "=== auto_execute ==="; grep '^AUTO_EXECUTE=' .env
echo "=== parity ===";       grep '^INSTANCE_PARITY=' .env
echo "=== vix ===";          tail -1 ~/captain-system/data/vix/vix_daily_close.csv
```

| Gate | Pass criterion |
|------|----------------|
| §3.1 replay | Clean run, all assertions met, log archived |
| §3.2 D29 | All active assets have ≥5 non-null OR rows |
| §3.3 ZB/ZN | Either fixed (Option A) or excluded (Option B) |
| §3.4 broker | Live REST + WS handshake confirmed both towers |
| §3.5 SOD | `computed_sod.L_halt > 0` for trading account |
| §3.6 compliance | Allow-list, caps confirmed |
| §3.7 parity | `INSTANCE_PARITY` set per-tower, counter sync confirmed |
| §3.8 cron + VIX | Cron active, VIX is today's |
| §4.1 L_halt risk | Decision recorded |
| §4.4 GUI cache | All browsers hard-reloaded |

**Only after all green:** flip `AUTO_EXECUTE=true` in `.env` on both towers and restart `captain-command`:

```fish
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build captain-command
docker compose -f docker-compose.yml -f docker-compose.local.yml logs --tail=20 captain-command | grep -i "auto.*execute\|AUTO_EXECUTE"
```

Confirm the log shows auto-execute is on.

---

## 7. First-30-minutes live monitoring (NY 09:30 – 10:00 ET)

Watch for these in real time. Any of them = manual `AUTO_EXECUTE=false` + investigate.

- **Order rejected**: any `b3_api: order_rejected` log = stop, the system is sending orders the broker disagrees with.
- **Position monitor mismatch**: `B7: position not found in TopstepX` = Captain thinks it has a position the broker doesn't (or vice versa).
- **L1/L2 block rate > 50%**: trading nothing because of CB. Defer to §4.1 mitigation.
- **`Signal batch received` for the same asset twice within 10s**: dedup not working post-cache-bust; force browser hard reload.
- **Reconnect storm**: `WebSocket disconnected` more than 3× in 10 min. Auth, network, or topstep API outage.
- **PEL grew non-zero and didn't drain**: a Command consumer is stuck.

```fish
# Run these in parallel terminals during the first 30 minutes
docker compose -f docker-compose.yml -f docker-compose.local.yml logs -f captain-online captain-command
redis-cli -a "$REDIS_PASSWORD" XLEN stream:signals
redis-cli -a "$REDIS_PASSWORD" XPENDING stream:signals command_group_signals
```

---

## 8. Rollback plan

If the system misbehaves after open and a clean kill is needed:

```fish
# 1. Stop new orders immediately
sed -i 's/^AUTO_EXECUTE=.*/AUTO_EXECUTE=false/' .env
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build captain-command

# 2. Flat any open positions via TopstepX UI or scripts/paper_trader.py emergency-flat
#    (do NOT rely on Captain's flat-by logic if you've stopped Command)

# 3. If a code regression is suspected, revert to last-known-good
git revert HEAD          # only if the last commit is the suspect
# OR
git checkout a185f4e     # last-known-good before signal-stacking fix; lose 5df5041's improvements
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build
```

---

## 9. Critical-path summary

If you do nothing else, do these in order before 09:30 ET:

1. `git pull` on both towers; verify `git log -1` shows `5df5041`. *(2 min)*
2. `npm run build` in `captain-gui/`; hard-reload all open browsers. *(3 min)*
3. Re-run §3.1 replay; archive the clean log. *(5 min)*
4. Run §3.2 D29 query; confirm coverage. *(2 min)*
5. Decide §3.3 ZB/ZN — fix or exclude. *(5–30 min)*
6. Run §3.4 / §3.5 / §3.6 / §3.7 / §3.8 quick checks. *(10 min)*
7. Flip `AUTO_EXECUTE=true` only after §6 gate passes. *(2 min)*
8. Watch first 30 min per §7.

**Minimum time from now to safe go-live: ~30–45 minutes** (assuming §3.3 is Option B / exclude treasuries; add 30+ if Option A / fix ingestion).

---

## 10. Honest confidence assessment

| Subsystem | Confidence | Rationale |
|-----------|-----------|-----------|
| Signal generation pipeline (B1→B6) | **HIGH** | All amendment-plan blockers shipped; replay validated for sizing; this-session signal-stacking fix landed |
| Per-asset SL resolution | **HIGH** for equities, **LOW** for ZB/ZN | Phase-2 working for 6/8 assets; treasuries unresolved (§3.3) |
| TopstepX REST + WebSocket lifecycle | **MEDIUM** | Code aligned with ProjectX spec, but no live-session evidence on this branch — first real test is this morning |
| Order placement round-trip + B7 monitor | **MEDIUM** | Code paths haven't been exercised end-to-end on the post-amendment branch |
| Compliance gate | **MEDIUM** | Config exists; behaviour under live tick rate not stress-tested this week |
| Multi-instance parity | **MEDIUM** | Counter-based design is sound; deterministic alternation only verified via unit tests, not two live towers |
| Offline jobs (DMA, BOCPD, EWMA, Kelly update) | **MEDIUM-HIGH** | Triggered by trade outcomes; will not run today until first round-trip completes successfully. First-trade smoke is the real validation. |
| GUI signal panel | **HIGH** post-cache-bust | Dedup landed; depends on §4.4 being executed |

**Net:** the system is ready to *attempt* to trade today. The blocking checks in §3 take ~30–45 minutes. After that, the dominant remaining risk is the unproven live-execution leg (§3.4 / §7) — which can only be validated by trading. Recommend:

- Trade with **`AUTO_EXECUTE=true`** on the eval account (max risk = $4.5k MDD) but **NOT** on any live-funded account today.
- Treasuries excluded today (Option B) unless §3.3-A completes cleanly.
- Operator on-call for the first 90 minutes post-open with §8 rollback ready.

---

*End of pre-market checklist. Update this file with timestamps as items are checked off; commit before NY open as the "we shipped knowing this" record.*
