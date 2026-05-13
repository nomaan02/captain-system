# 08 — Ops commands cheatsheet

**TL;DR**

- Compose stack always uses **both** YAML files (`docker-compose.yml` + `docker-compose.local.yml`).
- QuestDB ad hoc queries prefer **HTTP `/exec`** from host (QuestDB container lacks `psql`).
- Redis CLI needs password from `.env`.

**Audit stamp:** commit `ef24edf632eba2462527505d28c5a75b133fb612`, `2026-05-12T14:08:20Z`

## 08.1 Compose shorthand

```bash
cd /home/nomaan/captain-system
docker compose -f docker-compose.yml -f docker-compose.local.yml ps
docker compose -f docker-compose.yml -f docker-compose.local.yml logs -f --tail=200 captain-online
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build captain-command
docker compose -f docker-compose.yml -f docker-compose.local.yml restart captain-offline
```

Tower helpers (`dco`, `cap-run`, `cmd-run`) live in workspace rule — mirror those when SSH'd on a tower host.

## 08.2 QuestDB validation queries

```bash
Q='SELECT count() FROM p3_d03_trade_outcome_log'
curl -s -G "http://127.0.0.1:9000/exec" --data-urlencode "query=$Q" | head -c 400

Q2='SELECT asset_id, captain_status FROM p3_d00_asset_universe LATEST ON last_updated PARTITION BY asset_id ORDER BY asset_id'
curl -s -G "http://127.0.0.1:9000/exec" --data-urlencode "query=$Q2"
```

Alternate (`psql` inside captain-command — ships client):

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T captain-command \
  sh -c 'PGPASSWORD=quest psql -h questdb -p 8812 -U admin -d qdb -c "SELECT 1"'
```

## 08.3 Redis checks

```bash
PW=$(grep '^REDIS_PASSWORD=' /home/nomaan/captain-system/.env | cut -d= -f2)
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T redis \
  redis-cli -a "$PW" --no-auth-warning PING
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T redis \
  redis-cli -a "$PW" --no-auth-warning XLEN stream:signals
```

## 08.4 Host-side regression lint

```bash
cd /home/nomaan/captain-system
PYTHONPATH=./:./captain-online:./captain-offline:./captain-command \
  python3 scripts/lint_decimal_boundary.py
```

## 08.5 Config bake reminder (towers)

If `_config/` directories drift during rebuilds, sync before `docker compose build` per `.cursor/rules/captain-deploy-and-tower-discipline.mdc` §2026-05-06 stale-config entry.

## 08.6 Cross-links

Health checklist → [10](10-VALIDATION-CHECKLIST.md). Schema → [02](02-QUESTDB-SCHEMA.md).
