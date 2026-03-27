# MOST Captain System — Stability Analysis & Vulnerability Map

> Deep analysis of all connectivity paths, failure modes, and recommended fixes for 24/7 stable operation.

## Executive Summary

The Captain System runs 6 Docker containers on a default bridge network with 4 external connection types (QuestDB PostgreSQL, Redis pub/sub, TopstepX REST/WebSocket, Telegram). Analysis identified **12 instability points** that can cause disconnections, data loss, or service degradation. The most critical issues are: no QuestDB connection pooling, fire-and-forget Redis pub/sub, and TopstepX WebSocket rapid-failure surrender.

---

## Architecture Overview

```
EXTERNAL                           DOCKER BRIDGE NETWORK
─────────                          ──────────────────────
Browser ──HTTP──► Nginx ─proxy──► Captain Command (port 8000)
                   │                 ├─ FastAPI/Uvicorn
                   │                 ├─ WebSocket Hub (/ws/{user_id})
                   │                 ├─ REST API (/api/*)
                   │                 ├─ Orchestrator (1s scheduler)
                   │                 ├─ Redis Listener (expo backoff)
                   │                 ├─ TopstepX Adapter (health monitor)
                   │                 ├─ GUI Data Server (B2)
                   │                 ├─ TSM Manager (B4)
                   │                 ├─ Notifications (Telegram)
                   │                 └─ Auto-Execute Handler
                   │
                   └──SPA files──► gui-dist volume (built by captain-gui)

TopstepX REST ◄──HTTPS──┐
TopstepX Mkt WS ◄──WSS──┤ Captain Command
TopstepX Usr WS ◄──WSS──┤   (outbound)
Telegram API ◄──HTTPS────┘

                  Captain Online (signal engine)        Captain Offline (strategic brain)
                   ├─ B1→B2→B3→B4→B5→B5B→B6            ├─ B1 AIM Lifecycle
                   ├─ B7 Position Monitor                ├─ B2 Decay Detection
                   ├─ Session Loop (NY/LON/APAC)         ├─ B3 Pseudotrader
                   ├─ Command Listener                   ├─ B8 Kelly/CB Params
                   └─ MarketStream (SignalR)              ├─ Scheduler (D/W/M/Q)
                                                         └─ Redis Listener

                  QuestDB (port 8812)                    Redis (port 6379)
                   ├─ 29 tables (P3-D00..D26)            ├─ captain:signals:{uid}
                   ├─ PostgreSQL wire protocol            ├─ captain:trade_outcomes
                   └─ HTTP console (9000)                 ├─ captain:commands
                                                         ├─ captain:alerts
                                                         └─ captain:status
```

---

## Connection Inventory

| # | Connection | Protocol | Host:Port | Direction | Timeout | Pooling | Reconnect | File |
|---|-----------|----------|-----------|-----------|---------|---------|-----------|------|
| 1 | QuestDB | psycopg2 (PG wire) | questdb:8812 | Bidirectional | None (default) | **None** | **None** | shared/questdb_client.py:21 |
| 2 | Redis pub/sub (listener) | TCP Redis | redis:6379 | Inbound | Blocking | Implicit | Expo 1-30s | cmd/orchestrator.py:136 |
| 3 | Redis pub/sub (publish) | TCP Redis | redis:6379 | Outbound | None | Implicit | **None** | shared/redis_client.py:24 |
| 4 | TopstepX REST | HTTPS | api.topstepx.com | Outbound | 15s | Session | Token @20h | shared/topstep_client.py:109 |
| 5 | TopstepX Market WS | WSS SignalR | rtc.topstepx.com | Inbound stream | 15s keepalive | Single | Auto 15s×10 | shared/topstep_stream.py:216 |
| 6 | TopstepX User WS | WSS SignalR | rtc.topstepx.com | Inbound stream | 15s keepalive | Single | Auto 15s×10 | shared/topstep_stream.py:438 |
| 7 | FastAPI HTTP | HTTP | 0.0.0.0:8000 | Inbound | None | Uvicorn | N/A | cmd/api.py:53 |
| 8 | GUI WebSocket | WS | 0.0.0.0:8000/ws/{uid} | Inbound | 10s send | Max 3/user | Client-side | cmd/api.py:167 |
| 9 | Telegram Bot | HTTPS long-poll | api.telegram.org | Outbound | None | None | **None** | cmd/main.py:128 |
| 10 | SQLite WAL | File I/O | /captain/journal.sqlite | Local | None | Per-op | N/A | shared/journal.py:19 |
| 11 | Nginx proxy | HTTP | captain-command:8000 | Internal | 24h (WS) | N/A | N/A | nginx/nginx-local.conf |
| 12 | Docker health | HTTP/shell | Various | Internal | 10s | N/A | 3-5 retries | docker-compose.yml |

---

## 12 Identified Vulnerabilities

### VUL-01: No QuestDB Connection Pooling [CRITICAL]

**Location:** `shared/questdb_client.py:32-41`

**Root Cause:** Every `get_cursor()` call creates a brand-new TCP connection via `psycopg2.connect()`, uses it for one query, then closes it. No connection pool exists.

**Impact:** Under load (e.g., Captain Command's 1-second scheduler running dashboard queries for multiple users + GUI data server + health checks), this creates hundreds of TCP connections per minute. Each connection requires TCP handshake + authentication overhead. Under stress, QuestDB can run out of file descriptors or connection slots, causing cascading failures across all three Captain processes.

**Evidence from today:** QuestDB JVM crash at 09:31 ET during first signal generation pipeline (10 assets × multiple queries per block).

**Recommended Fix:**
```python
# shared/questdb_client.py — replace get_cursor() with pooled connections
from psycopg2 import pool

_pool = None
_pool_lock = threading.Lock()

def _get_pool():
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = pool.ThreadedConnectionPool(
                    minconn=2,
                    maxconn=10,
                    host=QUESTDB_HOST,
                    port=QUESTDB_PORT,
                    user=QUESTDB_USER,
                    password=QUESTDB_PASSWORD,
                    database=QUESTDB_DB,
                )
    return _pool

@contextmanager
def get_cursor():
    p = _get_pool()
    conn = p.getconn()
    try:
        conn.autocommit = True
        cur = conn.cursor()
        yield cur
    finally:
        p.putconn(conn)
```

**Priority:** P0 — Fix immediately. Affects all three processes.

---

### VUL-02: No QuestDB Query Timeout [HIGH]

**Location:** `shared/questdb_client.py:23-29`

**Root Cause:** `psycopg2.connect()` is called without any `connect_timeout` or `options='-c statement_timeout=...'` parameter. If QuestDB hangs (e.g., during compaction, WAL replay, or after JVM crash), queries block indefinitely, freezing the calling thread.

**Impact:** A hung QuestDB connection blocks the Captain Command orchestrator's 1s scheduler loop, the online session pipeline, or the offline trade outcome handler. Since health checks also use QuestDB, the Docker health check itself can hang beyond its 10s timeout, causing Docker to mark the container as unhealthy and restart it — potentially during an active trade.

**Recommended Fix:**
```python
# shared/questdb_client.py — add timeouts
def get_connection():
    return psycopg2.connect(
        host=QUESTDB_HOST,
        port=QUESTDB_PORT,
        user=QUESTDB_USER,
        password=QUESTDB_PASSWORD,
        database=QUESTDB_DB,
        connect_timeout=5,                          # 5s connection timeout
        options='-c statement_timeout=15000',        # 15s query timeout
    )
```

**Priority:** P0 — Fix with VUL-01.

---

### VUL-03: Redis Pub/Sub Fire-and-Forget (No Delivery Guarantee) [HIGH]

**Location:** `captain-online/blocks/b6_signal_output.py:263`, `b7_position_monitor.py:359`

**Root Cause:** Redis `PUBLISH` is fire-and-forget. If the subscriber is disconnected at the moment of publish, the message is permanently lost. There is no queue, no retry, no acknowledgment. Critical messages affected:
- `captain:signals:{uid}` — trade signals from Online to Command
- `captain:trade_outcomes` — trade outcomes from Online to Offline (feedback loop)
- `captain:commands` — user decisions from Command to Online/Offline

**Impact:** A lost `captain:trade_outcomes` message means the Offline process never learns about a completed trade. EWMA, Kelly, and AIM states become stale. A lost `captain:signals` message means a valid signal never reaches the GUI or auto-execute handler. A lost `captain:commands` message means a TAKEN/SKIPPED decision never creates a position for B7 monitoring.

**Recommended Fix:**
```python
# Option A: Redis Streams (recommended — durable, replayable)
# Replace PUBLISH/SUBSCRIBE with XADD/XREADGROUP

# In publisher (b6_signal_output.py):
client.xadd("captain:signals:" + user_id, {"payload": json.dumps(signal_data)})

# In subscriber (cmd/orchestrator.py):
# Create consumer group once:
client.xgroup_create("captain:signals:*", "command_group", id="0", mkstream=True)
# Read:
messages = client.xreadgroup("command_group", "command_1", {"captain:signals:*": ">"})
# Acknowledge after processing:
client.xack(stream, "command_group", message_id)

# Option B: Write-through to QuestDB (simpler, less infra change)
# After PUBLISH, also INSERT into a QuestDB staging table.
# Subscriber checks staging table on reconnect for missed messages.
```

**Priority:** P1 — Fix before going live with real money. Trade outcomes are the system's learning signal.

---

### VUL-04: Redis Listener Thread Silent Death [HIGH]

**Location:** `captain-offline/blocks/orchestrator.py:93-94`, `captain-online/blocks/orchestrator.py:383`

**Root Cause:** The Redis listener runs in a daemon thread. In Captain Offline, if the listener throws an exception, it logs the error and the thread terminates silently (`except Exception as e: logger.error(...)`). There is no retry loop, no restart mechanism, and no alerting. The main scheduler thread continues running unaware that the listener is dead.

In Captain Command, there IS exponential backoff reconnection (orchestrator.py:176-189), but Captain Online and Offline lack this.

**Impact:** If Redis has a transient network hiccup, the Offline process permanently loses its ability to receive trade outcomes and commands. The system continues operating but the feedback loop is broken — Offline never updates EWMA/Kelly/AIM states. This is invisible until you notice stale parameters.

**Recommended Fix:**
```python
# captain-offline/blocks/orchestrator.py — add retry loop like Captain Command has
def _redis_listener(self):
    backoff = 1
    while self.running:
        try:
            client = get_redis_client()
            pubsub = client.pubsub()
            pubsub.subscribe(CH_TRADE_OUTCOMES, CH_COMMANDS)
            logger.info("Redis listener connected (backoff reset)")
            backoff = 1  # Reset on success
            for message in pubsub.listen():
                if not self.running:
                    break
                if message["type"] != "message":
                    continue
                # ... handle message ...
        except Exception as e:
            logger.error("Redis listener error: %s — reconnecting in %ds", e, backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, 30)
```

Apply same pattern to Captain Online's `_command_listener`.

**Priority:** P0 — Simple fix, prevents silent degradation.

---

### VUL-05: TopstepX WebSocket Rapid-Failure Surrender [MEDIUM]

**Location:** `shared/topstep_stream.py:287-305` (MarketStream), `shared/topstep_stream.py:506-522` (UserStream)

**Root Cause:** If the WebSocket connection opens, stays connected for less than 10 seconds, then disconnects — and this happens 5 times consecutively — the stream permanently stops reconnecting. The assumption is "market is closed or token is expired." But this also triggers during:
- Transient network congestion (ISP packet loss)
- Windows sleep/wake cycles
- Docker network reconfigurations
- Redis or QuestDB causing CPU spikes that starve the WS thread

**Impact:** MarketStream stops providing real-time quotes. B1 Data Ingestion falls back to REST (1-minute bars with 15s timeout), degrading signal quality. UserStream stops providing real-time position/order updates, making B7 Position Monitor blind to actual fill statuses.

**Recommended Fix:**
```python
# shared/topstep_stream.py — add time-based reset for rapid failure counter
def _on_close(self):
    if self._state == StreamState.DISCONNECTED:
        return

    now = time.time()
    uptime = now - self._last_open_time if self._last_open_time else 0

    if uptime < self._RAPID_THRESHOLD_S:
        self._rapid_failures += 1
    else:
        self._rapid_failures = 0

    # NEW: Reset rapid failure counter after 5 minutes of no failures
    if self._last_rapid_failure_time and (now - self._last_rapid_failure_time) > 300:
        self._rapid_failures = 0
    self._last_rapid_failure_time = now

    if self._rapid_failures >= self._MAX_RAPID_FAILURES:
        logger.warning("Rapid failures — backing off for 60s then retrying")
        self._state = StreamState.RECONNECTING
        # Instead of giving up, schedule a delayed retry
        threading.Timer(60.0, self._delayed_reconnect).start()
        return

    self._state = StreamState.RECONNECTING
```

**Priority:** P1 — Prevents permanent stream loss during transient issues.

---

### VUL-06: No Redis Connection Pooling [MEDIUM]

**Location:** `shared/redis_client.py:24-30`

**Root Cause:** Every call to `get_redis_client()` creates a new `redis.Redis()` instance, which internally creates a new connection pool. Since this is called frequently (every publish, every health check, every query), it creates excessive connection churn.

**Impact:** Under load, multiple parallel Redis operations create redundant connections. While redis-py handles this internally better than raw TCP, it still causes unnecessary overhead and can hit Redis's `maxclients` limit.

**Recommended Fix:**
```python
# shared/redis_client.py — use module-level singleton with connection pool
import redis

_client = None
_client_lock = threading.Lock()

def get_redis_client() -> redis.Redis:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = redis.Redis(
                    host=REDIS_HOST,
                    port=REDIS_PORT,
                    decode_responses=True,
                    socket_timeout=5,
                    socket_connect_timeout=5,
                    retry_on_timeout=True,
                    health_check_interval=30,
                )
    return _client
```

**Priority:** P2 — Performance improvement, not a crash risk.

---

### VUL-07: QuestDB JVM Crash (GraalVM WSL2 Bug) [CRITICAL]

**Location:** `docker-compose.yml` (QuestDB service configuration)

**Root Cause:** QuestDB uses GraalVM's JVMCI compiler which has a known incompatibility with WSL2's memory management. Under load (many concurrent queries during signal pipeline execution), the JVM segfaults and QuestDB crashes.

**Evidence:** Crash at 09:31 ET today during first signal generation pipeline. All 3 Captain processes lost database connectivity simultaneously.

**Recommended Fix:**
```yaml
# docker-compose.yml — add JVM flag to disable problematic compiler
questdb:
  image: questdb/questdb:latest
  environment:
    QDB_CAIRO_COMMIT_LAG: 1000
    QDB_LINE_TCP_ENABLED: "true"
    JAVA_TOOL_OPTIONS: "-XX:-UseJVMCICompiler"    # <-- ADD THIS
```

**Priority:** P0 — Fix immediately. This is the #1 cause of system-wide outages.

---

### VUL-08: Captain Command TSM Duplicate Linking [FIXED]

**Location:** `captain-command/captain_command/main.py:255-264`

**Root Cause:** On restart, the TSM auto-linking code ran without checking if the account was already linked, creating duplicate D08 entries. This caused the uvicorn server to fail to start because the TSM init blocked the event loop.

**Status:** FIXED on 2026-03-24 (observation #1796). Skip logic added to prevent re-linking on restart.

**Remaining Risk:** The fix prevents the immediate crash, but the 10 duplicate TSM entries in D08 from the original incident still exist. These should be cleaned up.

**Recommended Cleanup:**
```sql
-- Run against QuestDB to deduplicate D08
-- First verify: SELECT * FROM p3_d08_tsm_state ORDER BY timestamp;
-- Then delete duplicates (keep latest per account_id)
```

**Priority:** P3 — Cleanup task, not blocking.

---

### VUL-09: GUI WebSocket Gives Up After 30 Attempts [LOW]

**Location:** `captain-gui/src/ws/useWebSocket.ts:7-10`

**Root Cause:** The GUI WebSocket client uses exponential backoff from 2s to 30s max, with a hard limit of 30 reconnect attempts. After 30 failures (worst case: 30 × 30s = 15 minutes), the GUI permanently stops trying to reconnect.

**Impact:** If the backend is down for >15 minutes (e.g., during a Docker rebuild + restart), the GUI will show "WebSocket disconnected" with 10s REST polling fallback, but the user must manually refresh the page to re-establish the WebSocket.

**Recommended Fix:**
```typescript
// useWebSocket.ts — infinite reconnect with cap
const MAX_RECONNECT_ATTEMPTS = Infinity;  // Never give up
const RECONNECT_MAX_MS = 30_000;          // Keep 30s cap

// OR: add a periodic "liveness probe" that resets retries
// if REST /api/health returns 200, reset _retries = 0 and reconnect
```

**Priority:** P3 — REST fallback provides adequate coverage.

---

### VUL-10: TopstepX REST No Retry Logic [MEDIUM]

**Location:** `shared/topstep_client.py:354-360`

**Root Cause:** All TopstepX REST API calls have a 15-second timeout but no automatic retry on failure. A single network hiccup during `get_bars()` (used by B1 Data Ingestion for price fallback) causes the entire data ingestion to return None, which propagates through the signal pipeline as missing data.

**Impact:** Signal quality degradation. If the REST fallback for latest price fails AND the MarketStream cache is stale, B1 returns no price for that asset, and it gets skipped for the session.

**Recommended Fix:**
```python
# shared/topstep_client.py — add retry decorator
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def _post(self, endpoint: str, payload: dict, **kwargs) -> dict:
    # existing implementation
    ...
```

**Priority:** P1 — Prevents signal generation failures from transient API issues.

---

### VUL-11: Nginx No Health Check for GUI Container [LOW]

**Location:** `docker-compose.yml` (nginx depends_on captain-gui)

**Root Cause:** Nginx depends on `captain-gui` but without a health check condition. The GUI container copies built files to a shared volume and exits. If the copy fails or takes longer than expected, Nginx starts serving stale or incomplete files.

**Impact:** Users may see a broken or outdated GUI after deployment. Requires manual Nginx restart.

**Recommended Fix:**
```yaml
# docker-compose.yml
captain-gui:
  build: ./captain-gui
  volumes:
    - gui-dist:/gui-dist
  restart: "no"
  healthcheck:
    test: ["CMD", "test", "-f", "/gui-dist/index.html"]
    interval: 5s
    timeout: 3s
    retries: 10
    start_period: 120s  # Allow time for npm build

nginx:
  depends_on:
    captain-command:
      condition: service_healthy
    captain-gui:
      condition: service_healthy  # NOW waits for GUI files
```

**Priority:** P3 — Only affects deployment, not runtime stability.

---

### VUL-12: Health Check Only Validates QuestDB (Not Redis) [MEDIUM]

**Location:** Captain Offline and Captain Online Dockerfiles (lines 20-22)

**Root Cause:** The Docker health check for Captain Offline and Captain Online only tests QuestDB connectivity:
```
CMD python -c "import psycopg2; c=psycopg2.connect(host='questdb',...); c.close()"
```
It does NOT test Redis. If Redis goes down but QuestDB is fine, Docker still reports the container as "healthy" even though the Redis listener thread may be dead and the feedback loop broken.

**Impact:** Docker won't restart the container when Redis connectivity is lost. The process continues running but cannot receive or send messages, leading to silent degradation.

**Recommended Fix:**
```dockerfile
# Offline + Online Dockerfiles — check BOTH services
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python -c "\
import psycopg2, redis; \
c=psycopg2.connect(host='questdb',port=8812,user='admin',password='quest',dbname='qdb'); c.close(); \
r=redis.Redis(host='redis',port=6379); r.ping()" || exit 1
```

**Priority:** P1 — Enables Docker to auto-restart on Redis failures.

---

## Remediation Priority Matrix

| Priority | Vulnerability | Effort | Impact |
|----------|--------------|--------|--------|
| **P0** | VUL-07: QuestDB JVM crash (add `-XX:-UseJVMCICompiler`) | 1 line | Eliminates #1 outage cause |
| **P0** | VUL-01: QuestDB connection pooling | ~30 lines | Prevents connection exhaustion |
| **P0** | VUL-02: QuestDB query timeout | ~3 lines | Prevents thread hangs |
| **P0** | VUL-04: Redis listener retry loop | ~15 lines/process | Prevents silent degradation |
| **P1** | VUL-03: Redis pub/sub delivery guarantee | ~50 lines | Prevents lost signals/outcomes |
| **P1** | VUL-05: TopstepX WS rapid-failure fix | ~20 lines | Prevents permanent stream loss |
| **P1** | VUL-10: TopstepX REST retry logic | ~10 lines | Prevents signal generation failures |
| **P1** | VUL-12: Health check validates both services | ~3 lines/Dockerfile | Enables auto-recovery |
| **P2** | VUL-06: Redis connection pooling | ~15 lines | Performance improvement |
| **P3** | VUL-08: TSM duplicate cleanup | Manual SQL | Data hygiene |
| **P3** | VUL-09: GUI infinite reconnect | ~2 lines | Better UX during outages |
| **P3** | VUL-11: Nginx GUI health check | ~8 lines YAML | Deployment reliability |

---

## Recommended Implementation Order

### Phase 1: Immediate (before next market session)
1. Add `JAVA_TOOL_OPTIONS: "-XX:-UseJVMCICompiler"` to docker-compose.yml (VUL-07)
2. Add `connect_timeout=5` and `statement_timeout=15000` to QuestDB client (VUL-02)
3. Add retry loop to Captain Offline and Online Redis listeners (VUL-04)

### Phase 2: This week
4. Implement QuestDB connection pooling via `psycopg2.pool.ThreadedConnectionPool` (VUL-01)
5. Add `tenacity` retry decorator to TopstepX REST client (VUL-10)
6. Fix TopstepX WS rapid-failure to use delayed retry instead of surrender (VUL-05)
7. Add Redis health check to Offline/Online Dockerfiles (VUL-12)

### Phase 3: Before live trading
8. Migrate critical Redis channels to Redis Streams with consumer groups (VUL-03)
9. Implement Redis connection singleton with health checks (VUL-06)

### Phase 4: Polish
10. GUI infinite reconnect (VUL-09)
11. Nginx GUI health check (VUL-11)
12. TSM duplicate data cleanup (VUL-08)

---

## Signal Flow — Complete Data Path

```
┌─────────────────────────── SIGNAL GENERATION ───────────────────────────┐
│                                                                         │
│  Session opens (NY 9:30 / LON 3:00 / APAC 20:00)                       │
│       │                                                                 │
│       ▼                                                                 │
│  B1: Data Ingestion                                                     │
│  ├─ QuestDB: READ p3_d00 (active assets), p3_d05 (EWMA), p3_d12 (Kelly)│
│  ├─ MarketStream cache: latest price (sub-second)                       │
│  ├─ TopstepX REST fallback: 1-min bars (15s timeout)  [VUL-10]         │
│  └─ Computes 220 features across all eligible assets                    │
│       │                                                                 │
│       ▼                                                                 │
│  B2: Regime Probability → B3: AIM Aggregation → B4: Kelly Sizing        │
│  ├─ QuestDB: READ regime states, AIM weights, Kelly parameters          │
│  └─ Each query: NEW TCP connection, no pool [VUL-01], no timeout [VUL-02]│
│       │                                                                 │
│       ▼                                                                 │
│  B5: Trade Selection → B5B: Quality Gate → B6: Signal Output            │
│  ├─ QuestDB: READ circuit breaker states, quality thresholds            │
│  └─ Redis PUBLISH captain:signals:{uid} [VUL-03: fire-and-forget]       │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────── SIGNAL ROUTING ──────────────────────────────┐
│                                                                         │
│  captain:signals:{uid}  ──Redis──►  Captain Command Orchestrator        │
│       │                                [VUL-04: listener may be dead]    │
│       ├──► GUI push (WebSocket) → Browser [VUL-09: max 30 retries]      │
│       ├──► Telegram notification                                        │
│       └──► Auto-Execute handler (if enabled)                            │
│              │                                                          │
│              ▼                                                          │
│        TopstepX Adapter.send_signal()                                   │
│        ├─ Market entry order (REST, 15s timeout) [VUL-10]               │
│        ├─ Stop loss order                                               │
│        └─ Take profit order                                             │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────── POSITION MONITORING ─────────────────────────┐
│                                                                         │
│  Captain Command publishes TAKEN on captain:commands                     │
│       │                                                                 │
│       ▼                                                                 │
│  Captain Online Command Listener (daemon thread) [VUL-04]               │
│       │                                                                 │
│       ▼                                                                 │
│  B7: Position Monitor (continuous, in session loop)                     │
│  ├─ MarketStream cache: live price [VUL-05: may stop reconnecting]      │
│  ├─ Check TP/SL/time-exit                                               │
│  └─ On exit: resolve_position()                                         │
│       ├─ QuestDB: WRITE p3_d03 (outcome), p3_d16 (capital), p3_d23 (CB) │
│       └─ Redis PUBLISH captain:trade_outcomes [VUL-03]                  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────── LEARNING FEEDBACK ───────────────────────────┐
│                                                                         │
│  captain:trade_outcomes ──Redis──► Captain Offline Redis Listener        │
│       [VUL-03: no delivery guarantee] [VUL-04: listener may die]        │
│       │                                                                 │
│       ▼                                                                 │
│  _handle_trade_outcome()                                                │
│  ├─ DMA update → QuestDB p3_d02                                        │
│  ├─ BOCPD/CUSUM → QuestDB p3_d04                                       │
│  ├─ Level escalation → Redis captain:alerts (if Level ≥ 3)             │
│  ├─ Kelly update → QuestDB p3_d12                                       │
│  ├─ CB params → QuestDB p3_d25                                         │
│  └─ Checkpoint → SQLite WAL journal                                     │
│                                                                         │
│  Next session reads updated parameters → signal quality improves        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Docker Network Topology

```
┌──────────────────────── Docker Default Bridge ────────────────────────┐
│                                                                       │
│   127.0.0.1:80 ──► nginx ──► captain-command:8000                     │
│                      │                                                │
│                      └──► gui-dist volume (SPA files)                 │
│                                                                       │
│   captain-command ◄──depends──► questdb (healthy)                     │
│                    ◄──depends──► redis (healthy)                      │
│                                                                       │
│   captain-online  ◄──depends──► questdb (healthy)                     │
│                    ◄──depends──► redis (healthy)                      │
│                                                                       │
│   captain-offline ◄──depends──► questdb (healthy)                     │
│                    ◄──depends──► redis (healthy)                      │
│                                                                       │
│   All ports bound to 127.0.0.1 (localhost only)                       │
│   No explicit network defined (uses default bridge)                   │
│                                                                       │
│   Memory limits (local):                                              │
│   ├─ captain-online:  2GB limit, 768MB reserve                        │
│   ├─ captain-offline: 1.5GB limit, 512MB reserve                      │
│   ├─ captain-command: 768MB limit, 256MB reserve                      │
│   └─ nginx:           128MB limit, 32MB reserve                       │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

---

*Generated 2026-03-24 by deep system analysis across 6 parallel research agents examining all service entry points, connection modules, Docker configuration, and GUI connectivity.*
