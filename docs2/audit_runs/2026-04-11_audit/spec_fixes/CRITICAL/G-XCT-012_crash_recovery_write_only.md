# G-XCT-012 — Crash Recovery Journal Is Write-Only Across All 3 Processes

| Field | Value |
|-------|-------|
| **Severity** | CRITICAL |
| **Process** | Cross-Cutting (all 3 processes) |
| **Block** | main.py startup logic |
| **Spec Reference** | Doc 33 Crash Recovery, Doc 32 Version Snapshot Policy |
| **File(s)** | `captain-offline/captain_offline/main.py`, `captain-online/captain_online/main.py`, `captain-command/captain_command/main.py` |
| **Fixed In** | Session 3.1, commit `cd35c24` |

## What Was Wrong (Before)

All 3 processes diligently wrote checkpoints throughout execution (60+ `write_checkpoint()` calls codebase-wide). On startup, all 3 called `get_last_checkpoint(ROLE)`, logged the result, and then **proceeded with normal initialization — completely ignoring the checkpoint state**.

Example (captain-online/main.py):
```python
last = get_last_checkpoint(ROLE)
if last:
    logger.info(f"Resuming from: {last['checkpoint']} — next: {last.get('next_action','fresh')}")
# ... proceeds with full fresh startup regardless
```

If Online crashed mid-session with checkpoint `STREAMS_STARTED`, it restarted streams from scratch. If Offline crashed after `WEEKLY_START` with `next_action = "run_sensitivity"`, the sensitivity scan was never resumed. The journal infrastructure was complete but the **recovery logic was entirely missing**.

## What Was Fixed (After)

Checkpoint branching logic added to each process:

**Captain Offline:**
- `WEEKLY_START` / `TRADE_OUTCOME` / `ORCHESTRATOR_STARTED` / `AIMS_SEEDED` → skips `_seed_aim_states()`, jumps directly to orchestrator event loop
- Avoids re-seeding AIM states that are already populated

**Captain Online:**
- `STREAMS_STARTED` → reconnects streams without full re-initialization
- `SESSION_ACTIVE` → mid-session resume (re-attaches to active session)
- `SESSION_COMPLETE` → advances to next session
- Crash detection: if `next_action` is not `shutdown`/`initialization`/empty, writes a `CRASH_RECOVERY` checkpoint with metadata

**Captain Command:**
- `ORCHESTRATOR_STARTED` → fast restart (skips TSM/Telegram/TopstepX init if already connected)
- `RECONCILIATION` → resumes start-of-day reconciliation

**All processes:**
- `SHUTDOWN` / `None` paths preserve existing fresh-start behaviour (clean restart)
- Recovery paths write a `RECOVERY` checkpoint with `recovered_from` and `original_entry` metadata for debugging

## Overall Feature: Crash Recovery Journal

The crash recovery journal (`shared/journal.py`) is a SQLite WAL-backed persistence layer that tracks each process's progress through its startup and operational phases. Each `write_checkpoint()` call records the current state, what the process was doing, and what it should do next. On restart, `get_last_checkpoint()` retrieves the last recorded state.

The purpose is **idempotent recovery** — if a process crashes mid-operation, it should resume from where it left off rather than restarting from scratch. This prevents duplicate processing (e.g., re-running a DMA update that already committed), missed work (e.g., skipping a sensitivity scan that was next in queue), and unnecessary latency (e.g., re-initializing streams that just need reconnection). The journal is especially important for Offline, where mid-run crashes could leave parameter updates in a half-committed state.
