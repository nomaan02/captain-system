# Session Replay Tab — User Guide

## What Is It?

The Replay tab is a **sandboxed flight simulator** for the Captain trading system. It lets you replay any past trading session (or test hypothetical configs) without affecting the live system. Everything is read-only — no trades are placed, no live data is modified.

## Getting Started

1. Navigate to **http://localhost** in your browser
2. Click **"Replay"** in the top navigation bar (between Reports and Settings)
3. You'll see the Replay page with three panels: Config (left), Asset Cards (center), Summary (right)

## Running a Replay

### Step 1: Configure

In the left panel, set your parameters:

| Parameter | Description | Default |
|-----------|-------------|---------|
| **Date** | Which trading day to replay | Today |
| **Session** | NY, LONDON, APAC, or NY_PRE | NY |
| **Capital** | Starting account capital | $150,000 |
| **Budget Divisor** | How many days to spread MDD over (higher = more conservative) | 20 |
| **MDD Limit** | Maximum drawdown before trading stops | $4,500 |
| **MLL Limit** | Maximum daily loss limit | $2,250 |
| **Max Positions** | Maximum simultaneous trades | 5 |
| **Max Contracts** | Per-asset contract cap | 15 |
| **TP Multiple** | Take-profit as fraction of OR range | 0.70 |
| **SL Multiple** | Stop-loss as fraction of OR range | 0.35 |
| **Risk Goal** | Account risk profile (PASS_EVAL is most conservative) | PASS_EVAL |
| **CB L1 Enabled** | Circuit breaker Layer 1 preemptive halt | On |
| **Speed** | Simulation speed (1x = real-time, 100x = fast) | 50x |

### Step 2: Run

Click the green **"Run Replay"** button. The system will:

1. **Load config** from QuestDB (your overrides are applied on top, without changing live data)
2. **Authenticate** with TopstepX to fetch historical bar data
3. **Process each asset** through the full pipeline:
   - Fetch 1-minute bars from TopstepX (cached locally after first fetch)
   - Compute Opening Range (OR high, OR low, range)
   - Detect breakout direction (LONG/SHORT/none)
   - Simulate TP/SL exit
   - Run full Kelly sizing (10-step pipeline)
   - Apply position limits
4. **Stream results** to the UI in real time

### Step 3: Watch

As the replay runs:

- The **Pipeline Stepper** (top of left panel) shows which B-block is executing
  - Click any completed block to expand its detail panel
  - B3 shows individual AIM modifiers with vote arrows (▲ increase / ▼ decrease / — neutral)
  - B4 shows the full Kelly sizing trace table (every intermediate value)
- **Asset Cards** appear one by one in the center panel as each asset completes
- The **Simulated Position** panel shows the active trade (entry, live P&L, TP/SL levels)
- Green cards = profitable trades, Red cards = losses, Grey = blocked, Red background = errors

### Step 4: Review

When the replay completes:

- The **Summary panel** (right) shows total PnL, win/loss record, and trade table
- Click **"Save"** to persist the results (stored in QuestDB `p3_replay_results`)
- Click **"Discard"** to throw away the results

## Playback Controls

| Control | Action |
|---------|--------|
| **▶ / ⏸** | Play or pause the simulation |
| **1x / 10x / 50x / 100x** | Change simulation speed |
| **⏭ Skip** | Jump to next breakout, exit, or error event |

At **1x speed**, each 1-minute bar arrives every 60 seconds (true real-time). At **100x**, the full session processes in seconds.

## What-If Scenarios

After a replay completes:

1. **Modify parameters** in the config panel (e.g., change Budget Divisor from 20 to 10)
2. Click **"Run What-If"** in the summary panel
3. The system **reuses cached bars** (no API calls) and instantly recalculates sizing
4. A **comparison overlay** appears showing:
   - Original PnL vs What-If PnL vs Delta
   - Per-asset contract count changes
   - Which assets changed from blocked to active (or vice versa)

This lets you test "what would have happened if..." scenarios instantly.

## Saving and Loading

### Config Presets

- Configure parameters → click **"Save Preset"** → name it
- Next time, select the preset from the dropdown to load those exact settings
- Presets persist across browser sessions

### Replay History

- Saved replays appear in the **History** section (right panel)
- Click a saved replay to view its results without re-running
- History is stored in QuestDB and persists across container restarts

## Understanding the Pipeline Visualization

### Pipeline Stepper Blocks

| Block | Name | What It Does |
|-------|------|--------------|
| **B1** | Data Ingestion | Loads assets, specs, strategies from QuestDB |
| **B2** | Regime Detection | Classifies market as calm/stormy (currently neutral 50/50) |
| **B3** | AIM Aggregation | Combines 6 AI model signals into a sizing modifier |
| **B4** | Kelly Sizing | Computes optimal position size (10-step pipeline) |
| **B5** | Trade Selection | Applies position limits, selects top trades by edge |
| **B5C** | Circuit Breaker | L1 preemptive halt — blocks trades exceeding risk threshold |
| **B6** | Signal Output | Final trade signals ready for execution |

### Kelly Sizing Trace (B4 Detail)

When you expand B4, you see every step for every asset:

```
Asset  K_lo    K_hi    Blend   ×Shrk   ×0.7    EWMA    FbRisk  Raw  MDD  MLL  Max  CB  Final  Binding
ES     0.0593  0.0380  0.0487  0.0474  0.0332  192.17  200     25   1    11   15       1      MDD
```

- **K_lo / K_hi**: Kelly fractions for calm/stormy regimes
- **Blend**: Weighted average (50/50 when regime neutral)
- **×Shrk**: After shrinkage factor
- **×0.7**: After PASS_EVAL risk goal (70% of full Kelly)
- **EWMA / FbRisk**: Risk per contract from trade history / fallback from SL distance
- **Raw**: Unconstrained Kelly contracts
- **MDD / MLL / Max**: Cap from drawdown budget, daily loss, and absolute max
- **CB**: Circuit breaker reduction (if any)
- **Final**: Actual contracts traded
- **Binding**: Which constraint was the tightest

### AIM Breakdown (B3 Detail)

Shows 6 Adaptive Intelligence Modules per asset:

| AIM | What It Measures |
|-----|------------------|
| 4 - Trend Strength | Is price trending or ranging? |
| 6 - Mean Reversion | Is price overextended and likely to reverse? |
| 8 - Momentum Quality | Is the breakout backed by genuine momentum? |
| 11 - Vol Regime | Is volatility expanding or contracting? |
| 12 - Correlation | Are correlated assets confirming the signal? |
| 15 - Micro Regime | Short-term regime shifts |

Vote arrows: **▲** = AIM wants to increase size, **▼** = decrease, **—** = neutral

## Important Notes

- **Completely isolated**: Replay never writes to live QuestDB tables (D00, D08, D12, etc.)
- **Bar caching**: First replay for a given date fetches bars from TopstepX API. Subsequent replays (including what-if) reuse the cache — no redundant API calls.
- **Cache location**: `data/bar_cache.sqlite` (auto-pruned after 30 days)
- **TopstepX auth**: The replay uses your TopstepX credentials to fetch historical data. This is read-only and doesn't place any orders.

## API Reference (Advanced)

If you want to trigger replays programmatically:

```bash
# Start a replay
curl -X POST http://localhost:8000/api/replay/start \
  -H "Content-Type: application/json" \
  -d '{"date": "2026-03-30", "session": "NY", "speed": 100.0}'

# Control playback
curl -X POST http://localhost:8000/api/replay/control \
  -H "Content-Type: application/json" \
  -d '{"action": "pause"}'

# Run what-if
curl -X POST http://localhost:8000/api/replay/whatif \
  -H "Content-Type: application/json" \
  -d '{"config_overrides": {"budget_divisor": 10}}'

# Save results
curl -X POST http://localhost:8000/api/replay/save \
  -H "Content-Type: application/json" \
  -d '{"replay_id": "abc123def456"}'

# View history
curl http://localhost:8000/api/replay/history

# Manage presets
curl http://localhost:8000/api/replay/presets
curl -X POST http://localhost:8000/api/replay/presets \
  -H "Content-Type: application/json" \
  -d '{"name": "Conservative", "config": {"budget_divisor": 30, "risk_goal": "PRESERVE_CAPITAL"}}'
```
