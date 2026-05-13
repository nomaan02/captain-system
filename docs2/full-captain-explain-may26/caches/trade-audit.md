# Captain Trade Audit — cache (`captain-trade-audit` checklist)

**Stamp:** commit `ef24edf632eba2462527505d28c5a75b133fb612`, ISO `2026-05-12T14:08:20Z`  
**Scope:** Code verified at HEAD only — environment / `.env` not executed here.

## Captain Auto-Trade Audit Report

### Date: 2026-05-12

### Status: **PASS WITH WARNINGS**

### Critical Findings (MUST FIX before go-live)

- None verified **from enum mapping / bracket path alone** at HEAD. Re-run Stage 0 against production `.env` before live capital.

### Warnings

- **[W1]** Trade-audit skill text still describes **three separate orders** as primary; **`TopstepXAdapter.send_signal`** prefers **atomic bracket** when `entry_est`, `tp`, `sl`, `tick_size` are present — see `captain-command/captain_command/blocks/b3_api_adapter.py` (~241–277). Update runbooks that assume three REST calls as the only path.
- **[W2]** `sanitise_for_api` returns **more than six keys** (includes `signal_id`, `user_id`, `session`, `entry_price`, model context) — `captain-command/captain_command/blocks/b1_core_routing.py` ~131–153. Adapter path must continue to ignore extras when building REST payloads (currently does).

### Verified OK (selected)

| Stage | Evidence |
|-------|-----------|
| Stage 3 enums | `shared/topstep_client.py` ~54–66 `OrderSide` BUY=0 SELL=1; `OrderType` LIMIT=1 MARKET=2 STOP=4 |
| Bracket payload | `shared/topstep_client.py` ~342–382 `place_bracket_order`: MARKET entry + `stopLossBracket{type:STOP}` + `takeProfitBracket{type:LIMIT}` |
| Direction mapping | `captain-command/.../orchestrator.py` ~588–591 maps `1`/`-1` → `"BUY"`/`"SELL"`; `b3_api_adapter.py` ~231 maps to `OrderSide` |
| Compliance gate | `b3_api_adapter.py` ~211–224 `check_compliance_gate` + `compliance_check` before placement |
| Redis stream | `shared/redis_client.py` `STREAM_SIGNALS = "stream:signals"`; command orchestrator ensures consumer group (`orchestrator.py` ~194–220) |
| AUTO_EXECUTE | `orchestrator.py` ~463 reads env once per evaluation: `("1","true","yes")` |

### Enum Mapping Verification

| Internal | Expected API | Actual @ HEAD | Status |
|----------|--------------|----------------|--------|
| LONG `direction==1` → BUY string | MARKET `type=2`, side Bid `0` | `OrderType.MARKET`, `OrderSide.BUY` in bracket path | ✓ |
| SHORT `direction==-1` | MARKET `type=2`, side Ask `1` | `OrderSide.SELL` | ✓ |
| SL bracket | type **4** STOP | `OrderType.STOP` in `stop_loss_bracket` | ✓ |
| TP bracket | type **1** LIMIT | `OrderType.LIMIT` in `take_profit_bracket` | ✓ |

### Recommendations

1. Run Stage 0–2 against live `.env` + `config/compliance_gate.json` on the tower before enabling capital.
2. Align external docs with **bracket-first** execution path.
