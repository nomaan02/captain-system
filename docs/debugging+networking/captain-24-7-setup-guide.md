# Running a 24/7 Docker trading system on WSL 2

**Your "Captain" trading engine can run reliably on Windows 11 Home + WSL 2 during market hours — but only with aggressive power management lockdown, a switch from signalrcore to pysignalr, and hardened Docker Compose configuration.** The single biggest risk is Windows sleep/hibernation silently killing your WSL 2 VM mid-session. The second biggest risk is signalrcore's known socket-closing bugs dropping your TopstepX WebSocket during volatile markets. Both are solvable. This report covers every configuration change needed, with copy-paste-ready commands and YAML throughout.

The core constraint — TopstepX prohibiting VPS hosting — means your 16GB Manchester machine must be both development workstation and production server. That tension shapes every recommendation below: defense-in-depth at the OS layer, the right SignalR library for resilience, and a Docker workflow that lets you push code changes without killing live WebSocket streams.

---

## WSL 2 will work for market hours, but sleep is a showstopper

WSL 2 has **well-documented, severe issues** with sleep and hibernation cycles. GitHub issues #8696, #8763, #9563, and #14005 (December 2024) confirm that WSL 2 enters an unrecoverable "zombie running" state after sleep/wake — services appear running but vsock communication is broken, and only a full reboot fixes it. Issue #5324 documents clock drift after sleep that breaks SSL certificate validation. Docker Desktop compounds this: issue docker/for-win#12981 shows the Docker engine appearing "stuck" after wake.

**Sleep and hibernation must be completely disabled.** Run these commands in an elevated Command Prompt:

```cmd
powercfg /change standby-timeout-ac 0
powercfg /change standby-timeout-dc 0
powercfg -h off
powercfg /ATTRIBUTES SUB_SLEEP SYSTEMREQUIRED -ATTRIB_HIDE
```

The last command unhides the "System unattended sleep timeout" setting, which can trigger sleep even when "Never" is selected. After running it, open Advanced Power Options → Sleep → System unattended sleep timeout → set to **0**. Also set laptop lid close action to "Do nothing" for both battery and plugged-in states via Control Panel → Power Options.

For Windows Update reboots — the other major threat — Windows 11 Home lacks Group Policy Editor, but the same registry keys work:

```reg
[HKEY_LOCAL_MACHINE\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU]
"NoAutoRebootWithLoggedOnUsers"=dword:00000001

[HKEY_LOCAL_MACHINE\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate]
"SetActiveHours"=dword:00000001
"ActiveHoursStart"=dword:00000006
"ActiveHoursEnd"=dword:00000000
```

This sets an **18-hour active window** (06:00–midnight) covering your 14:30–21:00 GMT trading session with generous buffer. The `NoAutoRebootWithLoggedOnUsers` key mirrors the Pro/Enterprise Group Policy and prevents reboot while you're logged in. You can also pause updates for up to 5 weeks during critical trading periods directly from Settings → Windows Update.

### The .wslconfig that keeps Captain alive

```ini
# C:\Users\<YourUsername>\.wslconfig

[wsl2]
memory=10GB
swap=4GB
processors=6
kernelCommandLine=sysctl.vm.max_map_count=262144
vmIdleTimeout=-1
dnsTunneling=true
firewall=true
localhostForwarding=true
guiApplications=false
nestedVirtualization=false

[experimental]
autoMemoryReclaim=gradual
sparseVhd=true
```

The **memory=10GB** allocation gives your 6.6GB Docker stack ~3.4GB headroom for spikes while leaving ~6GB for Windows. The `kernelCommandLine` setting persists **vm.max_map_count=262144** across WSL restarts — this is the recommended approach for QuestDB, superior to `/etc/wsl.conf` boot commands because it applies globally to all WSL distributions including docker-desktop. The `vmIdleTimeout=-1` prevents the WSL 2 VM from auto-shutting down on idle, which is critical since WSL 2 has two separate idle timers (a 15-second instance timer and a 60-second VM timer). Setting `autoMemoryReclaim=gradual` slowly returns unused memory to Windows without the sudden I/O pauses that `dropCache` causes — important for latency-sensitive trading.

**Do not use mirrored networking mode.** Despite its theoretical advantages, issues moby/moby#48201 and microsoft/WSL#10494 document TCP connection stalls and Docker port forwarding failures. Stick with **NAT mode** (the default), which is battle-tested with Docker Desktop.

---

## Replace signalrcore with pysignalr immediately

**signalrcore (v1.0.2) has a critical, acknowledged defect: it is permanently pinned to websocket-client 0.54.0** due to socket-closing bugs the maintainer cannot fix. The README explicitly states: "Issues related with closing socket inherited from websocket-client library. Due to these problems I can't update library to versions higher than websocket-client 0.54.0." For a trading system that needs persistent WebSocket connections through volatile market sessions, this is disqualifying.

Additional signalrcore problems include thread-safety concerns (it uses threading internally via websocket-client, creating race conditions), unresolved issues dating to 2020 (#49: "Application freezed after received message"), and a synchronous architecture that conflicts with FastAPI's asyncio event loop. It is maintained by a solo developer.

**pysignalr (v1.3.0, by baking-bad/dipdup-io) is the clear replacement.** It is a complete ground-up rewrite — not a fork — built natively on asyncio and the modern `websockets` library (v16.x). The `websockets` library provides built-in ping/pong frames every 20 seconds with automatic broken-connection detection, which is exactly what a trading WebSocket needs. pysignalr has seen 4 releases in the last 18 months (1.0.0 through 1.3.0), supports `access_token_factory` for JWT token refresh on reconnection, is fully typed, and is classified as "Production/Stable" on PyPI.

| Criterion | signalrcore 1.0.2 | pysignalr 1.3.0 |
|---|---|---|
| WebSocket library | websocket-client 0.54.0 (pinned, buggy) | websockets 16.x (modern, maintained) |
| Architecture | Synchronous + threading | Native asyncio |
| Keep-alive | Manual interval config | Built-in 20s ping/pong |
| FastAPI compatibility | Blocking calls conflict with event loop | Seamless async integration |
| Token refresh | access_token_factory supported | access_token_factory supported |
| Maintenance | Solo developer, old bugs unresolved | 5 contributors, regular releases |

Migration is straightforward since pysignalr supports the same core concepts (hub connection, `on()` callbacks, `access_token_factory`), but the API is async. For your FastAPI system on Python 3.11, this is an advantage, not a cost.

Note that **Microsoft does not provide an official Python SignalR client** — only JavaScript, .NET, and Java are supported. pysignalr is the best community option. The deprecated `aiosignalrcore` (same team) should be avoided — it was a transitional project and is now archived with a "use pysignalr instead" notice.

---

## tsxapi4py uses signalrcore internally, limiting its value

The tsxapi4py library (github.com/mceesincus/tsxapi4py) uses **signalrcore** as its SignalR transport, confirmed by its requirements.txt and README ("Configured for automatic reconnection attempts by the underlying signalrcore library"). This means adopting tsxapi4py does not solve the WebSocket stability problem — it inherits all of signalrcore's socket-closing bugs and threading issues.

The library is a **single-developer, pre-release project** with no PyPI package (manual installation only), no formal versioning system, and "full packaging for pip installation" listed as a future enhancement. Its `DataStream` and `UserHubStream` classes provide useful abstractions for TopstepX's market and user hubs respectively, but they cannot be used standalone — they require the library's `APIClient` for token management. Token refresh for streams requires manual application intervention: you must call `stream_instance.update_token(new_token)`, which stops the connection, reconfigures the URL, and restarts the stream.

A more mature alternative exists: **project-x-py** (PyPI: `project-x-py`, v1.0.5 / SDK v3.3.4) provides async-based HTTP/2 connections via httpx, a `ProjectXRealtimeClient` with dual-hub SignalR support, deadlock prevention, memory leak protection, and safe token refresh via `update_jwt_token()`. It has documentation on ReadTheDocs and is MIT licensed. However, you should verify which SignalR library it uses internally before adopting it.

**The recommended approach** is to use pysignalr directly with your own thin wrapper around TopstepX's hub URLs and subscription patterns, borrowing the authentication and reconnection patterns from tsxapi4py's source code without depending on the library itself.

---

## TopstepX SignalR connections need specific configuration

TopstepX's SignalR infrastructure lives at two hub endpoints: **`rtc.topstepx.com/hubs/market`** for quotes, trades, and depth data, and **`rtc.topstepx.com/hubs/user`** for account, position, order, and trade events. Authentication uses JWT tokens obtained via `POST /api/Auth/loginKey` with your username and API key. **Tokens are valid for 24 hours** and can be refreshed via `POST /api/Auth/validate` with the current token in the Authorization header.

The correct connection pattern uses **skip_negotiation=True** for direct WebSocket transport, bypassing the initial HTTP negotiate request. This is confirmed by tsxapi4py's implementation, the LobeHub TopStepX documentation, and the project-x-py SDK. The token is passed as a query parameter: `wss://rtc.topstepx.com/hubs/market?access_token=TOKEN`. While this is the standard SignalR pattern, it means tokens appear in server logs — an accepted trade-off given the protocol's design.

For keep-alive, ASP.NET Core SignalR's default server keepalive is **15 seconds**. Set your client's keep_alive_interval to **10–15 seconds** to stay within the server's timeout window and prevent proxy idle-connection kills. With pysignalr, the underlying `websockets` library adds an additional WebSocket-level ping every 20 seconds automatically.

Critical operational constraints to know:

- **Single session per username** — running both the API connection and the TopstepX platform simultaneously causes session conflicts and logout. Start the API connection first, then open TopstepX charts if needed.
- **Rate limits** return HTTP 429. The community-standard configuration uses approximately 60 requests/minute with a burst limit of 10.
- **Re-subscribe after every reconnection** — SignalR does not restore subscriptions automatically. Your reconnection handler must re-subscribe to `GatewayQuote`, `GatewayTrade`, and `GatewayDepth` for each contract ID.
- **Proactive token refresh** — implement a timer to refresh via `/api/Auth/validate` at approximately 20–22 hours, well before the 24-hour expiry. On reconnection, always check token freshness before establishing the new connection.
- **Orders placed via API are final** — they are not eligible for review, adjustment, or reversal by Topstep.

Community resources include the TopstepX-API Discord channel (within Topstep's 169,000+ member Discord server), Swagger docs at `api.topstepx.com/swagger/index.html`, and the ProjectX Gateway documentation at `gateway.docs.projectx.com`. Trustpilot reviews note occasional "API Reconnecting" loops during high-volatility events, reinforcing the need for robust reconnection logic with exponential backoff.

---

## Docker Compose configuration for always-on trading

The following patterns address restart policies, health checks, networking, resource limits, log rotation, and graceful shutdown for your 6-container stack.

**Use `restart: unless-stopped`** for all trading services and `restart: always` for databases. The difference: if you manually `docker stop` a container and the Docker daemon later restarts, `always` resurrects it while `unless-stopped` respects your manual stop. One critical caveat on Windows 11 Home: **Docker Desktop requires a user login to start** — it does not run as a Windows service. Enable "Start Docker Desktop when you sign in" and configure Windows auto-login, or your containers won't restart after an unexpected reboot.

**Always use a custom bridge network** instead of the default. Custom bridge networks provide automatic DNS resolution by service name (the default bridge only supports IP addresses), enable network isolation, and allow inter-container communication without port exposure. For security, use a two-network topology:

```yaml
networks:
  frontend:
    driver: bridge
  backend:
    driver: bridge
    internal: true    # No internet access for backend services

services:
  nginx:
    networks: [frontend]
    ports: ["127.0.0.1:80:80"]
  captain-command:
    networks: [frontend, backend]
  captain-online:
    networks: [backend]
  captain-offline:
    networks: [backend]
  questdb:
    networks: [backend]
  redis:
    networks: [backend]
```

The `internal: true` flag on the backend network blocks QuestDB and Redis from reaching the internet — a significant security improvement. Only captain-command bridges both networks, acting as the gateway between nginx and the backend services.

**Health checks with dependency ordering** ensure containers start in the right sequence and restart when truly unhealthy:

```yaml
services:
  redis:
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 10s
  questdb:
    healthcheck:
      test: ["CMD-SHELL", "wget --no-verbose --tries=1 --spider http://localhost:9003/status || exit 1"]
      interval: 15s
      timeout: 5s
      retries: 5
      start_period: 45s
  captain-command:
    depends_on:
      redis: { condition: service_healthy }
      questdb: { condition: service_healthy }
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
      interval: 15s
      timeout: 5s
      retries: 3
      start_period: 30s
```

**Log rotation is mandatory** — the json-file driver does not rotate by default, and a moderately verbose trading system can generate 50–200MB per day per active container. Without rotation, you'll hit multi-gigabyte logs within weeks:

```yaml
x-logging: &default-logging
  driver: json-file
  options:
    max-size: "25m"
    max-file: "5"
    compress: "true"
```

Apply this anchor to all services. At 25MB × 5 files × 6 containers, your maximum log footprint is ~750MB.

**Resource limits** protect against OOM kills cascading across your system. With your current allocation of 6.6GB across containers on a 10GB WSL allocation:

```yaml
services:
  questdb:
    deploy:
      resources:
        limits: { memory: 2560M, cpus: '2.0' }
        reservations: { memory: 1G, cpus: '1.0' }
  captain-online:
    deploy:
      resources:
        limits: { memory: 2560M, cpus: '1.5' }
        reservations: { memory: 512M, cpus: '0.5' }
  captain-command:
    deploy:
      resources:
        limits: { memory: 1G, cpus: '2.0' }
        reservations: { memory: 512M, cpus: '0.5' }
  captain-offline:
    deploy:
      resources:
        limits: { memory: 2G, cpus: '1.0' }
        reservations: { memory: 256M, cpus: '0.25' }
  redis:
    command: redis-server --requirepass ${REDIS_PASSWORD} --maxmemory 230mb --maxmemory-policy allkeys-lru --appendonly yes
    deploy:
      resources:
        limits: { memory: 256M, cpus: '0.5' }
  nginx:
    deploy:
      resources:
        limits: { memory: 256M, cpus: '0.5' }
```

Set limits slightly above current usage to allow for spikes. When a container hits its memory limit, the kernel OOM-killer sends SIGKILL (exit code 137), and the restart policy recreates it. Do **not** use `oom_kill_disable: true` — it can freeze the entire host.

**Graceful shutdown** requires two things: a long enough `stop_grace_period` (default is only 10 seconds) and proper SIGTERM handling in your Python code. Set QuestDB to 60 seconds (for WAL flush), trading services to 30 seconds, and use FastAPI's lifespan context manager:

```python
@asynccontextmanager
async def lifespan(app):
    yield
    await ws_manager.close_all()      # Close WebSocket connections
    await flush_pending_trades()       # Ensure no in-flight orders are lost
```

Critically, ensure your Python process is PID 1 in the container by using exec-form CMD (`CMD ["uvicorn", "main:app", ...]`), not shell form. Shell form wraps your process in `/bin/sh`, which swallows SIGTERM.

---

## Security is adequate for localhost, but Redis and QuestDB need passwords

Binding all ports to **127.0.0.1** is correct and sufficient for a localhost-only trading system on Docker Desktop. Without this binding, Docker defaults to 0.0.0.0, making services accessible from your LAN. However, several improvements are straightforward:

**Redis must have authentication enabled.** Currently open on the bridge network with no password, any container (or any local process if the port is exposed) can read and write. The fix is a single line: `command: redis-server --requirepass ${REDIS_PASSWORD}`. Store `REDIS_PASSWORD` in your `.env` file (which must be in `.gitignore`).

**QuestDB's default admin:quest credentials** are a medium risk. If the web console port (9000) is not exposed to the host and QuestDB sits on the `internal: true` backend network, the risk is low. If you need the web console during development, bind it to 127.0.0.1 and change the default credentials in QuestDB's `server.conf`.

**JWT tokens in WebSocket URL query strings** are an accepted pattern within SignalR's protocol design — ASP.NET Core SignalR's `accessTokenFactory` passes tokens this way by default. The risk is that tokens appear in server logs and potentially proxy logs. Since your system is localhost-only with no intermediary proxies, the exposure surface is limited to Docker's json-file logs. Enabling log rotation (above) limits how long tokens persist in logs. There is no practical alternative within the SignalR protocol.

**TLS is not needed** for inter-container traffic on a Docker bridge network — this traffic never leaves the host's network namespace. Add TLS only if regulatory compliance requires encryption in transit for all data.

For additional hardening, add these security options to your services:

```yaml
x-security: &default-security
  cap_drop: [ALL]
  security_opt: ["no-new-privileges:true"]
```

This drops all Linux capabilities and prevents privilege escalation. Add back only what each container needs (e.g., `NET_BIND_SERVICE` for nginx). Running containers as a non-root user (`user: "1000:1000"`) provides another layer of isolation.

---

## Development workflow while Captain is live

The key command for making changes without disrupting WebSocket connections in other containers:

```bash
docker compose build captain-command && docker compose up -d --no-deps captain-command
```

The `--no-deps` flag is critical — it prevents Compose from recreating any services that captain-command depends on or that depend on captain-command. The two-step approach (build first, then restart) catches Dockerfile errors before touching the running container. Verify other containers weren't affected by checking uptimes: `docker ps --format "table {{.Names}}\t{{.Status}}"` — all containers except captain-command should show their original uptime.

**Store your source code in the WSL 2 Linux filesystem, not the Windows filesystem.** Docker's official documentation confirms that bind mounts from `/mnt/c/` (Windows files) use the Plan9 file share protocol, which is **3–12x slower** than native Linux filesystem mounts and breaks inotify-based file watching. Clone your repo into `~/projects/` inside WSL and use VS Code's Remote-WSL extension to edit. This gives native-speed volume mounts and reliable `uvicorn --reload` hot-reloading.

Use Docker Compose override files to separate development from production:

```yaml
# docker-compose.override.yml (git-ignored, auto-loaded in dev)
services:
  captain-command:
    build:
      context: ./captain-command
      target: dev
    volumes:
      - ./captain-command/src:/app/src
    command: uvicorn main:app --host 0.0.0.0 --reload --reload-dir /app/src
    environment:
      - LOG_LEVEL=debug
    restart: "no"
```

The base `docker-compose.yml` holds production configuration. The override adds volume mounts, hot-reload, debug logging, and disables auto-restart (so crashes surface immediately in development). For production deployment: `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d` explicitly skips the override.

A multi-stage Dockerfile supports both modes cleanly:

```dockerfile
FROM python:3.11-slim AS deps
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM deps AS dev
# Source code volume-mounted at runtime
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--reload"]

FROM deps AS production
COPY ./src /app/src
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--workers", "2"]
```

For deploying changes during market hours, follow this sequence: tag the current working image (`docker tag captain-command:latest captain-command:pre-deploy`), build the new image, deploy with `--no-deps`, monitor for 5 minutes, and rollback by retagging the old image if anything breaks. **Never deploy to captain-online or any WebSocket-holding container during market hours** unless absolutely necessary — changes to captain-command (the FastAPI/REST layer) are safer since they don't hold the TopstepX SignalR connection.

---

## Conclusion

The highest-impact actions, in priority order: **First**, disable Windows sleep/hibernation and apply the .wslconfig — this eliminates the most common failure mode. **Second**, replace signalrcore with pysignalr in your SignalR connection layer — this eliminates the known socket-closing bugs and gives you native asyncio compatibility with FastAPI. **Third**, add Redis authentication, custom bridge networks with `internal: true`, health checks with dependency ordering, and log rotation — these are straightforward docker-compose.yml changes that prevent cascading failures and disk exhaustion.

The system architecture is sound for its constraints. WSL 2 is not designed as a production server, but with sleep disabled, updates suppressed, and robust application-level reconnection logic, traders in the TopstepX community are running similar setups successfully. Your biggest ongoing risks are Windows forced-update reboots (mitigated by registry settings and Active Hours) and TopstepX server-side instability during high-volatility events (mitigated by exponential-backoff reconnection and re-subscription logic). Build your reconnection handler to assume the connection **will** drop during every session and to recover automatically — this defensive posture makes the specific cause of any drop irrelevant.