# NY Open 2026-05-06 — Truncated logs (Troubleshooting digest)

**Source:** `all_logs.md` (same folder). **Session date in logs:** 2026-05-06 ET.

**What was removed:** Repeated per-asset boilerplate (duplicate `pass_probability` / `max_daily_loss` Kelly preamble lines), health-check spam, verbose websocket/api noise, and duplicate AIM-per-asset lines (one representative kept where useful).

**What this digest emphasizes:** MNQ / MES / M2K path (parity, portfolio skip, shadow PnL), Command execution vs skip, and all ERROR/WARNING lines retained verbatim.

---

## Quick read: MNQ, MES, M2K, NQ


| Asset   | What happened                                                                                                                                                                                                                                                              |
| ------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **MNQ** | Signals generated with ES/NQ/MES in first Phase B batch. **Neither tower auto-executed MNQ** — Command **parity skip** on both (see Command sections). Shadow monitor later: **SL_HIT** (theoretical). Offline Category A learning for MNQ **failed** (`qexecute` import). |
| **MES** | Same as MNQ for **parity skip** (no Command AUTO-EXECUTE). Shadow: **SL_HIT** (theoretical). Offline MES outcome processing **failed** (`qexecute`).                                                                                                                       |
| **M2K** | OR breakout fired later; **ON-B6-SKIP**: M2K removed by **portfolio-level constraint (correlation or position limit)** — **B6 short-circuited (no candidates)** for that wave. Not a parity issue; portfolio optimizer dropped it alongside ES.                            |
| **NQ**  | Kelly sizing **0 contracts [SKIP]** (`tsm=0 topstep=0`). Also listed in B6 skip reasons as **Position size rounded to 0**.                                                                                                                                                 |


**NaN on signal cards:** These logs do **not** contain the string `NaN`. For **MNQ/MES**, the practical explanation in-log is **parity skip** (signals published from Online, but **no trades** on either account for those assets). Investigate GUI serialization separately if NaN still appears when SL/TP are present in the Redis/API payload.

---

## 1. Isaac (captain-tower-2) — captain-online

**Account:** `20258288` — `150KTC-V2-478426-52758441`

**Container recycle before RTH:** shutdown ~09:22:20, asyncio pending-task errors on exit, then clean restart ~09:22:22.

```text
captain-online-1 | [ONLINE] 2026-05-06 09:22:20,583 ERROR asyncio: Task was destroyed but it is pending!
captain-online-1 | task: <Task pending name='Task-3' coro=<Connection.keepalive() done, defined at /usr/local/lib/python3.12/site-packages/websockets/asyncio/connection.py:808> wait_for=>
captain-online-1 | [ONLINE] 2026-05-06 09:22:20,584 ERROR asyncio: Task was destroyed but it is pending!
captain-online-1 | task: <Task pending name='Task-6' coro=<Connection.keepalive() done, defined at /usr/local/lib/python3.12/site-packages/websockets/asyncio/connection.py:808> wait_for=>
captain-online-1 | [ONLINE] 2026-05-06 09:22:20,584 ERROR asyncio: Task was destroyed but it is pending!
captain-online-1 | task: <Task pending name='Task-9' coro=<<async_generator_athrow without name>()>>
captain-online-1 | [ONLINE] 2026-05-06 09:22:20,584 ERROR asyncio: Task was destroyed but it is pending!
captain-online-1 | task: <Task pending name='Task-10' coro=<<async_generator_athrow without name>()>>
```

**NY session open / Kelly (representative + MNQ MES M2K NQ):**

```text
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,284 INFO captain_online.blocks.orchestrator: ON-Orch: session NY init for 20258288 — eff_L_halt=750.00 eff_E=750.00 (SOD share=0.3163, completed=1 earlier sessions, carryover=275.59)

captain-online-1 | [ONLINE] 2026-05-06 09:25:10,731 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: MNQ ac=20258288 kelly=0.0669→0.0569(rg)→156.7(raw) risk/c=54.5 cap=150000 tsm=8 topstep=8 scale=999 → 8 contracts [TRADE]

captain-online-1 | [ONLINE] 2026-05-06 09:25:10,752 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: M2K ac=20258288 kelly=0.0685→0.0583(rg)→428.3(raw) risk/c=20.4 cap=150000 tsm=15 topstep=26 scale=999 → 15 contracts [TRADE]

captain-online-1 | [ONLINE] 2026-05-06 09:25:10,759 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: MES ac=20258288 kelly=0.0845→0.0718(rg)→547.8(raw) risk/c=19.7 cap=150000 tsm=15 topstep=25 scale=999 → 15 contracts [TRADE]

captain-online-1 | [ONLINE] 2026-05-06 09:25:10,766 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: NQ ac=20258288 kelly=0.0737→0.0627(rg)→17.7(raw) risk/c=531.3 cap=150000 tsm=0 topstep=0 scale=999 → 0 contracts [SKIP]
```

**MGC OR warning:**

```text
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,938 WARNING captain_online.blocks.b8_or_tracker: OR EXPIRED (stuck WAITING): MGC — no ticks received before cutoff 03:35:00 (market stream may be disconnected for this contract)
```

**Opening range / breakouts (MNQ, MES, M2K):**

```text
captain-online-1 | [ONLINE] 2026-05-06 09:35:00,050 INFO captain_online.blocks.b8_or_tracker: OR COMPLETE: MNQ — high=28446.5000 low=28336.7500 range=109.7500 (5537 ticks)

captain-online-1 | [ONLINE] 2026-05-06 09:35:00,101 INFO captain_online.blocks.b8_or_tracker: OR COMPLETE: MES — high=7341.2500 low=7327.2500 range=14.0000 (3391 ticks)

captain-online-1 | [ONLINE] 2026-05-06 09:35:00,197 INFO captain_online.blocks.b8_or_tracker: OR COMPLETE: M2K — high=2881.2000 low=2873.5000 range=7.7000 (1587 ticks)

captain-online-1 | [ONLINE] 2026-05-06 09:35:00,494 INFO captain_online.blocks.b8_or_tracker: OR BREAKOUT LONG: MES — price=7341.5000 > OR high=7341.2500, or_range=14.0000

captain-online-1 | [ONLINE] 2026-05-06 09:35:00,746 INFO captain_online.blocks.b8_or_tracker: OR BREAKOUT LONG: MNQ — price=28446.7500 > OR high=28446.5000, or_range=109.7500

captain-online-1 | [ONLINE] 2026-05-06 09:35:03,850 INFO captain_online.blocks.orchestrator: Phase B: generated signals for ['ES', 'NQ', 'MNQ', 'MES']

captain-online-1 | [ONLINE] 2026-05-06 09:35:05,847 INFO captain_online.blocks.b8_or_tracker: OR BREAKOUT LONG: M2K — price=2881.4000 > OR high=2881.2000, or_range=7.7000

captain-online-1 | [ONLINE] 2026-05-06 09:35:06,357 WARNING captain_online.blocks.orchestrator: ON-B6-SKIP 

user=primary_user session=1 assets_filter=['M2K'] recommended_trades=['ZB', 'ZN', 'MNQ', 'MYM', 'MES'] 

account_skip_reason={'MNQ': {'20258288': None},
 'ES': {'20258288': 'Removed by portfolio-level constraint (correlation or position limit)'}, 
'M2K': {'20258288': 'Removed by portfolio-level constraint (correlation or position limit)'}, 
'MES': {'20258288': None}, 
'MYM': {'20258288': None}, 
'NQ': {'20258288': 'Position size rounded to 0'},
 'ZB': {'20258288': None}, 
'ZN': {'20258288': None}} — B6 short-circuited (no candidates)
captain-online-1 | [ONLINE] 2026-05-06 09:35:06,357 INFO captain_online.blocks.orchestrator: Phase B: generated signals for ['M2K']
```

**Shadow / B7:**

```text
captain-online-1 | [ONLINE] 2026-05-06 09:38:00,480 INFO captain_online.blocks.b7_shadow_monitor: Shadow resolved: MNQ SL_HIT SIG-4D524C4EAE13 pnl=-629.33 (theoretical)

captain-online-1 | [ONLINE] 2026-05-06 09:39:16,168 ERROR captain_online.blocks.b7_position_monitor: ON-B7: cannot cancel orphan brackets for MYM — account_id unresolved (account=20258288)

captain-online-1 | [ONLINE] 2026-05-06 09:42:14,171 ERROR captain_online.blocks.b7_position_monitor: ON-B7: cannot cancel orphan brackets for ZB — account_id unresolved (account=20258288)

captain-online-1 | [ONLINE] 2026-05-06 09:50:51,821 INFO captain_online.blocks.b7_shadow_monitor: Shadow resolved: MES SL_HIT SIG-AD90E5324AE5 pnl=-550.00 (theoretical)
```

---

## 2. Isaac — captain-command (parity + execution)

**Parity skips (MNQ, MES, ZN) vs executes (MYM, ZB):**

```text
captain-command-1 | [COMMAND] 2026-05-06 09:35:03,840 INFO captain_command.blocks.orchestrator: PARITY CHECK: trade_number=1, signal_parity=0, my_parity=1, skip=True, assets=['MNQ', 'MES']

captain-command-1 | [COMMAND] 2026-05-06 09:36:03,166 INFO captain_command.blocks.orchestrator: PARITY CHECK: trade_number=2, signal_parity=1, my_parity=1, skip=False, assets=['MYM']

captain-command-1 | [COMMAND] 2026-05-06 09:36:03,172 INFO captain_command.blocks.orchestrator: AUTO-EXECUTE: BUY MYM x15 (account=20258288, TP=49983.0, SL=49877.0)

captain-command-1 | [COMMAND] 2026-05-06 09:36:03,539 ERROR captain_command.blocks.b3_api_adapter: Bracket order FAILED (errorCode=2): Brackets cannot be used with Position Brackets. You must enable Auto OCO Brackets.

 [asset=MYM account=20258288 side=BUY size=15 SL_ticks=35 TP_ticks=71 entry_est=49912] — falling back to NON-OCO separate orders. Orphan SL/TP cleanup will be attempted by B7 on resolution.

captain-command-1 | [COMMAND] 2026-05-06 09:36:43,897 INFO captain_command.blocks.orchestrator: PARITY CHECK: trade_number=3, signal_parity=0, my_parity=1, skip=True, assets=['ZN']

captain-command-1 | [COMMAND] 2026-05-06 09:42:12,945 INFO captain_command.blocks.orchestrator: PARITY CHECK: trade_number=4, signal_parity=1, my_parity=1, skip=False, assets=['ZB']

captain-command-1 | [COMMAND] 2026-05-06 09:42:13,244 WARNING captain_command.blocks.b1_core_routing: Unknown command type: SESSION_CLOSE from user SYSTEM

captain-command-1 | [COMMAND] 2026-05-06 09:42:13,349 ERROR captain_command.blocks.b3_api_adapter: Bracket order FAILED (errorCode=2): Brackets cannot be used with Position Brackets. You must enable Auto OCO Brackets. 

[asset=ZB account=20258288 side=SELL size=15 SL_ticks=1 TP_ticks=2 entry_est=113.46875] — falling back to NON-OCO separate orders. Orphan SL/TP cleanup will be attempted by B7 on resolution.
```

*Verbatim line from `all_logs.md` immediately before Isaac’s PARITY block (line 285 in source — pasted log loses the leading `c` on the container name):*

```text
aptain-command-1 | INFO: 127.0.0.1:60504 - "GET /api/health HTTP/1.1" 200 OK
```

---

## 3. Isaac — captain-offline

```text
captain-offline-1 | [OFFLINE] 2026-05-06 09:36:43,923 ERROR captain_offline.blocks.orchestrator: Error processing signal outcome for ZN: cannot import name 'qexecute' from 'shared.questdb_client' (/app/shared/questdb_client.py)
captain-offline-1 | [OFFLINE] 2026-05-06 09:38:01,604 ERROR captain_offline.blocks.orchestrator: Error processing signal outcome for MNQ: cannot import name 'qexecute' from 'shared.questdb_client' (/app/shared/questdb_client.py)
captain-offline-1 | [OFFLINE] 2026-05-06 09:39:16,245 ERROR captain_offline.blocks.orchestrator: Stream listener error: float() argument must be a string or a real number, not 'dict' — reconnecting in 1s
captain-offline-1 | [OFFLINE] 2026-05-06 09:42:14,276 ERROR captain_offline.blocks.orchestrator: [pg01c] training dispatch failed: cannot import name 'qexecute' from 'shared.questdb_client' (/app/shared/questdb_client.py)
captain-offline-1 | [OFFLINE] 2026-05-06 09:42:14,279 ERROR captain_offline.blocks.orchestrator: Stream listener error: float() argument must be a string or a real number, not 'dict' — reconnecting in 1s
captain-offline-1 | [OFFLINE] 2026-05-06 09:42:16,326 ERROR captain_offline.blocks.orchestrator: Error processing signal outcome for ZB: cannot import name 'qexecute' from 'shared.questdb_client' (/app/shared/questdb_client.py)
captain-offline-1 | [OFFLINE] 2026-05-06 09:50:53,818 ERROR captain_offline.blocks.orchestrator: Error processing signal outcome for MES: cannot import name 'qexecute' from 'shared.questdb_client' (/app/shared/questdb_client.py)
```

---

## 4. Nomaan (captain-tower-1) — captain-online

**Account:** `21855714` — `150KTC-V2-551001-86041837`

**Container recycle:** same asyncio pattern ~09:22:22.

```text
captain-online-1 | [ONLINE] 2026-05-06 09:22:22,561 ERROR asyncio: Task was destroyed but it is pending!
captain-online-1 | task: <Task pending name='Task-3' coro=<Connection.keepalive() done, defined at /usr/local/lib/python3.12/site-packages/websockets/asyncio/connection.py:808> wait_for=>
captain-online-1 | [ONLINE] 2026-05-06 09:22:22,562 ERROR asyncio: Task was destroyed but it is pending!
captain-online-1 | task: <Task pending name='Task-4' coro=<Connection.keepalive() done, defined at /usr/local/lib/python3.12/site-packages/websockets/asyncio/connection.py:808> wait_for=>
captain-online-1 | [ONLINE] 2026-05-06 09:22:22,562 ERROR asyncio: Task was destroyed but it is pending!
captain-online-1 | task: <Task pending name='Task-9' coro=<<async_generator_athrow without name>()>>
captain-online-1 | [ONLINE] 2026-05-06 09:22:22,562 ERROR asyncio: Task was destroyed but it is pending!
captain-online-1 | task: <Task pending name='Task-10' coro=<<async_generator_athrow without name>()>>
```

**B5C circuit breaker fallback (21855714):**

```text
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,155 WARNING captain_online.blocks.b5c_circuit_breaker: ON-B5C: L1 falling back to live L_halt=1500.00000 for 21855714 session=1 (no SOD per-session value)

captain-online-1 | [ONLINE] 2026-05-06 09:25:11,155 WARNING captain_online.blocks.b5c_circuit_breaker: ON-B5C: L2 falling back to live E=1500.0000 for 21855714 session=1 (no SOD per-session value)
```

*(Original repeats similar L1/L2 warnings multiple times for the same account; one pair shown.)*

**Kelly NQ + MNQ MES M2K:**

```text
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,127 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: NQ ac=21855714 kelly=0.0724→0.0616(rg)→17.4(raw) risk/c=531.3 cap=150000 tsm=0 topstep=999 scale=999 → 0 contracts [SKIP]

captain-online-1 | [ONLINE] 2026-05-06 09:25:11,126 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: MNQ ac=21855714 kelly=0.0658→0.0559(rg)→154.0(raw) risk/c=54.5 cap=150000 tsm=8 topstep=999 scale=999 → 8 contracts [TRADE]

captain-online-1 | [ONLINE] 2026-05-06 09:25:11,123 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: MES ac=21855714 kelly=0.0845→0.0718(rg)→547.8(raw) risk/c=19.7 cap=150000 tsm=15 topstep=999 scale=999 → 15 contracts [TRADE]

captain-online-1 | [ONLINE] 2026-05-06 09:25:11,123 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: M2K ac=21855714 kelly=0.0674→0.0573(rg)→421.1(raw) risk/c=20.4 cap=150000 tsm=15 topstep=999 scale=999 → 15 contracts [TRADE]
```

**Phase B + M2K B6 skip:**

```text
captain-online-1 | [ONLINE] 2026-05-06 09:35:03,285 INFO captain_online.blocks.orchestrator: Phase B: generated signals for ['MNQ', 'ES', 'NQ', 'MES']

captain-online-1 | [ONLINE] 2026-05-06 09:35:07,256 WARNING captain_online.blocks.orchestrator: ON-B6-SKIP user=primary_user session=1 assets_filter=['M2K'] recommended_trades=['ZB', 'ZN', 'MNQ', 'MYM', 'MES'] account_skip_reason={'MES': {'21855714': None}, 'MYM': {'21855714': None}, 'ES': {'21855714': 'Removed by portfolio-level constraint (correlation or position limit)'}, 'ZB': {'21855714': None}, 'M2K': {'21855714': 'Removed by portfolio-level constraint (correlation or position limit)'}, 'MNQ': {'21855714': None}, 'NQ': {'21855714': 'Position size rounded to 0'}, 'ZN': {'21855714': None}} — B6 short-circuited (no candidates)
captain-online-1 | [ONLINE] 2026-05-06 09:35:07,257 INFO captain_online.blocks.orchestrator: Phase B: generated signals for ['M2K']
```

**Shadow + B7:**

```text
captain-online-1 | [ONLINE] 2026-05-06 09:38:01,213 INFO captain_online.blocks.b7_shadow_monitor: Shadow resolved: MNQ SL_HIT SIG-3FF4EE9A1B09 pnl=-625.33 (theoretical)

captain-online-1 | [ONLINE] 2026-05-06 09:39:16,000 WARNING captain_online.blocks.b7_position_monitor: ON-B7: cannot resolve int account_id for MYM — falling back to polled price for exit (account=21855714)

captain-online-1 | [ONLINE] 2026-05-06 09:42:13,772 ERROR captain_online.blocks.b7_position_monitor: ON-B7: cannot cancel orphan brackets for ZB — account_id unresolved (account=21855714)

captain-online-1 | [ONLINE] 2026-05-06 09:50:51,370 INFO captain_online.blocks.b7_shadow_monitor: Shadow resolved: MES SL_HIT SIG-98C6A745A630 pnl=-643.75 (theoretical)
```

---

## 5. Nomaan — captain-command

**Startup / TSM:**

```text
captain-command-1 | [COMMAND] 2026-05-06 09:03:23,028 WARNING captain_command.blocks.b4_tsm_manager: TSM topstep_150k_live.json has errors: ['Missing required field: starting_balance', 'Missing required field: max_drawdown_limit']

captain-command-1 | [COMMAND] 2026-05-06 09:03:23,028 INFO main: TSM files loaded: 3/4 valid
```

**Parity + AUTO-EXECUTE (MNQ/MES skipped on this tower; MYM/ZB executed):**

```text
captain-command-1 | [COMMAND] 2026-05-06 09:35:03,275 INFO captain_command.blocks.orchestrator: PARITY CHECK: trade_number=2, signal_parity=1, my_parity=0, skip=True, assets=['MNQ', 'MES']

captain-command-1 | [COMMAND] 2026-05-06 09:36:02,988 INFO captain_command.blocks.orchestrator: PARITY CHECK: trade_number=3, signal_parity=0, my_parity=0, skip=False, assets=['MYM']

captain-command-1 | [COMMAND] 2026-05-06 09:36:02,993 INFO captain_command.blocks.orchestrator: AUTO-EXECUTE: BUY MYM x15 (account=21855714, TP=49983.0, SL=49877.0)

captain-command-1 | [COMMAND] 2026-05-06 09:36:03,434 INFO captain_command.blocks.b3_api_adapter: TopstepX BRACKET order PLACED: entry=2934939667 fill=49909.0 SL=35t TP=71t (BUY x15 @ CON.F.US.MYM.M26)

captain-command-1 | [COMMAND] 2026-05-06 09:36:43,657 INFO captain_command.blocks.orchestrator: PARITY CHECK: trade_number=4, signal_parity=1, my_parity=0, skip=True, assets=['ZN']

captain-command-1 | [COMMAND] 2026-05-06 09:42:12,608 INFO captain_command.blocks.orchestrator: PARITY CHECK: trade_number=5, signal_parity=0, my_parity=0, skip=False, assets=['ZB']

captain-command-1 | [COMMAND] 2026-05-06 09:42:12,618 INFO captain_command.blocks.orchestrator: AUTO-EXECUTE: SELL ZB x15 (account=21855714, TP=113.40625, SL=113.5)

captain-command-1 | [COMMAND] 2026-05-06 09:42:12,652 WARNING captain_command.blocks.b1_core_routing: Unknown command type: SESSION_CLOSE from user SYSTEM

captain-command-1 | [COMMAND] 2026-05-06 09:42:12,926 ERROR captain_command.blocks.b3_api_adapter: Bracket order FAILED (errorCode=2): Invalid stop loss ticks (1). Price should be at least 4 ticks away. [asset=ZB account=21855714 side=SELL size=15 SL_ticks=1 TP_ticks=2 entry_est=113.46875] — falling back to NON-OCO separate orders. Orphan SL/TP cleanup will be attempted by B7 on resolution.

captain-command-1 | [COMMAND] 2026-05-06 09:42:13,328 INFO captain_command.blocks.b3_api_adapter: TopstepX FALLBACK order PLACED: entry=2935091179 sl=2935091274 tp=2935091319 (SELL x15 @ CON.F.US.USA.M26)
```

---

## 6. Nomaan — captain-offline

```text
captain-offline-1 | [OFFLINE] 2026-05-06 08:54:38,886 WARNING captain_offline.blocks.version_snapshot: Could not prune old versions for P3-D01: unexpected token [FROM]
captain-offline-1 | LINE 1: DELETE FROM p3_d18_version_history
captain-offline-1 | ^
captain-offline-1 | (manual cleanup needed)
captain-offline-1 | [OFFLINE] 2026-05-06 09:36:44,898 ERROR captain_offline.blocks.orchestrator: Error processing signal outcome for ZN: cannot import name 'qexecute' from 'shared.questdb_client' (/app/shared/questdb_client.py)

captain-offline-1 | [OFFLINE] 2026-05-06 09:38:02,674 ERROR captain_offline.blocks.orchestrator: Error processing signal outcome for MNQ: cannot import name 'qexecute' from 'shared.questdb_client' (/app/shared/questdb_client.py)

captain-offline-1 | [OFFLINE] 2026-05-06 09:39:17,022 ERROR captain_offline.blocks.orchestrator: Stream listener error: float() argument must be a string or a real number, not 'dict' — reconnecting in 1s

captain-offline-1 | [OFFLINE] 2026-05-06 09:42:12,969 ERROR captain_offline.blocks.orchestrator: Error processing signal outcome for ZB: cannot import name 'qexecute' from 'shared.questdb_client' (/app/shared/questdb_client.py)

captain-offline-1 | [OFFLINE] 2026-05-06 09:42:14,021 ERROR captain_offline.blocks.orchestrator: [pg01c] training dispatch failed: cannot import name 'qexecute' from 'shared.questdb_client' (/app/shared/questdb_client.py)
captain-offline-1 | [OFFLINE] 2026-05-06 09:42:14,022 ERROR captain_offline.blocks.orchestrator: Stream listener error: float() argument must be a string or a real number, not 'dict' — reconnecting in 1s

captain-offline-1 | [OFFLINE] 2026-05-06 09:50:52,028 ERROR captain_offline.blocks.orchestrator: Error processing signal outcome for MES: cannot import name 'qexecute' from 'shared.questdb_client' (/app/shared/questdb_client.py)
```

---

## 7. Highlight roll-up — errors, warnings, and suspicious lines

**Severity: operational / correctness**


| Topic                       | Detail                                                                                                                                                                                                                              |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **MNQ + MES not traded**    | **Parity** on both towers skips the batch containing MNQ and MES (Isaac: `trade_number=1 … skip=True`; Nomaan: `trade_number=2 … skip=True`). Explains **no fills** and possibly **stale/incomplete UI** for those cards vs MYM/ZB. |
| **M2K not traded**          | **ON-B6-SKIP** — portfolio constraint removed **M2K** and **ES**; NQ already **0 contracts**.                                                                                                                                       |
| **Offline learning broken** | Repeated `**ImportError: cannot import name 'qexecute'`** from `shared.questdb_client` when processing theoretical outcomes — affects **ZN, MNQ, ZB, MES** (and Isaac ZN/MNQ/ZB/MES timeline).                                      |
| **Stream deserialization**  | `**float() ... not 'dict'`** on offline stream listener — likely bad payload shape on trade/outcome stream.                                                                                                                         |
| **Bracket orders**          | Isaac: Topstep **errorCode=2** Position Brackets vs Auto OCO. Nomaan ZB: **Invalid stop loss ticks (1)** — **min 4 ticks**, then **FALLBACK** non-OCO.                                                                              |
| **B7 cleanup**              | `**cannot cancel orphan brackets`** / `**account_id unresolved**` — Isaac MYM+ZB; Nomaan ZB (Nomaan MYM: **warning** fallback to polled price).                                                                                     |
| **Session close race**      | `**Unknown command type: SESSION_CLOSE from user SYSTEM`** around ZB bracket — timing/routing smell.                                                                                                                                |
| **Shutdown noise**          | **asyncio Task was destroyed but it is pending** on captain-online recycle (websockets keepalive).                                                                                                                                  |
| **Nomaan TSM**              | `**topstep_150k_live.json` missing fields** — 3/4 TSM files valid.                                                                                                                                                                  |
| **QuestDB maintenance**     | Nomaan offline: **DELETE FROM** parse error in version prune (`unexpected token [FROM]`).                                                                                                                                           |


**Signals with suspicious GUI correlation (not in raw docker logs):**  
The word `**NaN` does not appear** in `all_logs.md`. If cards showed NaN for SL/TP, cross-check **API/WebSocket payload** for skipped parity signals or **decimal JSON** (see project decimal remediation docs) separately from this file.

---

*End of truncated digest.*