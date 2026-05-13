# `/smart-explore` — MCP + manual structural map

**Stamp:** commit `ef24edf632eba2462527505d28c5a75b133fb612`, `2026-05-12T14:08:20Z`

## MCP results

Tool: `smart_search` (`plugin-claude-mem-mcp-search`)

| Query | Path | Result |
|-------|------|--------|
| `orchestrator block redis questdb` | `/home/nomaan/captain-system` | **0 symbols** (1535 files scanned) |
| `class Orchestrator` | `/home/nomaan/captain-system` | **0 symbols** |

**Interpretation:** Tree-sitter corpus indexing did not surface Python classes in this environment. Subagents must **not rely on this file alone** — use repo-relative paths below.

## Manual layout (verified directories)

| Area | Path | Role |
|------|------|------|
| Offline brain | `captain-offline/captain_offline/blocks/` | AIM lifecycle, DMA, drift, BOCPD/CUSUM, Kelly L1, diagnostics, scheduler hooks |
| Online engine | `captain-online/captain_online/blocks/` | B1–B9 sessions pipeline, OR tracker, signals |
| Command link | `captain-command/captain_command/blocks/` | Routing, GUI feed, Topstep adapter, compliance, reconciliation |
| Shared | `shared/` | QuestDB client + schemas, Redis helpers, Topstep REST, AIM math |
| Schema SO-T | `shared/canonical_schemas.py` | CREATE DDL + `CANONICAL_MIGRATIONS` |
| Init | `scripts/init_questdb.py` | Applies `CANONICAL_DDLS` + migrations |
| Compose | `docker-compose.yml`, `docker-compose.local.yml` | Service wiring |

## Orchestrator entrypoints (files)

| Process | Primary file |
|---------|----------------|
| Offline | `captain-offline/captain_offline/blocks/orchestrator.py` |
| Online | `captain-online/captain_online/blocks/orchestrator.py` |
| Command | `captain-command/captain_command/blocks/orchestrator.py` |

## Signal / execution hot path

```
captain-online/b6_signal_output.py  →  Redis stream `stream:signals`
captain-command/orchestrator.py     →  consumer group `GROUP_COMMAND_SIGNALS`
captain-command/b1_core_routing.py  →  sanitise + route
captain-command/b3_api_adapter.py →  TopstepXAdapter.send_signal
shared/topstep_client.py           →  REST /Order/place (+ bracket)
```
