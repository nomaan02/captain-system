# 03 — Live calculations

**TL;DR**

- Lists **who computes** session-critical quantities, **where stored**, and **transport** — verified paths use **PostgreSQL wire** (`psycopg2`) + **Redis Streams**, not ILP (no production ILP writer found).
- Deep formulas for AIM/Kelly remain in source — this is an **operator map**.
- Does **not** replay historical bars — see replay harness separately.

**Audit stamp:** commit `ef24edf632eba2462527505d28c5a75b133fb612`, `2026-05-12T14:08:20Z`

## 03.1 Calculation matrix

| ID | Calculation | Computes | Stored | Writer mechanism | Retry / errors |
|----|-------------|----------|--------|------------------|----------------|
| L1 | Active asset filter (`captain_status`, session) | `b1_data_ingestion._load_active_assets` ~49–101 | In-memory dict | SELECT `p3_d00_asset_universe` | Skip row — log |
| L2 | Data quality flags | `_run_data_moderator` ~450+ | `p3_d00_asset_universe.data_quality_flag` | UPDATE via helper | Drops `DATA_HOLD` assets ~492 |
| L3 | OR breakout direction / range | `b8_or_tracker.py` + orchestrator injection | `features` dict | Memory → B6 | Session logs |
| L4 | Regime probabilities | `b2_regime_probability.py` | Redis/session payload | Mixed PG + compute | See block logs |
| L5 | AIM aggregate modifier | `b3_aim_aggregation.py` | Payload | Reads D01/D02 via PG | Falls back per block |
| L6 | Kelly sizing contracts | `b4_kelly_sizing.py` | `final_contracts` | Memory | CB downstream clamps |
| L7 | Signal TP/SL levels | `b6_signal_output._compute_tp/_compute_sl` ~259–300 | Redis stream payload | `publish_to_stream` | Fire-and-forget publish |
| L8 | Position PnL + outcome | `b7_position_monitor.py` | `p3_d03_trade_outcome_log`, `p3_d16`, `p3_d23` | `qexecute` INSERT/UPDATE | Alerts on `PointValueResolutionError` ~75–79 |
| L9 | Trade outcome fan-out | `b7` | Redis `stream:trade_outcomes` | `publish_to_stream` | Backoff mentioned module header |

## 03.2 QuestDB write path

**Analog:** PG wire is the **cargo rail** — every crate is a parameterized INSERT; `qexecute` is the **weight station** ensuring DECIMAL-shaped crates fit column gauges.

| Concern | Detail |
|---------|--------|
| Protocol | `psycopg2` → QuestDB PostgreSQL wire `:8812` |
| ILP | **Not used** in Captain runtime (`rg ILP` → debug script only) |
| Typed inserts | `qexecute` maps columns using `COLUMN_TYPES` derived from canonical DDL (`shared/canonical_schemas.py` ~1065+) |

Verify DB responds:

```bash
curl -s -G "http://127.0.0.1:9000/exec" --data-urlencode "query=SELECT count() FROM p3_d00_asset_universe"
```

## 03.3 Redis streams inventory

| Stream / channel | Producer | Consumer |
|------------------|----------|----------|
| `stream:signals` (`STREAM_SIGNALS`) | Online `b6_signal_output.py` | Command `orchestrator.py` (~194–220) |
| `stream:trade_outcomes` (`STREAM_TRADE_OUTCOMES`) | Online `b7_position_monitor.py` | Offline orchestrator trade outcome handlers |

Constants: `shared/redis_client.py` ~77–78.

## 03.4 Redis streams & retry semantics

| Step | Behavior | File anchor |
|------|----------|-------------|
| Consumer group ensure | `ensure_consumer_group` on startup | `captain-command/.../orchestrator.py` ~194 |
| Read | `read_stream_messages` w/ pending reclaim | ~200–220 |
| ACK | `ack_message` after routing | ~209 |

Inspect pending entries:

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T redis redis-cli XINFO GROUPS stream:signals
```

## 03.5 Command FastAPI & signal handler

Recent stability work referenced in memory ID **#1570** lives around `captain-command/captain_command/api.py` (signal handling vs lifespan). Verify server health:

```bash
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/docs
```

## 03.6 Parameters

| name | value | file | line | source-of-truth | rationale |
|------|-------|------|------|-----------------|----------|
| `STREAM_SIGNALS` | `stream:signals` | `shared/redis_client.py` | 77 | Code constant | Redis stream name |
| `STREAM_TRADE_OUTCOMES` | `stream:trade_outcomes` | `shared/redis_client.py` | 78 | Code constant | Outcomes stream |
| PG cast adapter | per-value DECIMAL(p,s) | `shared/questdb_client.py` | 40–63 | Code | Avoid QDB cast bugs |

Cross-links: schema [02.5](02-QUESTDB-SCHEMA.md#025-decimal-runtime-casting-policy), trade flow [04](04-TRADE-LOGIC.md).
