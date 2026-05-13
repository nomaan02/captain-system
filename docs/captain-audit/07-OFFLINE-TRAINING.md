# 07 — Offline training & ML hooks

**TL;DR**

- Tiered AIM retrain cadence is enforced inside Offline `_run_weekly` / `_run_monthly` ([06](06-SCHEDULED-TASKS.md)).
- AIM-16 HMM trainer exists (`b1_aim16_hmm.py`) — **orchestrator wiring disputed** (finding **09-I01**).
- ORB parameters consume **`locked_strategy` JSON** from D00 — not recomputed online each session start ([07.5](#075-orb--locked-strategy)).

**Audit stamp:** commit `ef24edf632eba2462527505d28c5a75b133fb612`, `2026-05-12T14:08:20Z`

## 07.1 HMM regime (AIM-16)

**Analog:** A traffic camera clustering congestion into {quiet, normal, jam} — HMM learns transition dynamics between latent states; session budgeting reads posterior weights.

| Concern | Detail | Anchor |
|---------|--------|--------|
| Train function | `train_aim16_hmm` returns dict for D26 | `b1_aim16_hmm.py` ~72+ |
| Persist | `save_hmm_state` UPSERT merge | same ~177–216 |
| Target table | `p3_d26_hmm_opportunity_state` | INSERT inside `save_hmm_state` |
| Wiring gap | Weekly offline loop calls `run_tier_retrain`, **not** obviously `train_aim16_hmm` | See `.audit-cache/spec-audit.md` |

Validate table freshness:

```bash
curl -s -G "http://127.0.0.1:9000/exec" \
  --data-urlencode "query=SELECT asset_id, last_updated FROM p3_d26_hmm_opportunity_state LATEST ON last_updated PARTITION BY asset_id LIMIT 20"
```

## 07.2 AIM lifecycle & modifiers

| Component | File | Notes |
|-----------|------|-------|
| Lifecycle | `b1_aim_lifecycle.py` | States INSTALLED→ACTIVE path |
| Weekly Tier1 retrain | `_run_weekly` invokes `run_tier_retrain(asset, TIER_1_AIMS)` | `orchestrator.py` ~1315–1317 |
| Monthly Tier2/3 | `_run_monthly` uses `TIER_23_AIMS` | ~1346–1348 |
| Modifier math (online + offline shared) | `shared/aim_compute.py` | Consolidates per-AIM formulas |

## 07.3 DMA & decay loop

Offline per-trade handlers update DMA weights / BOCPD / CUSUM — see `b1_dma_update.py`, `b2_bocpd.py`, `b2_cusum.py`, escalation `b2_level_escalation.py`. Detailed spec deltas tracked in [09](09-KNOWN-ISSUES.md).

## 07.4 GUI touchpoints

Recent GUI memory items (#3219, #S423) reference AIM modal + Pseudotrader warmup surfaces — code lives under `captain-gui/src/` (see `PseudotraderPage.jsx`). Debugging flows still bottom out in QuestDB queries issued via GUI data server `captain-command/.../b2_gui_data_server.py`.

## 07.5 ORB / locked strategy

Opening-range multiples (`tp_multiple`, `sl_multiple`) are pulled from **`locked_strategy`** JSON referenced during Online B6 ([04.3](04-TRADE-LOGIC.md#043-tp--sl-multiples)).

Backtests / P2 regeneration live outside this repo (`most-production` per `CLAUDE.md`) — do **not** mutate frozen JSON under `config/` without explicit approval.

## 07.6 Parameters

| name | value | file | line | source-of-truth | rationale |
|------|-------|------|------|-----------------|----------|
| Tier1 weekly hook | `run_tier_retrain` | `captain-offline/.../orchestrator.py` | 1315–1317 | Offline scheduler | Weekly cadence |
| Tier23 monthly | `run_tier_retrain` | same | 1346–1348 | Offline scheduler | Monthly cadence |
