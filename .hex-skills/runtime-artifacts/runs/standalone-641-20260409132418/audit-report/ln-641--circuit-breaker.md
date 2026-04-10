<!-- AUDIT-META
skill: ln-641-pattern-analyzer
pattern: Circuit Breaker
score: 7.7
score_compliance: 78
score_completeness: 72
score_quality: 82
score_implementation: 75
issues_critical: 0
issues_high: 0
issues_medium: 2
issues_low: 3
files_analyzed: 7
-->

# Pattern Analysis: Circuit Breaker

**Audit Date:** 2026-04-09
**Score:** 7.7/10 (C:78 K:72 Q:82 I:75) | Issues: 5 (M:2 L:3)

## Files Analyzed

| File | Purpose |
|---|---|
| `captain-online/.../b5c_circuit_breaker.py` | 7-layer CB evaluation |
| `captain-offline/.../b8_cb_params.py` | Beta_b OLS regression |
| `captain-online/.../orchestrator.py` | CB call site |
| `captain-online/.../b7_position_monitor.py` | D23 intraday writes |
| `captain-command/.../b8_reconciliation.py` | D23 daily reset |
| `tests/test_b5c_circuit.py` | 20 unit tests |

## Checks

| Check | Score | Evidence |
|---|---|---|
| compliance_check | 78/100 | 7 spec layers implemented; cold-start guard correct; beta_b errata applied; L6 stub; VIX threshold duplicated |
| completeness_check | 72/100 | All states computed; D23 written atomically by B7; D23 reset by reconciliation; no Redis alert on trip; model_m not passed to L3/L4 |
| quality_check | 82/100 | No magic numbers in CB math; `DEFAULT_VIX_CB_THRESHOLD` named constant; OLS + significance gate clean; stateless functional model appropriate for domain |
| implementation_check | 75/100 | Pipeline wired; D25 persisted per-account/per-model; D23 intraday reset confirmed; `reset_flag` schema mismatch |

## Findings

| # | Severity | Category | File:Line | Issue | Suggestion | Effort |
|---|---|---|---|---|---|---|
| F-001 | MEDIUM | completeness | `b5c_circuit_breaker.py:137-142` | No Redis alert published on CB trip — high-priority operational event invisible to GUI | Add `publish(CH_ALERTS, ...)` on BLOCKED decision | S |
| F-002 | MEDIUM | implementation | `orchestrator.py:498-511` | `model_m` and `fee_per_trade` not passed — L3/L4 always get `basket_key=None` and `fee=0.0` | Pass `model_m` from AIM context and `fee_per_trade` from D00 specs | S |
| F-003 | LOW | compliance | `orchestrator.py:630` | VIX threshold hardcoded `50.0` bypassing `DEFAULT_VIX_CB_THRESHOLD` constant | Import and use the named constant from b5c | S |
| F-004 | LOW | implementation | `b8_reconciliation.py:428-430` | `reset_flag` column written but absent from D23 table schema in `init_questdb.py` | Remove `reset_flag` from insert or add column to schema | S |
| F-005 | LOW | completeness | `b5c_circuit_breaker.py:574-576` | Layer 6 (`_layer6_manual_override`) is a stub returning False | Document as V1 limitation or implement per-account manual halt | M |

### Positive Findings

- Beta_b errata correctly applied with cold-start significance gate
- Atomic D16+D23 write in B7 prevents split-brain
- Cold-start safe: L3/L4 return None when `n_observations == 0`
- Stateless functional model (no CLOSED/OPEN/HALF_OPEN) is domain-appropriate — session boundaries serve as natural recovery points
- 20 unit tests cover L0-L4 integration paths
- Non-Topstep bypass is explicit and tested

<!-- DATA-EXTENDED
{
  "pattern": "Circuit Breaker",
  "gaps": {
    "missingComponents": [
      "Layer 6 manual override (stub)",
      "Redis alert on CB trip",
      "model_m passthrough to L3/L4"
    ],
    "inconsistencies": [
      "VIX threshold: named constant in b5c vs hardcoded in orchestrator",
      "reset_flag column in reconciliation insert but not in D23 schema"
    ]
  }
}
-->
