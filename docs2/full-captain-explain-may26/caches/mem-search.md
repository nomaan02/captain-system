# `/mem-search` — raw MCP aggregate

**Stamp:** commit `ef24edf632eba2462527505d28c5a75b133fb612`, `2026-05-12T14:08:20Z`  
**Tool:** `plugin-claude-mem-mcp-search` → `search`

## Query A — `captain system orchestrator signal execution Topstep` (limit 40, date_desc)

Found 55 matches (40 obs, 12 sessions, 3 prompts). Representative rows:

| Date | ID | File / bucket | Title |
|------|-----|----------------|-------|
| Apr 9 | #1570 | `captain-command/captain_command/api.py` | NEW-A04 signal handler fix — removed `signal.signal()`, lifespan delegation |
| Apr 9 | #1527 | `captain-offline/captain_offline/main.py` | SIGNAL_OUTCOMES stream consumer group gap |
| Apr 9 | #1511 | `captain-command/.../orchestrator.py` | Orchestrator pattern across three subsystems |
| Apr 11 | #2147 | `captain-online/.../main.py` | Full auto-trade flow mapped (signal → execution) |
| Apr 11 | #2028 | `captain-command/.../orchestrator.py` | Auto-execute replaced hardcoded `primary_user` GUI pushes |
| Apr 12 | #2231 | `captain-command/.../orchestrator.py` | API health checks every 30s |
| Apr 12 | #2155 | `captain-command/.../orchestrator.py` | Redis Streams XACK after processing |
| Apr 13 | #2413 | `captain-command/.../b1_core_routing.py` | Auto-order placement flow via TopstepX |
| Apr 13 | #2379/#2380 | `captain-online/.../main.py` | TopstepX auth retry / fatal failure |
| Apr 14 | #2477 | `captain-command/.../b3_api_adapter.py` | Adapter init + health monitoring |
| Apr 15 | #2587 | `captain-command/.../orchestrator.py` | Non-idempotent signal handler duplicate notifications |
| Apr 15 | #2557 | `captain-online/.../b6_signal_output.py` | Trading safety architecture |
| Apr 16 | #2730 | `scripts/compact_questdb_tables.py` | QuestDB append-only bloat / compaction |
| Apr 27 | #3023 | `captain-offline/.../orchestrator.py` | Scheduler polling vs event-driven |
| May 8 | #3219 | `captain-gui/.../PseudotraderPage.jsx` | WarmupStatus in Pseudotrader page |

## Query B — `QuestDB Kelly AIM parity` (limit 30, date_desc)

| Date | ID | Anchor | Title |
|------|-----|--------|-------|
| Apr 15 | #2681 | `scripts/compact_questdb_tables.py` | Five append-only state targets |
| Apr 15 | #2627 | `b2_gui_data_server.py` | AIM states via GUI server |
| Apr 20 | #2815 | `b8_kelly_update.py` | D05/D12/D25 schema consistency |
| Apr 27 | #3005 | `b7_position_monitor.py` | D03 writers / locked-strategy access |
| May 8 | #S423–S433 | sessions | AIM modal fix + QuestDB ops threads |

## Ambiguity log (for clarification)

- Duplicate path prefixes (`captain-system/...` vs repo-relative).
- GUI registry filenames vs real offline modules (see `.audit-cache/README.md`).
