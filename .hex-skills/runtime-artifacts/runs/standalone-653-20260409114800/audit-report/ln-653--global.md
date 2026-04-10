# Runtime Performance Audit Report

<!-- AUDIT-META
worker: ln-653
category: Runtime Performance
domain: global
scan_path: captain-online/captain_online/blocks/b7_position_monitor.py,captain-online/captain_online/blocks/b7_shadow_monitor.py,captain-online/captain_online/blocks/b1_data_ingestion.py,shared/topstep_client.py
score: 8.9
total_issues: 4
critical: 0
high: 0
medium: 1
low: 3
status: completed
-->

## Checks

| ID | Check | Status | Details |
|----|-------|--------|---------|
| blocking_io_in_async | Blocking IO in async functions | passed | No async def found in any of the 4 files — fully synchronous codebase |
| unnecessary_list_allocation | Unnecessary list allocations | passed | No any([...]), all([...]), len([...]) patterns found |
| sync_sleep_in_async | Sync sleep in async functions | passed | No async def in scope; time.sleep calls are in sync retry loops (correct) |
| string_concat_in_loop | String concatenation in loops | passed | No += string building inside loops detected |
| missing_to_thread | Missing to_thread for CPU-bound in async | passed | No async context; ThreadPoolExecutor in b1 is correct sync pattern |
| redundant_data_copies | Redundant data copies | passed | No .copy(), list(...) wrap, or dict(...) copy patterns found |

## Findings

| Severity | Location | Issue | Principle | Recommendation | Effort |
|----------|----------|-------|-----------|----------------|--------|
| MEDIUM | captain-online/captain_online/blocks/b7_position_monitor.py:388 | time.sleep in synchronous position-resolution hot path: up to 3.5s total blocking (0.5s + 1s + 2s) per failed publish. During a Redis outage, the entire monitor loop stalls for each position being resolved. | Runtime Performance / Sync Sleep in Hot Path | Move retry to a background thread or use a non-blocking fire-and-forget queue (e.g. push to a local deque and drain on next tick). Alternatively reduce max_attempts to 2 and cap total backoff to 1.5s. | S |
| LOW | captain-online/captain_online/blocks/b7_position_monitor.py:366 | `import time` deferred inside `_publish_trade_outcome()` function body. Python caches module imports so the cost is minimal but non-zero on every call into an already-hot function. | Runtime Performance / Unnecessary Import Overhead | Move `import time` to the module-level import block at the top of the file. | S |
| LOW | captain-online/captain_online/blocks/b1_data_ingestion.py:365 | `ThreadPoolExecutor` created and destroyed fresh on each call to `_prefetch_market_data`. Pool construction/teardown overhead is incurred at every session open (typically 3× per day). | Runtime Performance / Pool Construction Overhead | For a function called only 3× per day the cost is negligible, but if called more frequently consider a module-level pool or `concurrent.futures.ProcessPoolExecutor` reuse pattern. Low priority given invocation frequency. | S |
| LOW | shared/topstep_client.py:367 | `time.sleep` in `_post()` for 429 rate-limit backoff. Intentional and documented, but blocks the calling thread for up to `RATE_LIMIT_BASE_DELAY_S * 2^attempt` seconds during rate-limited bursts. | Runtime Performance / Blocking Backoff | Acceptable in synchronous requests-based client. If the client is ever called from a thread pool that has limited workers, document the maximum blocking duration so callers can size the pool accordingly. No code change required; add a comment. | S |
