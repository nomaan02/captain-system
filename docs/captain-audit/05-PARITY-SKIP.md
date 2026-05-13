# 05 — Parity skip & asset eligibility

**TL;DR**

- **`PARITY_SKIPPED`** is **multi-instance batch routing** — not an asset ban list ([05.1](#051-multi-instance-parity-content-hash)).
- Assets disappear from live sessions when **QuestDB `captain_status`** / **session window** / **data moderator** says so ([05.2](#052-asset-eligibility-not-parity)).
- Audit skips via Command logs + GUI `parity_skipped` websocket payloads.

**Audit stamp:** commit `ef24edf632eba2462527505d28c5a75b133fb612`, `2026-05-12T14:08:20Z`

## 05.1 Multi-instance parity (content hash)

**Analog:** Two airport taxis sharing a dispatcher phone — each fare offer carries an opaque batch code; SHA256 picks **car A vs B**, deterministically, so both dispatchers agree even if SMS arrives twice.

| Topic | Detail |
|-------|--------|
| Env gate | `INSTANCE_PARITY` must be `"0"` or `"1"` — else parity disabled | `orchestrator.py` ~455–457 |
| Key material | `today NY`, `session_id`, `user_id`, **sorted** asset list | `parity.build_parity_key` ~21–44 |
| Decision | `sha256(key)[0] & 1` vs `my_parity` | `parity.compute_parity_decision` ~64–66 |
| Skip behavior | Still pushes GUI route but **`api_route_fn=None`** | `orchestrator.py` ~465–472 |
| Duplicate detection | Redis `SET` `captain:parity_keys_seen:{YYYY-MM-DD}` — second add triggers incident | ~548–567 |

**There is no static CSV of “parity excluded assets.”** Any asset can be skipped when its batch lands on the opposite parity tower.

### 05.1.1 Add/remove parity behavior

| Goal | Action |
|------|--------|
| Disable parity | Unset `INSTANCE_PARITY` or set outside `0/1` |
| Switch tower identity | Change `.env` parity + restart `captain-command` |

Verify env inside container:

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T captain-command printenv INSTANCE_PARITY
```

### 05.1.2 Audit historical parity skips

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml logs captain-command 2>&1 | grep PARITY
```

## 05.2 Asset eligibility (NOT parity)

Excluded / suppressed assets arise from **Online B1**:

| Mechanism | Rule | Code |
|-----------|------|------|
| Status filter | Only `ACTIVE`, `WARM_UP`, `TRAINING_ONLY` | `_load_active_assets` ~73–75 |
| Session filter | Must match `session_hours` | ~77–79 |
| Data moderator | Drops `DATA_HOLD` post moderation | ~491–492 |

Query statuses:

```bash
curl -s -G "http://127.0.0.1:9000/exec" \
  --data-urlencode "query=SELECT DISTINCT captain_status FROM p3_d00_asset_universe"
```

### 05.2.1 Reasoning table — typical exclusions

| Observation | Meaning | Remediation doc |
|-------------|---------|-----------------|
| `captain_status` ∈ {`P1_ELIM`,`P2_ELIM`,`DISABLED`,…} | Business rule removed asset | Update D00 via offline/bootstrap pipelines |
| Session mismatch | Asset not traded this session | Expect NY-only symbols absent at LON open |
| `DATA_HOLD` | Moderator flagged stale/extreme data | Fix upstream feeds / incidents |

## 05.3 Parameters

| name | value | file | line | source-of-truth | rationale |
|------|-------|------|------|-----------------|----------|
| `INSTANCE_PARITY` | `0`/`1`/empty | `captain-command/.../orchestrator.py` | 455 | Env `.env` | Chooses tower |
| Redis seen TTL | `86400 * 2` seconds | `captain-command/.../orchestrator.py` | 552 | Code | Two-day duplicate window |

Cross-links: architecture [01.3](01-ARCHITECTURE-OVERVIEW.md#013-end-to-end-trading-feedback-loop), issues [09](09-KNOWN-ISSUES.md).
