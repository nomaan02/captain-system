# Captain System -- Claude Code Reference

## Who You Are Helping

Nomaan -- strong Python/SWE, limited trading knowledge. Explain quant concepts in plain language with engineering analogies. Show complete code. Break problems into smaller pieces when stuck.

## Project Summary

**Captain Function** is a continuous 24/7 automated trading system built as part of the MOST (Market Open Short-Term) project. It executes Opening Range Breakout strategies on futures via the TopstepX brokerage API.

The system is a 3-process Docker pipeline with 28 blocks total, backed by QuestDB (29 tables) and Redis (5 pub/sub channels). It receives market data, runs regime detection and AIM (Adaptive Intelligence Module) scoring, sizes positions via Kelly criterion, and routes trade signals to the brokerage.

**This is a standalone repository.** P1/P2 research pipelines live separately in the original `most-production` repo and are not part of this codebase.

---

## Architecture

3 independent Docker processes sharing QuestDB + Redis:

| Process | Role | Blocks | Trigger |
|---------|------|--------|---------|
| Captain Offline | Strategic brain (AIM training, decay detection, Kelly) | 9 + orchestrator | Event-driven + scheduled |
| Captain Online | Signal engine (data -> regime -> AIM -> sizing -> signal) | 9 + orchestrator | Session-open (NY/LON/APAC) |
| Captain Command | Linking layer (routing, GUI, API, reconciliation) | 10 + orchestrator | Always-on |

### Critical Feedback Loop

This is the "system is alive" loop -- all three processes must participate:

```
Online B1-B6 -> signal -> Redis -> Command -> GUI -> TAKEN
  -> Command creates position -> Online B7 monitors
  -> TP/SL hit -> trade outcome -> P3-D03 -> Redis
  -> Offline updates DMA(D02), BOCPD(D04), EWMA(D05), Kelly(D12)
  -> Next session reads updated state -> new signal reflects
```

---

## File Structure

```
captain-system/
|-- captain-offline/           # Strategic brain process
|   |-- captain_offline/
|   |   |-- blocks/            # b1_aim_lifecycle, b1_dma_update, b2_bocpd, b3_pseudotrader, ...
|   |   |-- main.py
|   |-- Dockerfile
|   |-- requirements.txt
|-- captain-online/            # Signal engine process
|   |-- captain_online/
|   |   |-- blocks/            # b1_data_ingestion, b2_regime_probability, b3_aim_aggregation, ...
|   |   |-- main.py
|   |-- Dockerfile
|   |-- requirements.txt
|-- captain-command/           # Linking layer process (FastAPI on :8000)
|   |-- captain_command/
|   |   |-- blocks/            # b1_core_routing, b2_gui_data_server, b3_api_adapter, ...
|   |   |-- api.py
|   |   |-- main.py
|   |-- Dockerfile
|   |-- requirements.txt
|-- captain-gui/               # React/Vue SPA (builds static assets into shared volume)
|   |-- src/
|   |-- dist/
|   |-- package.json
|   |-- Dockerfile
|-- shared/                    # Code shared across all 3 processes (mounted read-only)
|   |-- topstep_client.py      # REST client (18 endpoints)
|   |-- topstep_stream.py      # WebSocket streaming (pysignalr, MarketStream + UserStream)
|   |-- contract_resolver.py   # Futures contract resolution (10 assets)
|   |-- account_lifecycle.py   # EVAL -> XFA -> LIVE account progression
|   |-- questdb_client.py      # QuestDB connection helper
|   |-- redis_client.py        # Redis connection + pub/sub helper
|   |-- vault.py               # AES-256-GCM encrypted key vault
|   |-- journal.py             # SQLite WAL crash recovery journal
|   |-- constants.py           # Shared constants
|   |-- statistics.py          # Statistical utilities
|   |-- signal_replay.py       # Signal replay for debugging
|   |-- trade_source.py        # Trade data source abstraction
|   |-- vix_provider.py        # VIX/VXV data provider
|-- config/                    # Configuration files
|   |-- compliance_gate.json   # Compliance rules
|   |-- contract_ids.json      # TopstepX contract ID mappings
|   |-- tsm/                   # Trade State Machine configs
|   |-- stress_tests/          # Stress test scenarios
|   |-- test_scenarios/        # Test scenario definitions
|-- scripts/                   # Operational scripts
|   |-- init_questdb.py        # Create QuestDB tables
|   |-- init_sqlite.py         # Create SQLite journals
|   |-- init_all.py            # Combined initialisation
|   |-- bootstrap_production.py # Production data bootstrap (strategies, capital, AIM, CB)
|   |-- seed_all_assets.py     # Full 17-asset seed from P1/P2 files
|   |-- seed_test_asset.py     # Seed test data
|   |-- seed_system_params.py  # Seed D17 system parameters
|   |-- ...
|-- tests/                     # Test suite
|   |-- test_pipeline_e2e.py   # Full pipeline end-to-end
|   |-- test_integration_e2e.py
|   |-- test_b2_regime.py, test_b3_aim.py, ...
|   |-- conftest.py
|   |-- fixtures/, helpers/, scenarios/
|-- deploy/                    # Deployment scripts (setup-server.sh, deploy.sh, update.sh)
|-- nginx/                     # Nginx config (nginx-local.conf for dev, TLS for prod)
|-- vault/                     # Encrypted API key vault (never commit keys)
|-- data/                      # Runtime data directory
|-- logs/                      # Application logs
|-- questdb/                   # QuestDB data directory (Docker volume)
|-- redis/                     # Redis AOF persistence
|-- docker-compose.yml         # Base compose (all 6 services)
|-- docker-compose.local.yml   # Local override (HTTP, memory limits, WSL 2)
|-- captain-start.sh           # WSL 2 startup script
|-- .env                       # Environment variables (DO NOT COMMIT)
|-- .env.template              # Template for .env
```

---

## Docker Workflow

The system runs 6 containers: QuestDB, Redis, captain-offline, captain-online, captain-command, captain-gui, and nginx.

**Always use both compose files locally** (base + local override):

```bash
# Start everything (first run or after code changes)
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build

# Start without rebuild (daily restart)
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d

# Stop everything
docker compose -f docker-compose.yml -f docker-compose.local.yml down

# Rebuild and restart a single container
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build captain-online

# View logs for a specific container
docker compose -f docker-compose.yml -f docker-compose.local.yml logs -f captain-online

# Check container health
docker compose -f docker-compose.yml -f docker-compose.local.yml ps

# Or use the startup script (handles prerequisites, health checks, QuestDB init):
bash captain-start.sh              # Normal start
bash captain-start.sh --build      # Force rebuild
```

**Key ports (all bound to 127.0.0.1):**
- 80 -- nginx (GUI + API proxy)
- 8000 -- captain-command FastAPI (dev direct access)
- 9000 -- QuestDB web console (admin only)
- 8812 -- QuestDB PostgreSQL wire protocol
- 6379 -- Redis

---

## Redis Channels

| Channel | Publisher | Subscriber | Payload |
|---------|----------|------------|---------|
| `captain:signals:{user_id}` | Online B6 | Command B1 | Signal batch (direction, size, TP, SL, per-account) |
| `captain:trade_outcomes` | Online B7 | Offline orch | Trade outcome (trade_id, pnl, regime, AIM context) |
| `captain:commands` | Command B1 | Online, Offline | TAKEN/SKIPPED, strategy decisions, TSM, AIM control |
| `captain:alerts` | Any process | Command B7 | Alert with priority (CRITICAL/HIGH/MEDIUM/LOW) |
| `captain:status` | All processes | Command B1 | Heartbeat + health |

---

## TopstepX Integration

All brokerage integration code lives in `shared/`:

| File | Purpose |
|------|---------|
| `shared/topstep_client.py` | REST client -- 18 endpoints (auth, orders, positions, accounts) |
| `shared/topstep_stream.py` | WebSocket streaming via pysignalr (MarketStream + UserStream) |
| `shared/contract_resolver.py` | Maps asset symbols to TopstepX contract IDs (10 assets) |
| `shared/account_lifecycle.py` | EVAL -> XFA -> LIVE account progression logic |

**Reference:** `TOPSTEPX_API_REFERENCE.md` in the old `most-production` repo root (or `C:\Users\nomaa\repos\tsxapi4py` for raw API source).

**Rules:**
- Read the API reference FIRST before writing any integration code
- Never guess enum values -- OrderType 1=Limit, 2=Market (not the other way around)
- Never guess field names -- always verify against the reference
- TopstepX requires email as `userName` for auth
- Use `TOPSTEP_` prefix for all env vars

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Database | QuestDB (29 tables, PostgreSQL wire) |
| Message Queue | Redis (AOF, 5 pub/sub channels) |
| Deployment | Docker Compose (6 containers) |
| Crash Recovery | SQLite WAL (1 per process) |
| API Gateway | nginx (TLS 1.3 for prod, HTTP for local) |
| Encryption | AES-256-GCM (API key vault) |
| Timezone | America/New_York (system-wide) |
| GUI | React/Vue SPA + WebSocket |
| Notifications | Telegram Bot API |
| Streaming | pysignalr (TopstepX SignalR WebSocket) |

---

## Frozen / Locked Files -- DO NOT MODIFY

These files are locked by spec. If a task requires changing them, STOP and ask Nomaan.

- Control parameters in `config/` -- never alter control values
- `shared/constants.py` -- shared constant definitions
- Any file explicitly marked FROZEN or LOCKED in code comments

**Note:** The original P1/P2 frozen files (`features.py`, `fe_variables.py`, `fe_transformations.py`, `feature_engine.py`, `opening_range.py`, `risk_manager.py`) live in the old `most-production` repo, not here.

---

## Rules

1. **Isaac's spec is law** -- if code would differ from spec, follow spec and flag for Nomaan
2. **One block at a time** -- never implement two blocks simultaneously
3. **Ask, don't assume** -- if any spec requirement is ambiguous, STOP and ask
4. **Timezone is always America/New_York** -- all timestamps, all processes, no exceptions
5. **Multi-user from day one** -- never hardcode single-user assumptions
6. **Never commit secrets** -- `.env`, vault keys, API tokens stay out of git
7. **Spec files:** V3 amendments (in `docs/CAPTAIN-FUNCTION-DOCS-NEW-AMENDMENTS/`) SUPERSEDE original specs where conflicts exist

---

## Current System State (2026-03-27)

**Status: DATA BOOTSTRAPPED -- ready for live session evaluation at NY open (09:30 ET).**

All 28 blocks implemented. All 6 containers healthy. Data bootstrap complete:

| Table | State | Details |
|-------|-------|---------|
| D00 (asset_universe) | 10 active, 1 P2-elim, 6 P1-elim | locked_strategy + specs populated for all 10 |
| D01 (aim_model_states) | 270 rows | Tier 1 AIMs installed per asset |
| D02 (aim_meta_weights) | 60 rows | Equal initial weights (6 AIMs x 10 assets) |
| D05 (ewma_states) | 60 rows | Bootstrapped from P1 trade history |
| D08 (tsm_state) | 1 account | 20319811 (150K Trading Combine) |
| D12 (kelly_params) | 60 rows | Bootstrapped from P1 trade history |
| D16 (capital_silos) | primary_user | $150K, account 20319811 linked, max 5 positions |
| D25 (circuit_breaker) | 1 row | Cold-start (beta_b=0, layers 3-4 disabled) |

**Active account:** 20319811 (TopstepX PRAC-V2-551001-43861321, $150K Trading Combine)
**AUTO_EXECUTE:** true

### Locked Strategies (from P2-D06)

Each asset has its own (m,k) pair. **Never use a single pair for all assets.**

| Asset | m | k | OO | Sessions |
|-------|---|---|-----|----------|
| ES | 7 | 33 | 0.8832 | NY |
| MES | 7 | 32 | 0.8879 | NY |
| NQ | 3 | 32 | 0.8242 | NY |
| MNQ | 5 | 32 | 0.8236 | NY |
| M2K | 5 | 32 | 0.9245 | NY |
| MYM | 9 | 115 | 0.7705 | NY |
| NKD | 6 | 6 | 0.8533 | APAC |
| MGC | 2 | 29 | 0.8892 | NY |
| ZB | 10 | 113 | 0.8054 | NY |
| ZN | 4 | 37 | 0.9058 | NY |

### Bootstrap Scripts

| Script | Purpose |
|--------|---------|
| `scripts/bootstrap_production.py` | Populates all 5 data gaps (D00 strategies/specs, D16 silo, D02 AIM weights, D25 CB). Run after init_all.py. |
| `scripts/seed_all_assets.py` | Full 17-asset seed from P1/P2 data files (includes bootstrap runner). |
| `scripts/init_all.py` | Phase 1 init: tables + params + test asset + user. |

---

## P1/P2 Research Data

P1/P2 pipelines live in the `most-production` repo (`C:\Users\nomaa\QuantConnect\most-production\`).

- P2 locked strategies are ALSO copied to `data/p2_outputs/{ASSET}/p2_d06_locked_strategy.json` in this repo
- P1 D-22 trade logs are at `data/p1_outputs/{ASSET}/d22_trade_log_{asset}.json`
- Each of 10 surviving assets has its OWN best (m,k) pair from P2
- **WARNING:** m=4,k=017 was the original single-asset ES-only run -- NEVER use it for all assets

If Captain decay detection (Level 3) triggers a P1/P2 rerun, refer to the `most-production` repo CLAUDE.md.

---

## Dev Setup

Quick start:
1. Copy `.env.template` to `.env` and fill in credentials
2. Run `bash captain-start.sh --build` (WSL 2 required)
3. Run `bootstrap_production.py` inside captain-command container (see Bootstrap Scripts above)
4. Access GUI at `http://localhost:80`
5. Access QuestDB console at `http://localhost:9000`

---

## Multi-Instance Deployment

Captain System supports running two independent instances on separate machines with different TopstepX accounts. Trades are split deterministically so neither account takes the same trades.

### Architecture

```
Instance A (PARITY=0, Nomaan)            Instance B (PARITY=1, client)
Takes signals 1, 3, 5...                 Takes signals 2, 4, 6...
     |                                        |
     |--- Both see ALL signals ---|           |
     |                            |           |
  Shadow monitor tracks           Shadow monitor tracks
  theoretical outcomes for        theoretical outcomes for
  signals 2, 4, 6...              signals 1, 3, 5...
     |                                        |
  Category A learning (ALL signals):  DMA, EWMA, Kelly, BOCPD  <- SYNCHRONIZED
  Category B learning (OWN trades):   CB params, TSM            <- INDEPENDENT
```

No network connection between instances. Zero cloud linkage. Compliant with TopstepX API ToS.

### Key Files

| File | Purpose |
|------|---------|
| `captain-command/.../orchestrator.py` | Parity filter (`_check_parity_skip`) — daily Redis counter, deterministic trade splitting |
| `captain-online/.../b7_shadow_monitor.py` | Tracks theoretical TP/SL outcomes for signals not executed |
| `captain-offline/.../orchestrator.py` | `_handle_signal_outcome()` — Category A learning from theoretical outcomes |
| `scripts/captain-setup.sh` | Interactive setup wizard for fresh machine deployment |
| `scripts/captain-update.sh` | Pull + rebuild script for receiving code updates |
| `scripts/bootstrap_production.py` | Parameterized via env vars (`BOOTSTRAP_ACCOUNT_ID`, `BOOTSTRAP_USER_ID`, `BOOTSTRAP_STARTING_CAPITAL`) |

### Category A vs B Learning Split

Strategy parameters learn from ALL signals (both instances stay synchronized):
- **D02** AIM meta-weights (DMA update)
- **D04** BOCPD changepoint detection
- **D05** EWMA win rate / avg win / avg loss
- **D12** Kelly fraction and shrinkage

Account-specific risk parameters learn from TAKEN trades only (each instance adapts to its own account):
- **D25** Circuit breaker beta_b (loss serial correlation)
- **D08** TSM state (actual account balance, MDD)
- **D16** Capital silo (real P&L)

### Setup on a New Machine

```bash
git clone https://github.com/nomaan02/captain-multi-user.git captain-system
cd captain-system
bash scripts/captain-setup.sh
# Answer prompts: email, API key, account name, account ID, capital, parity=1
# Wait ~5 minutes for build
# Done — GUI at http://localhost
```

### Pushing Updates

```bash
# On Nomaan's machine: commit + push
git push multi-user main

# On client machine: pull + rebuild (~2 min)
bash scripts/captain-update.sh
```

The update script warns if `.env.template` has new variables that need adding to `.env`.

### Git Remotes

| Remote | URL | Purpose |
|--------|-----|---------|
| `origin` | `https://github.com/nomaan02/captain-system.git` | Primary private repo (Nomaan only) |
| `multi-user` | `https://github.com/nomaan02/captain-multi-user.git` | Shared repo for multi-instance deployment |

### Environment Variables (Multi-Instance)

| Variable | Values | Purpose |
|----------|--------|---------|
| `INSTANCE_PARITY` | `0`, `1`, or empty | Trade alternation: 0=odd signals, 1=even signals, empty=all (single instance) |
| `BOOTSTRAP_ACCOUNT_ID` | TopstepX account ID | Used by bootstrap script for D16/D25 seeding |
| `BOOTSTRAP_USER_ID` | User identifier | Default: `primary_user` |
| `BOOTSTRAP_STARTING_CAPITAL` | Dollar amount | Default: `150000` |

---

## Running Tests

Tests run on the host (not inside containers). Some tests need container-only deps (pysignalr, numpy).

```bash
# Block-level unit tests (64 tests, no container deps needed)
PYTHONPATH=./:./captain-online:./captain-offline:./captain-command \
  python3 -B -m pytest tests/ \
  --ignore=tests/test_integration_e2e.py \
  --ignore=tests/test_pipeline_e2e.py \
  --ignore=tests/test_pseudotrader_account.py \
  --ignore=tests/test_offline_feedback.py \
  --ignore=tests/test_stress.py \
  --ignore=tests/test_account_lifecycle.py \
  -v
```

---

## Spec Files

**V3 Authoritative specs (55 files):** `docs/CAPTAIN-FUNCTION-DOCS-NEW-AMENDMENTS/`
- Start with `Nomaan_Master_Build_Guide.md`, then `Cross_Reference_PreDeploy_vs_V3.md`

**Original specs:** `docs/completion-validation-docs/Step 1 - Original Specs/`
- `03_Program3_Architecture.md` -- Architecture
- `04_Program3_Offline.md` -- Offline blocks
- `05_Program3_Online.md` -- Online blocks
- `06_Program3_Command.md` -- Command blocks
- `07_P3_Dataset_Schemas.md` -- QuestDB table schemas
