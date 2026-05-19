# NKD Pivot — Read-Only Scoping Audit

> **SUPERSEDED (in part) — 2026-05-19**
> Isaac's confirmed spec corrects two findings in this audit:
> - **§5.4 phase logic** ("linear taper, step gate"): Phase B is a **discrete `$1,000` flat step** over `[2000, 3000)` profit, NOT a continuous taper from `D_init → 450`.
> - **§5.6 jitter spec** ("J perturbs phase thresholds only — broker prices forbidden"): Jitter J **DOES** apply to broker dollar amounts. J shifts the SL buffer and the TP target at placement/trail time. Phase boundaries stay clean.
> - **§5.3 / §5.1 initial SL**: `D_init` is a **fixed `$1,025`** for all NKD trades, NOT derived from the OR-range × `sl_multiple` path used for other assets.
>
> See **[`day_2/PLAN.md`](../day_2/PLAN.md)** for the corrective commits (C14, C15, C16).
> This document is preserved as the original read-only audit baseline (HEAD `d6737178`).


**Author:** Cursor agent (Claude Opus 4.7) for Nomaan
**Mode:** Read-only. No code edits, DB writes, migrations, or installs were performed.
**Operator goal:** Pivot to NKD-focused APAC strategy with ratcheting trailing stop ($4450 TP), Isaac-jitter, and reallocated risk budget across NY/LON.

---

## 0. Pre-flight stamp

| Field | Value |
|-------|-------|
| Local HEAD | `d6737178bf4759f931535105614bbd9a25b434c1` |
| Branch | `main` |
| Audit baseline commit | `ef24edf632eba2462527505d28c5a75b133fb612` (doc-pack reference per `docs/captain-audit/00-INDEX.md` §00.1) |
| Commits ahead of baseline | 4 (per `git log ef24edf6..HEAD`) |
| Tip subject | `Revert "feat(online): optional emergency sizing and quality-gate env overrides"` |

### 0.1 Commit delta vs `ef24edf6`

```
d6737178 Revert "feat(online): optional emergency sizing and quality-gate env overrides"
d594ce9  feat(online): optional emergency sizing and quality-gate env overrides
5a1accd  docs+test: audits, tower runbook adjacents, canonical column + qexecute lint tests
e128f77  fix(questdb): quantize Decimals to column scale in qexecute
```

The `d594ce9 → d6737178` revert pair is a no-op in functional terms; the effective behavioural delta vs baseline is `e128f77` (Decimal→DECIMAL scale fix in `shared/questdb_client.qexecute`) plus the `5a1accd` doc+test commit. Neither touches B6/B7/B3 trade-execution surfaces. Audit-cache references in `docs2/full-captain-explain-may26/README.md` line 10 still pin `ef24edf6`.

### 0.2 Dirty / untracked files (per `git status`)

Modified (working-tree state at audit time):

```
M captain-command/captain_command/api.py
M captain-offline/captain_offline/blocks/bootstrap.py
M captain-offline/captain_offline/blocks/orchestrator.py
M captain-online/captain_online/main.py
M scripts/paper_trader.py
```

Untracked (no influence on this audit):

```
?? .audit-cache/
?? "Screenshot 2026-05-08 022014.png"
?? claude-mem/
?? docs2/full-captain-explain-may26/caches/captain-online-tower-logs-2026-05-11_to_2026-05-13.html
?? docs2/full-captain-explain-may26/caches/captain-online-tower-logs-raw.txt
?? docs2/logs-raw_html/
?? questdb-20260429.tar.gz
?? scripts/build_captain_online_log_viewer.py
```

**Action for operator before pivoting:** the five modified files should be committed or stashed before any NKD work lands — `captain-online/captain_online/main.py` (UserStream callbacks) and `captain-offline/.../bootstrap.py` in particular are on the hot path. None of them block this audit (I read from the working tree).

---

## 1. Doc-pack map (so anchors don't slip)

The user-supplied doc IDs map to `docs/captain-audit/*.md`:

| Cited ID | File | Section |
|---|---|---|
| 02.2 | `docs/captain-audit/02-QUESTDB-SCHEMA.md` | DECIMAL columns (CREATE TABLE bodies) |
| 04.3 | `docs/captain-audit/04-TRADE-LOGIC.md` | TP / SL multiples |
| 04.5 | `docs/captain-audit/04-TRADE-LOGIC.md` | Compliance gates |
| 04.6 | `docs/captain-audit/04-TRADE-LOGIC.md` | Bracket construction |
| 05.1 | `docs/captain-audit/05-PARITY-SKIP.md` | Multi-instance parity (content hash) |
| 05.2 | `docs/captain-audit/05-PARITY-SKIP.md` | Asset eligibility (NOT parity) |
| 08.2 | `docs/captain-audit/08-OPS-COMMANDS.md` | QuestDB validation queries |
| 09 (Ixx) | `docs/captain-audit/09-KNOWN-ISSUES.md` | Issue register |

---

## 2. Affected-file inventory per service

> "Reason" anchors against doc IDs where applicable. Line numbers are 1-indexed against HEAD `d6737178`.

### 2.1 `captain-online` (signal engine)

| File:line | Reason | Doc anchor |
|---|---|---|
| `captain-online/captain_online/blocks/b6_signal_output.py:281-300` | `_compute_sl` writes the dollar SL distance via `get_tick_size(asset_id)` + `math.ceil/floor`. NKD spec needs the **snapped `D_init`** persisted at entry. Existing direction-of-rounding is INWARD (`ceil` for long, `floor` for short) — opposite of the user's OUTWARD-rounding spec. Either a NEW asymmetric rounder lives next to `_compute_sl`, or `_compute_sl` itself gets an NKD branch. | 04.3 |
| `captain-online/captain_online/blocks/b6_signal_output.py:259-278` | Same tick path for `_compute_tp`. For NKD the LIMIT TP at `+$4450` must round to the nearest tick AT OR BELOW $4450; the existing `floor`-for-long behaviour is already correct for the NKD long case. | 04.3 |
| `captain-online/captain_online/blocks/b6_signal_output.py:138-176` | Signal dict shape must gain NKD-specific fields (`d_init_dollars`, `tp_dollars=4450`, `is_nkd_trail=True`, `jitter_x`, `jitter_y`, `jitter_j`) — these will round-trip through Redis to Command and back via `captain:open_positions`. | 04.6 |
| `captain-online/captain_online/blocks/b6_signal_output.py:371-387` | `_apply_jitter` is the EXISTING per-batch time/size jitter applied by `_publish_signals`. **Separate mechanism** from the proposed Isaac per-trade `J = 20·X·Y` PnL-threshold jitter; do NOT extend this function — add Isaac jitter at trail-state init in B7. | 05.1 |
| `captain-online/captain_online/blocks/b7_position_monitor.py:184-324` | `monitor_positions` is the 10-second poll loop. NKD trail-state evaluation (Phase A/B/C selection, ratchet, `modify_order` dispatch) lands here OR in a dedicated `b7b_nkd_trail.py` block that B7 invokes. | 04.6 |
| `captain-online/captain_online/blocks/b7_position_monitor.py:166` | `POLL_INTERVAL_SECONDS = 10`. **HAZARD:** at NKD's $5/pt × 5-pt tick = $25/tick, a $500 ratchet step is 20 ticks. If price moves >20 ticks in <10s on a thin Tokyo open, multiple ratchet boundaries can be crossed in one poll. Trail loop must compute `phase`+`buffer` STATELESSLY from current PnL each poll, not "step by step". See §5.4. | — |
| `captain-online/captain_online/blocks/b7_position_monitor.py:236-249` | Live PnL formula `(current_price - entry_price) * direction * contracts * pv` matches operator spec `pnl_$ = (mark - avg_entry) * size * point_value * direction_sign` byte-for-byte. Reuse as-is. | — |
| `captain-online/captain_online/blocks/b7_position_monitor.py:310-322` | `TIME_EXIT` path. See §7.2 for required NKD exemption. | — |
| `captain-online/captain_online/blocks/orchestrator.py:1170-1226` | `_handle_taken_skipped` builds the position dict and persists it to Redis `captain:open_positions` via `dumps_decimal`. Must add trail-state fields here so they survive process restart (see §5.5). | 04.6 |
| `captain-online/captain_online/blocks/orchestrator.py:400-417` | Online publishes `SESSION_CLOSE` to `STREAM_COMMANDS` at end of each session. This is a META message (drives Offline HMM retrain at `captain-offline/.../orchestrator.py:735-764`) — it does NOT flatten positions. No NKD change needed here; document for clarity. | 07 |
| `captain-online/captain_online/main.py:155-232` | UserStream `_on_order_update` / `_on_position_update` — the path that **can** deliver real broker-side SL/TP order IDs and average fill price. Post-2026-05-06 envelope-unwrap fix (`shared/topstep_stream.py:63-94`) re-armed these callbacks. NKD trail loop should consume these events to capture the real `sl_order_id` (see §5.1, option R1). | 09-I06 |

### 2.2 `captain-command` (linking layer)

| File:line | Reason | Doc anchor |
|---|---|---|
| `captain-command/captain_command/blocks/b3_api_adapter.py:241-284` | Atomic bracket placement path. Returns `sl_order_id: "BRACKET"` and `tp_order_id: "BRACKET"` (lines 274-275) — **sentinel strings, NOT real broker order IDs**. #1 BLOCKING gap for the proposed `/api/Order/modify` trail strategy. See §5.1. | 04.6 |
| `captain-command/captain_command/blocks/b3_api_adapter.py:194-224` | Compliance gate is invoked at `send_signal` entry (lines 211 + 220). There is NO equivalent wrap around `modify_order` calls. See §8. | 04.5 |
| `captain-command/captain_command/blocks/b3_api_adapter.py:326-432` | Fallback non-OCO path captures real `sl_order_id` (line 357) and `tp_order_id` (line 432) from `place_stop_order` / `place_limit_order` responses. This is the model for bracket order-ID capture (option R3 in §5.1). | 04.6 |
| `captain-command/captain_command/blocks/orchestrator.py:586-700` | `_auto_execute_signal` — receives B6 signal, calls adapter, forwards `entry_order_id` / `sl_order_id` / `tp_order_id` to Online. Trail orchestration entry point: must recognise NKD signals and trigger the bracket-order-ID capture (see §5.1). | 04.7 |
| `captain-command/captain_command/blocks/orchestrator.py:438-580` | `_handle_signal` + `_check_parity_skip` — the content-hash parity flow per doc 05.1. **Untouched by NKD pivot** (jitter is a separate, in-flight mechanism). | 05.1 |
| `captain-command/captain_command/blocks/b12_compliance_gate.py:180-214` | `compliance_check(signal, account_id)` reads `signal.size` vs `tsm.max_contracts` and `instrument_permitted`. Does not currently see modify operations. | 04.5 |
| `captain-command/captain_command/blocks/b2_gui_data_server.py:413-468` | `_get_open_positions_from_redis` — projects the position dict from `captain:open_positions` to the GUI. Must extend output schema for the Trade panel to render current phase / buffer / stop. | 07 |
| `captain-command/captain_command/blocks/b8_reconciliation.py:45-90` | 19:00 EST reconciliation. NO position-flatten action. NKD-safe by default — no change required, but flagged for completeness. | 06 |

### 2.3 `captain-offline` (strategic brain)

| File:line | Reason | Doc anchor |
|---|---|---|
| `captain-offline/captain_offline/blocks/orchestrator.py:735-764` | `_handle_session_close` is the receiver of the SESSION_CLOSE command — it dispatches HMM retraining via `_run_aim16_hmm_training`. **Does NOT close positions.** No NKD exemption needed; confirmed by direct read. | 07 |
| `captain-offline/captain_offline/blocks/orchestrator.py:622-650` | Command-dispatch loop. No code path flattens positions on session boundaries. | 06 |

### 2.4 `shared/` (cross-process)

| File:line | Reason | Doc anchor |
|---|---|---|
| `shared/topstep_client.py:342-382` | `place_bracket_order` returns `{orderId: <entry>, success, errorCode}` from `place_order`. **Does NOT surface SL/TP bracket order IDs.** This is the broker-side reality that forces the §5.1 capture strategy. | 04.6 |
| `shared/topstep_client.py:384-406` | `modify_order(account_id, order_id, size?, limit_price?, stop_price?, trail_price?)` — **already exists**, POSTs `/api/Order/modify`. Matches the verified ProjectX API context in the prompt. Reusable as-is. | 04.6 |
| `shared/topstep_client.py:54-66` | `OrderType.STOP = 4` and `OrderType.LIMIT = 1` — confirmed against verified API context. The proposed "type=4 STOP bracket on entry" matches the existing `place_bracket_order` line 380 (`type: OrderType.STOP`). | 04.6 |
| `shared/contract_resolver.py:99-105` | `get_tick_size(asset_id)` is the single tick-source for B6/B3. Returns `5.0` for NKD per `config/contract_ids.json:51`. **No asymmetric rounding helper exists** — needs scoping (see §5.3). | 04.3 |
| `shared/topstep_stream.py:466-498` | `MarketStream._handle_quote` → `quote_cache.update(contract_id, data)`. B7 reads `quote_cache.get(contract_id)["lastPrice"]` via `b7_position_monitor._get_live_price`. This is the tick subscription path for client-side PnL. | — |
| `shared/topstep_stream.py:178-179 + 410-444` | Rapid-failure circuit breaker — `_RAPID_THRESHOLD_S=10`, `_MAX_RAPID_FAILURES=5`, `_MAX_RECONNECT_BACKOFF_S=60`. A 22-hour APAC NKD position spans NY/LON market-data subscription churn; see §6.3. | — |
| `shared/sod_session_budget.py:84-128` | `session_budget_shares(hmm_state)` returns `{NY, LON, APAC}` Decimals summing to 1. Cold-start = 1/3 each; blended (`20 ≤ n_obs < 60`) = 50/50; full (`n_obs ≥ 60`) = pure HMM, floored at 0.05. **This is the LEVER for §4 reallocation.** | 06 |
| `shared/canonical_schemas.py:383-397` | `D23_CIRCUIT_BREAKER_INTRADAY` DDL — keyed by `(account_id, session_id)`. NOT per-position; not the right place for trail-state. See §3. | 02.2 |
| `shared/canonical_schemas.py:1027-1054` | M043-M047 — the most recent per-session budget migrations. Next available migration ID is `M048`. | 02.3 |

### 2.5 `captain-gui` (read-only consumer)

| File:line | Reason | Doc anchor |
|---|---|---|
| `captain-gui/src/components/trading/*` | Not opened in this audit. Will need a new NKD-trail panel column to render `current_phase`, `current_buffer_dollars`, `current_stop_price`, `pnl`, `jitter_j` (read from extended `captain:open_positions` payload). | — |
| `captain-gui/src/constants/blockRegistry.js` | If a new `b7b_nkd_trail` block is added (§5.5 option), register it here. Pre-existing registry drift is flagged as issue 09-I05. | 09-I05 |

---

## 3. QuestDB schema impact

### 3.1 Where the trail-state should live — **RECOMMEND: new table `p3_d34_nkd_trail_state`**

Three locations were considered:

| Option | Verdict | Reasoning |
|---|---|---|
| Extend `p3_d23_circuit_breaker_intraday` columns | **REJECT** | D23 keyed by `(account_id, session_id)` per `shared/canonical_schemas.py:383-397` and DEDUP UPSERT KEYS at M047 (`shared/canonical_schemas.py:1051-1053`). Trail-state is per-position (signal_id) — wrong cardinality. Would also dilute D23's CB semantics referenced by B5C and B7's `_update_capital_and_cb` (`b7_position_monitor.py:574-712`). |
| Reuse Redis hash `captain:open_positions` only | **PARTIAL** | The Redis hash IS already the live source of truth (`captain-online/.../orchestrator.py:1221`). MUST be extended for hot-path reads. But no audit trail of trail-state transitions; on broker reconciliation the hash gets re-derived from broker truth and any in-memory phase state would be lost. Recommend mirror-only. |
| New table `p3_d34_nkd_trail_state` | **PRIMARY** | Clean separation; QuestDB-native append-only audit log; survives restart; queryable for post-mortem of any 22-hour trade. D31-D33 are taken (`shared/canonical_schemas.py:657-694`: `p3_d31_implied_vol`, `p3_d32_options_skew`, `p3_d33_opening_volatility`). |

Recommended DDL skeleton (final shape Isaac-approved, NOT yet written by this audit):

```sql
CREATE TABLE IF NOT EXISTS p3_d34_nkd_trail_state (
    signal_id          STRING,
    account_id         SYMBOL,
    asset              SYMBOL,                 -- always 'NKD' but kept for portability
    contract_id        STRING,
    entry_order_id     STRING,
    sl_order_id        LONG,                   -- captured real broker ID, NOT 'BRACKET'
    tp_order_id        LONG,                   -- captured real broker ID
    direction          INT,                    -- +/-1
    contracts          INT,
    entry_price        DECIMAL(14, 6),
    snapped_d_init     DECIMAL(18, 2),         -- locked at entry; dollars
    tp_dollars         DECIMAL(18, 2),         -- 4450, locked
    jitter_x           DECIMAL(10, 8),         -- once per trade
    jitter_y           INT,                    -- +/-1
    jitter_j           DECIMAL(18, 8),         -- 20 * X * Y, dollars; signed
    phase              SYMBOL,                 -- 'A' | 'B' | 'C'
    current_buffer     DECIMAL(18, 2),         -- live $ buffer
    current_stop_price DECIMAL(14, 6),         -- last stopPrice sent to broker
    current_pnl        DECIMAL(18, 2),
    modify_seq         LONG,                   -- monotonic counter for /Order/modify calls
    last_modify_status STRING,                 -- 'OK' | 'REJECTED' | 'TIMEOUT'
    last_modify_error  STRING,
    last_updated       TIMESTAMP
) TIMESTAMP(last_updated) PARTITION BY DAY WAL
DEDUP UPSERT KEYS(last_updated, signal_id, modify_seq);
```

Notes:
- **DECIMAL precision per doc 02.2:** money fields use `DECIMAL(18, 2)` matching D08/D16/D23; prices use `DECIMAL(14, 6)` matching D03/D30. `jitter_j` uses `DECIMAL(18, 8)` to retain `20·X·Y` precision when `X ~ uniform(0.01, 1.00)`.
- **Degenerate case (`D_init ≤ 450`):** `phase` stays at `A` and `current_buffer` stays at `D_init` until `pnl ≥ 4450`. DDL handles this with no NULL requirement.
- `modify_seq` + `signal_id` DEDUP key gives one row per `/Order/modify` attempt — the audit trail.
- **TIMESTAMP convention:** `last_updated` matches every other table in `canonical_schemas.py` (e.g. D08:212-217, D16:300-306, D23:393-394).

### 3.2 Migration sequence

Next migration ID after `M047_d23_dedup_include_session_id` (`shared/canonical_schemas.py:1052-1053`) is **`M048`**. The pivot needs:

| ID | Purpose |
|---|---|
| `M048_create_d34_nkd_trail_state` | Create the new table. |
| (none required) | No ALTER on existing tables for the trail itself. |

### 3.3 `COLUMN_TYPES` delta

`shared/canonical_schemas.py:1064-` parses CREATE TABLE bodies via `_COLUMN_LINE_RE` (line 1080-1086) and migrations via `_ALTER_TYPE_RE` / `_ADD_COLUMN_RE`. Adding `D34_NKD_TRAIL_STATE` to `CANONICAL_DDLS` is sufficient — `COLUMN_TYPES` auto-derives from the constant. No manual delta to maintain. The existing `tests/test_canonical_column_types.py` regression covers it.

### 3.4 Doc-09 known-issue applicability

| Issue | Applicable? | Action |
|---|---|---|
| **I02** (D04 partial-row INSERT breaks `LATEST ON` fusion) | Yes — design D34 writes as full-row UPSERT (every modify writes the complete row), never partial. DEDUP key `(last_updated, signal_id, modify_seq)` is sound. |
| **I03** (missing version snapshots on D01/D02 writes) | Yes — trail-state IS an event log, not versioned state. Each row IS a snapshot. No snapshot-before-update path required. Document this explicitly so a future audit doesn't flag the absence. |
| **I06** (Redis channel naming drift) | Indirect — no new Redis channels are needed; reuse `STREAM_TRADE_OUTCOMES` (`shared/redis_client.py:78`) and `CH_ALERTS` for failure paths. |
| **I08** (D21/D33 writer mismatch flags) | None — D33 STRING-vs-TIMESTAMP issue is unrelated; D34 uses TIMESTAMP. |

---

## 4. Risk-budget reallocation (non-NKD reduction)

### 4.1 What the system already supports

`captain-online/captain_online/blocks/b4_kelly_sizing.py:416-457` (`_compute_topstep_daily_cap`) reads `computed_sod.session.{NY,LON,APAC}.E_daily_exposure` via `shared.sod_session_budget.get_session_e_exposure` (`shared/sod_session_budget.py:163-188`). The per-session SOD shares come from `session_budget_shares(hmm_state)` (`shared/sod_session_budget.py:84-128`) which:

- Cold-start (`n_observations < 20`): each session = 1/3
- Blended (`20 ≤ n < 60`): 50% equal + 50% HMM weights
- Full (`n ≥ 60`): pure HMM weights, floored at 0.05, renormalised

These shares feed both **L_halt** (B5C Layer 1 halt) and **E_daily_exposure** (B4 Topstep daily cap).

### 4.2 Minimum-friction interventions (no signal-logic change)

> All three are CONFIG / DATA changes — no rebuild required beyond the standard `cp -r config <svc>/_config` sync (`.cursor/rules/captain-deploy-and-tower-discipline.mdc` §2026-05-06 stale-config entry).

#### Intervention A — HMM weight override in `p3_d26_hmm_opportunity_state` (RECOMMENDED)

**File:** `p3_d26_hmm_opportunity_state` (live UPSERT, no static config) — table exists at `shared/canonical_schemas.py:351`.

**What:** Operator-driven INSERT that sets `opportunity_weights = {"NY": 0.10, "LON": 0.10, "APAC": 0.80}` with `cold_start=false` and `n_observations >= 60` (to escape blended mode). Floor at 0.05 per `shared/sod_session_budget.py:63`. Result of `session_budget_shares` becomes `~10/10/80` (no renormalisation needed because the floor isn't tripped).

**Where this lands downstream automatically:**

| Consumer | File:line | What it gets |
|---|---|---|
| B4 sizing — per-session contract cap | `b4_kelly_sizing.py:226-238` | NY/LON `topstep_daily_cap` shrinks proportionally; APAC expands. |
| B5C Layer 1 — preemptive halt | reads `effective_l_halt` from D23 SOD-locked column populated by Command B8 | NY/LON `effective_l_halt` shrinks; APAC expands. |
| Command B8 SOD allocator | `b8_reconciliation.py:_compute_sod_topstep_params` | Recomputes per-session `L_halt` and `E_daily_exposure` against the new shares at next 19:00 ET cycle. |

**Pros:** zero code change. Recoverable by re-running B8 SOD. The conserved-total-budget property in `compute_session_carryover` (`shared/sod_session_budget.py:214-296`) holds.
**Cons:** abuses the HMM semantic. Recommend marking the source row source as a manual override; restore once empirical NKD data matures.

#### Intervention B — Lower non-NKD `sl_multiple` to floor minimums

**Per-asset SL multiple lives in:** `p3_d00_asset_universe.locked_strategy` JSON (per doc 04.3 + `b6_signal_output.py:283`). The `sl_multiple` key is what `_compute_sl` reads; default `0.35`.

**Floor mechanism:** there is NO automatic SL floor in `_compute_sl`. The "current floor minimums" referenced by the operator are the per-asset locked-strategy values fed in from P2 (`scripts/load_p2_multi_asset.py`, `scripts/bootstrap_production.py`). The minimum-friction lever is to lower `sl_multiple` per asset to a smaller value (e.g. `0.20` or `0.15`).

**Caveat — `shared/sizing_helpers.resolve_sizing_sl`:**

`captain-online/.../b4_kelly_sizing.py:178` calls `resolve_sizing_sl(u, strategy, point_value)` which is the unified `rho_j` source used in BOTH B4 sizing AND B5C circuit-breaker preemptive halt. Per `docs2/pre-market-22-04-deadline/PRE_MARKET_CHECKLIST.md` lines 50-51 this falls back to `or_range_first_m_min` from D29 when `or_range` is missing — i.e. the SL distance is not solely driven by `sl_multiple`. Operator should verify (replay) that reducing `sl_multiple` on NY/LON assets actually narrows the dollar SL before relying on this lever.

**Update mechanism (no code change, ops-side):**

```bash
# Per doc 08.2 — READ only; the UPSERT is a follow-on the operator runs:
curl -s -G "http://127.0.0.1:9000/exec" \
  --data-urlencode "query=SELECT asset_id, locked_strategy FROM p3_d00_asset_universe \
    LATEST ON last_updated PARTITION BY asset_id"
```

Captain reads D00 `LATEST ON last_updated` — a fresh insert is picked up at next session open.

#### Intervention C — Per-session E override via D08 `topstep_state.computed_sod.session.<KEY>.E_daily_exposure`

**File:** runtime UPSERT into `p3_d08_tsm_state.topstep_state` JSON.

`shared.sod_session_budget.get_session_e_exposure` (`shared/sod_session_budget.py:163-188`) **prefers** the nested per-session entry over the legacy flat scalar. Writing `{"NY": {"E_daily_exposure": 150.0}, "LON": {"E_daily_exposure": 150.0}, "APAC": {"E_daily_exposure": 1200.0}}` directly forces B4's NY/LON contract caps tiny.

**Pros:** surgical, no HMM-semantic abuse.
**Cons:** B8's nightly reconciliation will rewrite this row from broker truth (`b8_reconciliation.py:97-169`). The override must be re-applied each day until the operator commits to a code-side change, OR the operator pauses B8's `_compute_sod_topstep_params` for the rollout window.

### 4.3 Recommendation

Intervention **A** (HMM weight override) is the cleanest single-lever change. Apply Intervention **B** in tandem to also shrink dollar-SL exposure per non-NKD trade. Defer Intervention **C** unless A+B is insufficient.

**Files touched:** none. Data writes only. No build/restart required (B4 reads `LATEST ON last_updated` from D00 and from D26 each session open).

---

## 5. Trailing-SL execution

### 5.1 BLOCKING — bracket capture does NOT preserve `stopOrderId`

**Code anchor:** `captain-command/captain_command/blocks/b3_api_adapter.py:241-284` (atomic bracket path).

```272:275:captain-command/captain_command/blocks/b3_api_adapter.py
                        "entry_order_id": entry_oid,
                        "fill_price": fill_price,
                        "sl_order_id": "BRACKET",
                        "tp_order_id": "BRACKET",
```

The atomic `_client.place_bracket_order(account_id, contract_id, side, size, sl_ticks, tp_ticks)` only returns the ENTRY `orderId`. The exchange creates the SL/TP children, but their IDs are never surfaced. Today they're stored as the literal string `"BRACKET"` and propagated through orchestrator (`captain-command/.../orchestrator.py:696-697`) and into the position dict at `captain-online/.../orchestrator.py:1202-1203`.

**Impact:** `/api/Order/modify` requires `orderId` per the verified API context. Without the real SL `stopOrderId`, the proposed trail mechanism cannot proceed.

**Resolution options (operator picks one):**

| Option | Surface |
|---|---|
| **R1 — UserStream capture (RECOMMENDED long-term).** Listen on `GatewayUserOrder` (`shared/topstep_stream.py:_async_handle_order` → `_handle_order` → `captain-online/.../main.py:_on_order_update`). When an order arrives with `accountId=our_account` and the side opposite to entry within ~3s after entry placement, persist its `id` as the bracket child ID. Disambiguate by `type` (4=STOP→`sl_order_id`, 1=LIMIT→`tp_order_id`). | `shared/topstep_stream.py`, `captain-online/.../main.py`, `captain-online/.../orchestrator.py` |
| **R2 — REST poll capture.** After `place_bracket_order` success, call `_client.search_open_orders(account_id)` (already exists at `shared/topstep_client.py:430-433`) and find the two children. | `captain-command/.../b3_api_adapter.py` post-bracket block |
| **R3 — Switch NKD to the existing fallback path (FASTEST to ship).** B3's fallback (`b3_api_adapter.py:326-432`) places SEPARATE entry+SL+TP and DOES capture real IDs (line 357 for SL, line 432 for TP). Trade-off: SL/TP are NOT OCO — when one fills, the other must be cancelled. `b7_position_monitor.py:_cancel_orphan_bracket_leg` (line 859-) already handles this. Re-using it for NKD = lowest-risk shipping path. | Branch on `asset == "NKD"` inside `b3_api_adapter.send_signal` (line 194-470) |

R1 is the right long-term answer (defence-in-depth for every asset). R3 is the right "ship in 2-3 days" answer because every piece already exists.

### 5.2 `/api/Order/modify` is already wired

`shared/topstep_client.py:384-406` — `modify_order(account_id, order_id, size, limit_price, stop_price, trail_price)`. Returns `{success, errorCode, errorMessage}` per spec. No new client method needed; reuse as-is for ratchet `stopPrice` updates.

### 5.3 Tick rounding — NEW asymmetric rounder REQUIRED

**Existing rounder:** `b6_signal_output._compute_sl` lines 293-299:

```293:299:captain-online/captain_online/blocks/b6_signal_output.py
    if sl is not None:
        tick = get_tick_size(asset_id)
        ndigits = max(0, len(str(tick).rstrip('0').split('.')[-1])) if '.' in str(tick) else 0
        if direction == 1:
            sl = round(math.ceil(sl / tick) * tick, ndigits)
        elif direction == -1:
            sl = round(math.floor(sl / tick) * tick, ndigits)
```

This rounds INWARD (long: `ceil` → higher stop price = closer to entry, narrower; short: `floor` → lower stop price = closer to entry, narrower). The operator's NKD spec rounds OUTWARD:

```
Long:  stop_price = floor(raw / 5) * 5    # → lower price, further below entry, WIDER
Short: stop_price = ceil(raw  / 5) * 5    # → higher price, further above entry, WIDER
```

**Directions are opposite.** Existing helper is NOT reusable for NKD ratchet trail. Two scoping options:

- New function `_tick_snap_stop_outward(price, tick, direction)` in `shared/contract_resolver.py` (next to `get_tick_size`), called from the new B7 trail block; OR
- An NKD branch inside `_compute_sl` that swaps the rounding direction (less invasive but mixes intent).

Prefer the new function — cleaner unit-test surface.

The `_compute_tp` helper (b6 lines 271-278) rounds TP INWARD too (long: `floor` → keep TP at-or-below raw; short: `ceil` → keep TP at-or-above raw). For the NKD `+$4450` LONG TP this is correct: the LIMIT lands on (or just below) the dollar ceiling. **Existing `_compute_tp` is reusable for NKD long TP. `_compute_sl` is not.**

### 5.4 Ratchet enforcement & phase logic (HAZARDS)

| Hazard | Resolution |
|---|---|
| **H1 — Crossing multiple $500 boundaries in one poll** (10s gap; fast move). | On each poll, compute `phase` and `buffer` deterministically from current PnL relative to thresholds — do NOT step boundary-by-boundary. The math is stateless: `phase = A if pnl < max(D_init, 1500+J); B if pnl < 4000+J; C if pnl < 4450; TP_HIT if >= 4450`. Then `stop_price = mark - (buffer × sign)` per phase formula. Only issue `modify_order` if the new `stop_price` differs from `current_stop_price` AND is strictly more conservative. |
| **H2 — `modify_order` returns `success=false`** (mid-tick rejection, broker latency, race with TP fill). | Capture `errorCode` + `errorMessage`. Log + alert via `CH_ALERTS` (CRITICAL). Do NOT retry mechanically — the next poll re-derives state from live PnL and tries again with refreshed price. Persist failure to `p3_d34.last_modify_status / last_modify_error`. |
| **H3 — Position externally closed** (manual cancel via UserStream `_on_order_update` status=`CANCELLED`, or `_on_position_update` size=0). | B7 already drops resolved positions from `open_positions` via `resolve_position`. Trail loop must check "still in `open_positions`" each iteration. |
| **H4 — Phase boundary respect for ratchet-only** | User spec is explicit: "SL never retreats". Implementation: hold `current_stop_price` in trail-state and only call `modify_order` when the new computed stop is strictly farther from entry than the current. For LONG: `new_stop > current_stop`. For SHORT: `new_stop < current_stop`. Degenerate case (`D_init ≤ 450`) means phase B/C are no-ops — stop stays at `entry - D_init` for long until TP. |
| **H5 — Latency overshoot** (PnL ≥ 4450 but TP didn't fill yet) | Treat $4450 LIMIT as the broker's hard ceiling; do not issue further modifies once PnL ≥ 4450. The exchange will fill at the LIMIT. Set a max-wait timer (e.g. 60s after PnL first hit 4450) — if TP doesn't fill, alert CRITICAL but do NOT auto-close (operator override). |
| **H6 — Concurrent compliance gate / parity skip race** | Parity-skip (`captain-command/.../orchestrator.py:508-580`, doc 05.1) runs at signal RECEIPT, not modify time. Once a position is OPEN, parity is irrelevant for the trail loop. Compliance gate (doc 04.5) is similarly placement-only. No race introduced — confirm via code reading, no race exists today. |
| **H7 — Redis hash race between B7 reading and B7 writing** | `captain:open_positions` is HSET-style (per-signal_id key). Concurrent writers are an issue only if multiple monitors fire for the same signal. Today B7 holds `_position_lock` (`captain-online/.../orchestrator.py:1205-1212`). Reuse — the trail iteration belongs inside that lock or the same poll iteration where `monitor_positions` runs. |

### 5.5 Trail loop placement

Two clean options:

| Option | Where | Trade-off |
|---|---|---|
| **In B7 directly** | Add NKD-branch inside `b7_position_monitor.monitor_positions` between lines 273 and 290 | Lowest LoC. Mixes concerns. |
| **New block `b7b_nkd_trail.py`** | Called by online orchestrator after `monitor_positions` returns | Cleaner. New file → easier to test in isolation. Per `01-ARCHITECTURE-OVERVIEW.md` §01.1, Online has 14 blocks — `captain-gui/src/constants/blockRegistry.js` needs an addition. |

Recommend the new block. The trail loop fires once per 10s poll, reads `captain:open_positions` for any signal with `is_nkd_trail=True`, computes phase/buffer, and issues `modify_order` via the existing `_client` singleton.

### 5.6 Per-trade Isaac jitter `J` — implementation contract

| Requirement | Where to implement |
|---|---|
| Read `INSTANCE_PARITY` once at trail-state init; if not `"1"`, set `X=0, Y=0, J=0` (Nomaan tower behaviour) | Trail-init in the new B7 block |
| Sample `X ~ uniform(0.01, 1.00)` and `Y ~ choice(-1, +1)` ONCE per trade (at first poll where the NKD position appears) | `random` module is already imported in `b6_signal_output.py:24`; mirror in trail block |
| Persist `X, Y, J` on first write to `p3_d34` and to `captain:open_positions` | §3.1 schema covers this |
| Apply `J` ONLY to phase B threshold (`1500 + J`) and phase C threshold (`4000 + J`); never to TP $4450, ratchet step $500, `D_init`, phase C buffer $450 | Trail-block phase decision tree |
| Re-load same `J` from persisted state on every subsequent poll for the same trade | Hot path read from Redis hash |
| `J` modifies PnL THRESHOLDS only — never broker prices. The non-tick-aligned nature of `J` (e.g. `+$3.47`) creates no tick-rejection risk because `J` never reaches the broker. | Comment-grade — assert in code |

The user-spec separation from doc 05.1 parity is preserved:
- **Parity skip** (`captain-command/.../parity.py:21-66`, called from `orchestrator._check_parity_skip:508-580`): operates on whole BATCHES BEFORE placement; tower decides take/skip. Per-asset, per-session, per-day batch.
- **Isaac jitter `J`**: operates on a single OPEN position's INTERNAL thresholds; never touches broker payloads. Per-trade, independent of parity-skip outcome.

These are orthogonal. Confirmed by reading both surfaces: no code-path overlap.

---

## 6. PnL data flow

### 6.1 Where PnL is computed today

| Stage | File:line | Note |
|---|---|---|
| Live (open position) | `captain-online/captain_online/blocks/b7_position_monitor.py:236-249` | Decimal arithmetic; formula `(current_price - entry_price) * direction * contracts * pv` matches user spec |
| `pv` source | `b7_position_monitor.py:_resolve_point_value:83-141` | Reads `p3_d00_asset_universe.point_value`; cached per-process. Raises on miss — no 50.0 default (Bug A protection) |
| On exit (closed) | `b7_position_monitor.py:_write_trade_outcome:516-571` | Writes `gross_pnl`, `commission`, `pnl`, `slippage` to `p3_d03_trade_outcome_log` (doc 02.2 DECIMAL columns confirmed) |
| Broker exit-fill resolution | `b7_position_monitor.py:_resolve_exchange_exit_price:1004-1121` | For bracket orders, queries `/Trade/search` for the actual fill price (since polled `lastPrice` can drift) |

For the trail loop, REUSE the b7 formula. NKD `point_value = 5.0` per `config/contract_ids.json:51` and `scripts/seed_all_assets.py:71`.

### 6.2 Tick subscription path

`shared/topstep_stream.py:466-498` (`MarketStream._handle_quote`) populates a thread-safe `quote_cache` (lines 110-150) keyed by `contract_id`. B7's `_get_live_price` reads `quote_cache.get(contract_id)["lastPrice"]` with REST fallback to `/History/retrieveBars` 1-min bars (line 802-808).

For NKD specifically, the MarketStream is started by `captain-online/captain_online/main.py` (preloads contracts via `preload_contracts()` in `shared/contract_resolver.py:65`). NKD's `CON.F.US.NKD.M26` is in `config/contract_ids.json:48`.

**Hazard for 22-hour NKD spanning sessions:** the MarketStream may be subscribed only to today's active session's assets. If at session rollover the orchestrator rebuilds the active asset set (`captain-online/.../orchestrator.py:_run_session` → `_load_active_assets` per doc 03.1 L1), NKD's subscription could be dropped at NY open (NKD is not in the NY active set per `config/session_registry.json:53`).

**Read-only verification action the operator can run (NOT executed by this audit):**

```bash
dco logs captain-online | grep -i "Subscribed to CON.F.US.NKD"
```

If the log shows NKD being UN-subscribed at session rollover, the trail loop loses live price → falls back to REST (1-minute bar lag — too slow for $500-boundary ratchet). Fix: hold NKD's contract_id in the MarketStream subscription set for as long as `captain:open_positions` contains an NKD entry. `shared/topstep_stream.py:318-334` already exposes `add_contract` for runtime additions; the symmetric `remove_contract` is what to guard.

### 6.3 Session-boundary survival — Tower B MGC precedent

The exact "Tower B MGC dropout" memory referenced by the operator isn't surfaced verbatim in the in-repo docs — the closest evidence is `docs2/context/tracking_context.md:487` showing both towers sized MGC on LON, and the 2026-04-15 NKD incident (`docs2/major-issues/15-04-26/2026-04-15-NKD-account-failure.md`, issue 2A) which documents position-enrichment loss when UserStream events fail. The 2026-05-06 root-cause audit (`docs2/quick-fixes/NY-Open-May_5th_error_logs/2026-05-06_issue4_userstream_none_root_cause_audit.md`) fixes the envelope unwrap that re-armed position-update enrichment.

**Concrete risk for NKD trail loop:** if MarketStream rapid-failure CB trips (`shared/topstep_stream.py:_RAPID_THRESHOLD_S=10s`, `_MAX_RAPID_FAILURES=5` at lines 178-179) during the 22-hour hold, `quote_cache` goes stale, `_get_live_price` falls back to REST 1-min bars, trail loop computes PnL on lagged price. Mitigation: the new trail block should degrade gracefully — if `quote_cache` is older than e.g. 30s, SKIP this poll's modify, emit a CRITICAL alert, and let the next poll re-evaluate.

---

## 7. Session-close auto-flatten audit

### 7.1 Inventory of every code path that closes positions

| Path | File:line | When fires | NKD exemption needed? |
|---|---|---|---|
| **B7 TIME_EXIT** | `captain-online/captain_online/blocks/b7_position_monitor.py:310-322` | When `not tsm.get("overnight_allowed", True)` AND wall-clock ≥ `trading_hours.close_time - 5min` | YES — see §7.2 |
| **B3 SL-failure emergency flatten** | `captain-command/captain_command/blocks/b3_api_adapter.py:387-423` | When entry succeeds but separate-path SL placement fails | NO — safety net; if it fires for NKD, the NKD position is unprotected and SHOULD flatten |
| **`SESSION_CLOSE` command publication (online → offline)** | `captain-online/captain_online/blocks/orchestrator.py:400-417` | End of each session loop | NO — meta-event (drives Offline HMM retrain at `captain-offline/.../orchestrator.py:735-764`); does NOT close positions |
| **Daily reconciliation** | `captain-command/captain_command/blocks/b8_reconciliation.py:45-90` | 19:00 EST | NO — balance reconciliation only; no order/position close action |
| **`scripts/paper_trader._close_position`** | `scripts/paper_trader.py:342-344` | Offline paper-trader simulation | N/A — does not run against live broker |
| **`captain-command/test_gui_order.py` emergency flatten** | `captain-command/test_gui_order.py:121` | One-off manual test script; not in service path | N/A |

### 7.2 The `TIME_EXIT` NKD exception

**Current code:**

```310:322:captain-online/captain_online/blocks/b7_position_monitor.py
        # Time exit — forced close for no-overnight accounts
        tsm = tsm_configs.get(pos.get("account"))
        if tsm and not tsm.get("overnight_allowed", True):
            trading_hours = tsm.get("trading_hours", "")
            close_time = _parse_close_time(trading_hours)
            if close_time:
                buffer_time = close_time - timedelta(minutes=5)
                if datetime.now(ZoneInfo("America/New_York")) >= buffer_time:
                    _notify(pos["user_id"], "CRITICAL",
                            f"TIME EXIT: {pos['asset']} closing — account does not allow overnight")
                    resolve_position(pos, "TIME_EXIT", float(current_price), tsm_configs)
                    resolved.append(pos)
                    continue
```

**Status today:** the active TSM `config/tsm/providers/topstep_150k_eval.json:22-30` has `overnight_allowed: false` AND uses a DICT for `trading_hours` (`{session_close: "16:10 EST", flat_by: "16:10 EST", risk_manager_flatten: "16:08 EST", ...}`). `_parse_close_time` (`b7_position_monitor.py:1150-1160`) expects a STRING `"09:30-16:00"` format with `.split("-")[1].split(":")`. When passed a dict, `.split` raises → `_parse_close_time` returns `None` → TIME_EXIT never fires.

So as of today this branch is effectively DEAD CODE. **However**, the NKD pivot must NOT rely on this latent bug. Recommended explicit exemption (sketch — operator-approved variant):

```python
# Sketch — DO NOT APPLY without operator review:
if tsm and not tsm.get("overnight_allowed", True):
    # NKD pivot 2026-05: NKD positions intentionally span session boundaries
    # (up to ~22h holds). Skip TIME_EXIT for NKD; rely on the trailing-stop
    # bracket for protection.
    if pos.get("asset") == "NKD":
        continue
    # ... rest of block unchanged
```

**Also** add the exception to the (presumably future) re-armed code path — if `_parse_close_time` is ever fixed to accept the dict format, the NKD exemption must already be in place.

### 7.3 Other implicit close paths verified

`captain-command/captain_command/blocks/b3_api_adapter.py:393` (`self._client.close_position`) — only invoked on SL-placement failure. NOT a session-boundary auto-flatten.

Scheduled tasks (per doc 06.1): `_run_daily` (after 16:00 ET), `_run_weekly`, `_run_monthly`, `_run_quarterly`, `_run_compaction` at `captain-offline/.../orchestrator.py:1247, 1300, 1329, 1375, 1429`. None close positions; all run learning / diagnostic jobs.

**Verdict:** the only Captain-side path that can flatten NKD on a session boundary is `b7.monitor_positions TIME_EXIT` line 320. Exempt it.

---

## 8. Compliance gate (doc 04.5)

### 8.1 Current scope

| Call site | File:line | What it gates |
|---|---|---|
| Global gate | `captain-command/captain_command/blocks/b3_api_adapter.py:211-217` | Short-circuits to `MANUAL_PENDING` if `execution_mode == "MANUAL"` |
| Per-signal | `b3_api_adapter.py:220-224` | Calls `compliance_check(order, account_id)` from `b12_compliance_gate.py:180-214` |

`compliance_check` enforces:
1. `signal.size <= tsm.max_contracts` (line 207-208)
2. `instrument_permitted(asset, tsm)` — asset in D00 active list AND (if fee_schedule has fees_by_instrument) asset in that map (`b12_compliance_gate.py:156-177`)

### 8.2 BLOCKING — modify is NOT gated

`shared/topstep_client.modify_order` (`shared/topstep_client.py:384-406`) has NO compliance wrapper. The trail loop will issue `/api/Order/modify` calls directly via `_client.modify_order(...)` — none of these go through B3's `send_signal` path.

**Scope a wrapper:** the trail block should call a new helper `compliance_modify_check(account_id, original_order_id, new_stop_price)` that re-validates:

- The account is still permitted to trade NKD (`instrument_permitted` unchanged)
- The modify operation respects `max_contracts` (size never increases here — it's a `stopPrice` change only — but the check is cheap)
- `execution_mode` is still `AUTO` (a global lockdown via `check_compliance_gate` should prevent further trail updates)

This is **NEW code** but mirrors `compliance_check` (~30 lines). Land it in `captain-command/captain_command/blocks/b12_compliance_gate.py`. The trail block imports and calls it before each `modify_order`.

**Decision lever:** the operator may accept the implicit assumption that an already-accepted bracket's children inherit the entry's compliance verdict (most brokers do not gate `/modify`). If so, no wrapper is needed; document the assumption explicitly in §5.5's trail block module docstring.

---

## 9. NKD contract specs — verification

### 9.1 Per `config/contract_ids.json:47-53`

```47:53:config/contract_ids.json
        "NKD": {
            "contract_id": "CON.F.US.NKD.M26",
            "name": "NKDM6",
            "description": "Nikkei 225 (Globex): June 2026",
            "tick_size": 5.0,
            "tick_value": 25.0
        },
```

### 9.2 Per `scripts/seed_all_assets.py:71` and `scripts/bootstrap_production.py:65`

```
NKD: point_value=5.0, tick_size=5.0, margin=7700.0, tz=Asia/Tokyo, sessions=APAC
```

But `scripts/load_p2_multi_asset.py:67` says `margin=11000` — and the operator prompt cites "margin ~$11k". **DISCREPANCY** between active bootstrap (`margin=7700`) and load_p2_multi_asset (`margin=11000`). See §12 question 1.

### 9.3 Locked strategy per `scripts/bootstrap_production.py:48`

```
NKD: m=6, k=6, OO=0.8533, regime_class=REGIME_NEUTRAL, complexity_tier=C1
```

Matches `CLAUDE.md` "Locked Strategies" table (NKD is `m=6, k=6`, NOT the `m=4, k=017` legacy default).

### 9.4 Tick size — units verification

`shared/contract_resolver.get_tick_size("NKD")` returns `5.0` (a float). It is **5 price points per tick**, NOT 5 dollars. Confirmed:

- `tick_value = 25.0` ($ per tick)
- `point_value = 5.0` ($ per point)
- `tick_value / point_value = 5.0` → 5 points per tick. ✓

Consumer audit:
- `b6_signal_output._compute_sl:294` uses `tick = get_tick_size(asset_id)` and snaps `sl / tick`. Treats the float as the price-point increment, not as dollars. Correct interpretation.
- `b3_api_adapter.send_signal:248-253` computes `sl_ticks = abs(entry - sl) / tick_size` (price difference in points / 5 points/tick) — correct.
- `tests/test_b3_api_adapter_sltp.py:381-390` (`test_bracket_nkd_tick_calculation`) confirms NKD: entry 38000, SL 37950 → `(38000-37950)/5 = 10 ticks`, TP 38100 → `(38100-38000)/5 = 20 ticks`. ✓

### 9.5 Operator-required confirmation query (doc 08.2 style; NOT executed by this audit)

```bash
# Read-only — operator can run to confirm what's actually in D00 today:
curl -s -G "http://127.0.0.1:9000/exec" \
  --data-urlencode "query=SELECT asset_id, point_value, tick_size, margin_per_contract, captain_status \
    FROM p3_d00_asset_universe \
    WHERE asset_id = 'NKD' \
    LATEST ON last_updated PARTITION BY asset_id"
```

Confirm `point_value = 5.0`, `tick_size = 5.0`, and decide which `margin_per_contract` is canonical (the `7700` from bootstrap or `11000` from `load_p2_multi_asset`).

---

## 10. Known-issue intersections (doc 09)

| Issue | File anchor | Applies to NKD pivot? | Action |
|---|---|---|---|
| **09-I01** AIM-16 HMM offline driver unwired | `captain-offline/.../b1_aim16_hmm.py`; weekly scheduler | INDIRECT — HMM weights drive `session_budget_shares` (§4.2 Intervention A). If HMM trainer isn't re-running, weights stay stale, but the operator override remains effective. | No action; document dependency on Intervention A. |
| **09-I02** D04 partial-row INSERT | `b2_bocpd.py`, `b2_cusum.py` | NO — D04 is BOCPD/CUSUM state, unrelated to trail. | None |
| **09-I03** Version snapshots missing on D01/D02 writes | Various D01/D02 writers | NO — D34 is an event log, not versioned state. | Document explicitly in D34 DDL comment. |
| **09-I06** Redis channel naming drift | `b7_position_monitor.py` docstring vs `STREAM_TRADE_OUTCOMES` | INDIRECT — any new alert from the trail loop uses `CH_ALERTS` (`shared/redis_client.py`). Match existing naming. | None |
| **09-I08** D21/D33 writer type mismatch | `shared/canonical_schemas.py:43-67` header | NO | None |
| **Candidate 09-I10 (NEW DRIFT)** | `b3_api_adapter.py:274-275` `sl_order_id="BRACKET"` sentinel | YES — this is the BLOCKING gap from §5.1. | Add as Candidate I10 in `docs/captain-audit/09-KNOWN-ISSUES.md`. |
| **Candidate 09-I11 (NEW DRIFT)** | `b7_position_monitor.py:1150-1160` `_parse_close_time` returns `None` on dict-typed `trading_hours` (silently) | YES — surfacing this means TIME_EXIT is currently DEAD CODE for the active TSM. NKD safety relies on this bug NOT being fixed without adding the exemption first. | Add as Candidate I11. |
| **Candidate 09-I12 (LOW)** | `config/contract_ids.json` `tick_size` units vs consumer expectations | LOW — confirmed correct by code-path audit; documenting for future-readers. | Optional. |

---

## 11. Test surface — existing + gaps

### 11.1 Existing harnesses relevant to NKD pivot

| Path | What it covers |
|---|---|
| `scripts/replay_full_pipeline.py:663` (`["NKD"]` for APAC session) | Full replay including APAC NKD path |
| `scripts/replay_session.py:53` (`NKD: APAC`) | Session replay |
| `tests/test_replay_engine_per_session.py:50,103,140` | Per-session L1/L2/L3 isolation with NKD specifically (`test_per_session_l1_isolated_lon_loss_does_not_block_apac_nkd`) — confirms NKD APAC is not budget-starved by NY/LON losses |
| `tests/test_b4_per_session_cap.py:41` (NKD: 6pt SL, $5/pt → $30/contract) | Per-session contract cap |
| `tests/test_b3_api_adapter_sltp.py:370-390` (`test_bracket_nkd_tick_calculation`) | NKD tick math at entry: SL 50pt = 10 ticks, TP 100pt = 20 ticks |
| `tests/test_b6_signal.py:114-127` | TP/SL helpers (LONG only) |
| `tests/test_parity_filter.py` | Parity skip mechanism (doc 05.1) — confirms NKD pivot does NOT touch this |
| `docs2/pre-market-22-04-deadline/PRE_MARKET_CHECKLIST.md` | Tower pre-market gate; reusable shape for the NKD pivot |

### 11.2 Test gap list (none of these exist today)

**Unit tests required for the trail block:**

| Test | Asserts |
|---|---|
| `test_nkd_phase_a_step_ratchet` | At `pnl < max(D_init, 1500+J)`: stop only updates when PnL crosses a `$500` boundary; `buffer == D_init` |
| `test_nkd_phase_b_linear_taper` | At `max(D_init, 1500+J) ≤ pnl < 4000+J`: `buffer = D_init - progress * (D_init - 450)`; updates on entry + every `$500` boundary |
| `test_nkd_phase_c_tight_trail` | At `4000+J ≤ pnl < 4450`: single update at C-entry; `buffer = 450` |
| `test_nkd_ratchet_never_retreats` | Across price oscillations: `current_stop_price` is monotonic in the safe direction |
| `test_nkd_degenerate_d_init_le_450` | When `D_init ≤ 450`: phases B/C collapse; stop stays at `mark - D_init` (with ratchet) until TP |
| `test_isaac_jitter_nomaan_tower_zero` | `INSTANCE_PARITY != "1"` → `X=0, Y=0, J=0` |
| `test_isaac_jitter_isaac_tower_sampled_once` | `INSTANCE_PARITY == "1"` → `X ∈ [0.01, 1.00]`, `Y ∈ {-1, 1}`, `J = 20 * X * Y`; same J across multiple polls of the same trade |
| `test_isaac_jitter_does_not_touch_broker_prices` | `J` modifies threshold checks only; `stop_price` sent to broker is grid-aligned per §5.3 |
| `test_tick_snap_outward_long` | `floor(raw / 5) * 5` for long |
| `test_tick_snap_outward_short` | `ceil(raw / 5) * 5` for short |
| `test_nkd_tp_at_4450_never_exceeded` | TP LIMIT is always at-or-below $4450 in dollar terms (regardless of jitter) |

**Integration tests:**

| Test | Asserts |
|---|---|
| `test_nkd_session_span` | NKD position opens in APAC, survives session rollover (mock MarketStream re-subscription), exits during next-day APAC |
| `test_nkd_modify_retries_and_alerts` | `modify_order` returns `success=false` → alert CRITICAL, next poll re-attempts with refreshed price |
| `test_nkd_fast_crossing_multiple_boundaries` | One poll crosses `$500 → $4000` → phase computed STATELESSLY, only ONE modify issued for final state |
| `test_nkd_external_close_handling` | UserStream `_on_position_update` size=0 mid-trail → trail loop drops the signal; no further modifies |
| `test_nkd_compliance_gate_lockdown_stops_trail` | `check_compliance_gate.execution_mode == "MANUAL"` mid-position → trail loop logs + halts modifies (does NOT close) |

**Replay test:**

| Test | Asserts |
|---|---|
| `test_replay_22h_nkd_trade_2026_05_13` | A scripted replay of the actual 22h trade that paid $7125, with the new trail block in place, computes a final realised PnL within ±$50 of $7125 and never exceeds $4450 TP |

**Verdict:** total of ~15 new test files/cases. Test load is concentrated in phase math + ratchet semantics — pure-function tests, very fast.

---

## 12. Open questions for the operator

These are items the prompt did not specify and the codebase cannot answer:

1. **NKD `margin_per_contract`** — `7700` (per `bootstrap_production.py:65`, `seed_all_assets.py:71`) or `11000` (per `load_p2_multi_asset.py:67` and operator prompt)? Affects B4 sizing if NKD position size > 1 (margin × size × buffer).
2. **Trail-loop placement** — in `b7_position_monitor.py` directly (mixed concerns) or new `b7b_nkd_trail.py` block (cleaner, GUI block-registry update needed)?
3. **Bracket order-ID capture strategy** — R1 (UserStream), R2 (REST poll), or R3 (switch NKD to fallback non-OCO path)? R3 is fastest to ship; R1 is most robust long-term.
4. **Compliance wrapper for `/modify`** — gate every modify call (§8.2), or document the implicit "modify inherits placement compliance" assumption?
5. **Risk-budget reallocation lever** — Intervention A (HMM weight override), B (`sl_multiple` lowering), C (per-session E override), or all three?
6. **TP LIMIT order tick alignment** — confirm broker treats `$4450 / point_value = 890 NKD points` LIMIT as binding even if not perfectly grid-aligned. Existing `_compute_tp` (long: `floor`) already does the right thing. Operator should confirm against a previous bracket order's recorded fill.
7. **Per-tower jitter activation** — confirm Isaac tower will set `INSTANCE_PARITY=1` (`docs/captain-audit/05-PARITY-SKIP.md` §05.3) and Nomaan tower keeps it as `0` or unset. If unset, parity is disabled (`captain-command/.../orchestrator.py:455-457`) AND jitter must also be disabled by the trail block's logic — confirm semantics.
8. **Replay data availability** — does a tick-level (sub-1min) bar export exist for 2026-05-12/13 NKD to feed the replay test in §11.2?
9. **D34 retention** — partition `BY DAY` (current schema sketch) or keep indefinitely for audit?

---

## 13. Effort estimate (per work-item, 2-3 day deadline)

| # | Item | Size | Parallel/Serial | Note |
|---|---|---|---|---|
| 1 | New table `p3_d34_nkd_trail_state` + M048 migration + COLUMN_TYPES check | XS | Parallel | Pure schema, no consumers blocked |
| 2 | Bracket order-ID capture (R3 fallback path, lowest risk) | S | Serial — blocks 3 | `b3_api_adapter.py` NKD branch |
| 2-alt | Bracket order-ID capture (R1 UserStream-based) | M | Serial | Cleaner; more touch points |
| 3 | NKD trail block (phase math, ratchet, modify dispatch, persistence) | M | Serial — depends on 1, 2 | `b7b_nkd_trail.py` or B7 inline |
| 4 | Isaac jitter sampling + persistence | XS | Parallel with 3 | Shares trail-state row |
| 5 | TIME_EXIT NKD exemption | XS | Parallel | `b7_position_monitor.py:310-322` |
| 6 | Outward tick-snap helper | XS | Parallel | `shared/contract_resolver.py` or new module |
| 7 | Compliance gate wrapper for `/modify` (if elected) | S | Parallel | `b12_compliance_gate.py` |
| 8 | Risk-budget reallocation (Intervention A or B) | XS | Parallel | DB UPSERT only; no rebuild |
| 9 | Unit tests for phase math, ratchet, jitter (§11.2) | M | Parallel with 3 | ~10 unit cases |
| 10 | Integration tests for session span / modify retry / external close | M | Serial after 3 | Mocks pysignalr |
| 11 | Replay test against 2026-05-13 22h trade | M | Serial after all above | Needs §12.8 data |
| 12 | GUI panel column for trail-state (Trade panel + Telegram alert text) | S | Parallel with 3 | `captain-gui/src/components/trading/*` |
| 13 | Tower deploy + smoke-test | S | Serial after everything | Sync `_config/`, dual-remote push per workspace rule |

**Critical path (picking R3 + Intervention A):** XS + S + M + XS + XS + XS + M + M + S ≈ **2.5 to 3.5 dev-days**. Tight against the 2-3 day operator deadline. Specifically tight if:

- The replay test (#11) is treated as mandatory pre-deploy — depends on §12.8 data availability.
- The compliance wrapper (#7) is required rather than documented-as-deferred.
- Bracket-capture is upgraded from R3 fallback to R1 UserStream (#2-alt) for long-term robustness.

**Compression options:**

- Ship R3 (fallback non-OCO) on day 1; backport R1 (UserStream capture) as a hardening pass later.
- Treat #11 replay test as a Tower-side validation (operator runs it in pre-market like `docs2/pre-market-22-04-deadline/PRE_MARKET_CHECKLIST.md`) rather than a unit test.
- Defer #7 compliance wrapper if operator accepts placement-time compliance inheritance.

---

## 14. Stop here

Per the prompt's closing constraint: this report ENDS the read-only audit. No implementation, no follow-on planning, no code patches. Awaiting operator decisions on the §12 open questions before any code lands.
