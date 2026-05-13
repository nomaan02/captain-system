# Captain Offline Spec-vs-Code — audit cache digest

**Stamp:** commit `ef24edf632eba2462527505d28c5a75b133fb612`, ISO `2026-05-12T14:08:20Z`

## Authoritative full audit

**Path:** `docs2/audits/2026-04-22_offline_spec_vs_code_audit.md`  
**Mode stated in doc:** AUDIT ONLY — no code changes  
**Baseline counts (from doc §1):**

| Severity | Count |
|----------|-------|
| BLOCKING | 6 |
| HIGH | 32 |
| MEDIUM | 24 |
| LOW | 17 |
| **Total** | **79** |

## HEAD-verified schema flags (`shared/canonical_schemas.py`)

Module header (~43–67) documents **intentional gaps**:

| ID | Topic | Summary |
|----|-------|---------|
| D21 | `p3_d21_incident_log` | Majority sites use `timestamp`; **one** writer uses `ts` → INSERT mismatch risk until unified |
| D33 | `session_date` | Mixed STRING implicit cast vs TIMESTAMP spec |
| D30/D29 | date columns | Left STRING deliberately |

## Representative BLOCKING IDs (unchanged unless code fixed since 2026-04-22)

From audit doc §3 — **re-verify before treating as closed**:

| ID | Summary |
|----|---------|
| F-01 | AIM-16 HMM training (`b1_aim16_hmm.py`) not wired from offline orchestrator weekly path |
| F-02 | Version snapshots omitted on several D01/D02 writes |
| F-03 | D04 partial INSERT rows break `LATEST ON` composition for BOCPD vs CUSUM |

Full narratives remain **only** in `docs2/audits/2026-04-22_offline_spec_vs_code_audit.md`.

## Instruction for downstream agents

- **ml-agent:** Read §3 findings F-01, F-12–F-19 cluster + AIM/Kelly sections from the full audit file.
- **lead-agent:** Map §3 `F-NN` IDs into `docs/captain-audit/09-KNOWN-ISSUES.md` with severity from source doc.
