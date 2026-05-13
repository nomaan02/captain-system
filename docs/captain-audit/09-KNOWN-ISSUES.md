# 09 — Known issues & drift register

**TL;DR**

- Aggregates **2026-04-22 offline audit BLOCKING/HIGH** IDs still treated open until individually cleared.
- Adds **May 2026** operational/documentation drift discovered during cache generation.
- Empty? **Not applicable** — rows exist; mark resolved inline when fixed.

**Audit stamp:** commit `ef24edf632eba2462527505d28c5a75b133fb612`, `2026-05-12T14:08:20Z`

## 09.1 Severity legend

| Tag | Meaning |
|-----|---------|
| BLOCKING | Safety/architecture break — fix before trusting subsystem |
| HIGH | Silent wrongness / major spec gap |
| MEDIUM | Ops friction / replay-only |
| LOW | Docs/registry hygiene |

## 09.2 Issue register

### 09-I01 — AIM-16 HMM offline driver unwired (spec audit F-01)

| Field | Value |
|-------|-------|
| Severity | BLOCKING |
| Source | `docs2/audits/2026-04-22_offline_spec_vs_code_audit.md` §F-01 |
| Code anchor | `captain-offline/.../b1_aim16_hmm.py` (`train_aim16_hmm`, `save_hmm_state`); weekly scheduler `orchestrator.py` ~1305–1324 calls `run_tier_retrain` only |
| Current state | Trainer implemented; **no caller** in orchestrator path (per April audit; re-verify before closing). |
| Expected | Weekly (or agreed cadence) invocation persists `p3_d26`. |
| Fix sketch | Add `_run_aim16_training` hook + Isaac cadence decision |

### 09-I02 — D04 partial-row INSERT breaks `LATEST ON` fusion (F-03)

| Field | Value |
|-------|-------|
| Severity | BLOCKING |
| Source | F-03 |
| Code anchor | `b2_bocpd.py`, `b2_cusum.py` writers + Kelly reader `b8_kelly_update.py` ~42–52 (per audit) |
| Current state | BOCPD & CUSUM alternate sparse inserts |
| Expected | Single fused row or merged read path |
| Fix sketch | Unified UPSERT or transactional merge |

### 09-I03 — Version snapshots missing on many D01/D02 writes (F-02)

| Field | Value |
|-------|-------|
| Severity | BLOCKING |
| Source | F-02 (`docs2/audits/2026-04-22_offline_spec_vs_code_audit.md`) |
| Current state | Many INSERT paths skip `snapshot_before_update` |
| Expected | Snapshot policy parity with spec |
| Fix sketch | Instrument all writers |

### 09-I04 — Residual offline audit backlog

**Source:** same audit doc §3 — **76 additional findings** beyond I01–I03 remain enumerated there (HIGH/MEDIUM/LOW). Track them as engineering backlog; do not delete the audit file.

### 09-I05 — GUI block registry `sourceFile` paths stale {#09-i05}

| Field | Value |
|-------|-------|
| Severity | LOW |
| Evidence | Registry references `b1_hmm_training.py`; repo contains `b1_aim16_hmm.py` (`captain-gui/src/constants/blockRegistry.js` vs filesystem) |
| Expected | Registry paths match importable modules |
| Fix | Update JSX constants or add alias comments |

### 09-I06 — Redis channel naming drift (modules vs constants)

| Field | Value |
|-------|-------|
| Severity | MEDIUM (documentation / observability) |
| Evidence | `b7_position_monitor.py` module doc ~15 references `captain:trade_outcomes`; runtime publishes `STREAM_TRADE_OUTCOMES` (`shared/redis_client.py` ~78) |
| Expected | Docstrings + runbooks match `stream:trade_outcomes` |

### 09-I07 — Trade audit skill vs bracket-first implementation

| Severity | LOW | Detail | Skill narrative emphasizes 3-order path; code prefers bracket (`b3_api_adapter.py` ~241+) |

### 09-I08 — Canonical schema writer mismatch flags (D21 / D33)

| Severity | MEDIUM | Source | `shared/canonical_schemas.py` header ~50–62 |

### 09-I09 — `/mem-search` path duplication

| Severity | LOW | Memory entries alternate `captain-system/` prefix — confusing for grep tutorials |

## 09.3 Contradiction protocol outcome

**Code wins:** Multi-instance parity uses **content-hash** (`parity.py`, `orchestrator.py` ~508–580), not Redis `INCR` counter described in older captain-trade-audit prose — treat skill text as superseded.

Cross-links: parity detail [05](05-PARITY-SKIP.md), trade enums [04.6](04-TRADE-LOGIC.md#046-bracket-construction).
