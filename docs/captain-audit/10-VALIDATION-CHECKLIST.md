# 10 — Validation checklist

**TL;DR**

- Ordered checks from **infra → data → streams → processes → trading gates**.
- Run top-to-bottom after deploy or incident.

**Audit stamp:** commit `ef24edf632eba2462527505d28c5a75b133fb612`, `2026-05-12T14:08:20Z`

## 10.1 Compose health

- [ ] `docker compose -f docker-compose.yml -f docker-compose.local.yml ps` — all required services `running` / healthy.
- [ ] `curl -s -o /dev/null -w "%{http_code}\\n" http://127.0.0.1:8000/docs` — expect `200`.

## 10.2 QuestDB

- [ ] HTTP smoke: `curl -s -G "http://127.0.0.1:9000/exec" --data-urlencode "query=SELECT 1"` returns dataset.
- [ ] Asset universe rows: query in [08.2](08-OPS-COMMANDS.md#082-questdb-validation-queries).

## 10.3 Redis

- [ ] `PING` OK ([08.3](08-OPS-COMMANDS.md#083-redis-checks)).
- [ ] Consumer group exists for signals: `XINFO GROUPS stream:signals`.

## 10.4 Processes / logs

- [ ] Online heartbeat / session traces: `logs captain-online | grep ON-B1 | tail`.
- [ ] Offline scheduler banner present after 16:00 ET window (or temporarily adjust clock on dev): see [06.1](06-SCHEDULED-TASKS.md#061-offline-orchestrator-scheduler).
- [ ] Command stream reader consuming: log lines containing `Signal batch received`.

## 10.5 Configuration & safety gates

- [ ] `AUTO_EXECUTE` matches intention (`captain-command` env) — verify via `printenv AUTO_EXECUTE` inside container.
- [ ] `INSTANCE_PARITY` correctly unset or `0/1` ([05.3](05-PARITY-SKIP.md#053-parameters)).
- [ ] Compliance JSON readable inside container ([04.5](04-TRADE-LOGIC.md#045-compliance-gates)).

## 10.6 Broker connectivity

- [ ] Adapter ping path logged from `b3_api_adapter` / Topstep client — inspect `captain-command` logs for auth failures.

## 10.7 Regression lint (host)

- [ ] `python3 scripts/lint_decimal_boundary.py` passes ([08.4](08-OPS-COMMANDS.md#084-host-side-regression-lint)).

## 10.8 Audit artefacts fresh

- [ ] `.audit-cache/README.md` commit hash matches `git rev-parse HEAD`.

---

When everything passes, record timestamp + operator in operator log.
