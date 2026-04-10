<!-- AUDIT-META
skill: ln-641-pattern-analyzer
pattern: Pub/Sub Messaging
score: 6.6
score_compliance: 72
score_completeness: 68
score_quality: 74
score_implementation: 70
issues_critical: 1
issues_high: 3
issues_medium: 4
issues_low: 2
files_analyzed: 12
-->

# Pattern Analysis: Pub/Sub Messaging

**Audit Date:** 2026-04-09
**Score:** 6.6/10 (C:72 K:68 Q:74 I:70) | Issues: 10 (Crit:1 H:3 M:4 L:2)

## Architecture

Two-tier messaging:
- **Redis Streams** (durable): `stream:signals`, `stream:trade_outcomes`, `stream:commands`, `stream:signal_outcomes`
- **Redis Pub/Sub** (fire-and-forget): `captain:alerts`, `captain:status`

## Checks

| Check | Score | Evidence |
|---|---|---|
| compliance_check | 72/100 | Centralized constants; consistent naming; `default=str` serialization; scripts bypass streams via old pub/sub paths |
| completeness_check | 68/100 | Consumer groups with ACK on critical streams; trade outcome 3-retry; no XPENDING recovery; no DLQ |
| quality_check | 74/100 | Clean DI via callables; strict API sanitization boundary; no inbound schema validation |
| implementation_check | 70/100 | Thread-safe singleton; exponential backoff; no stream lag monitoring; test tools broken against current architecture |

## Findings

| # | Severity | Category | File:Line | Issue | Suggestion | Effort |
|---|---|---|---|---|---|---|
| CP-01 | CRITICAL | completeness | All orchestrators | No XPENDING/XCLAIM recovery — crash between handler and ACK permanently loses messages | Add XPENDING recovery at startup: claim messages older than 60s TTL and reprocess | M |
| Q-02 | HIGH | quality | `b1_core_routing.py:277` | `MANUAL_HALT`/`MANUAL_RESUME` uses `client.publish(CH_COMMANDS)` — Online reads `STREAM_COMMANDS` only | Change to `publish_to_stream(STREAM_COMMANDS, ...)` | S |
| C-03 | HIGH | compliance | `inject_test_signal.py:122`, `paper_trader.py:293,350` | Scripts publish to old pub/sub channels ignored by production consumers | Update to use `publish_to_stream()` | S |
| CP-02 | HIGH | completeness | All stream reader loops | No dead-letter queue — malformed message causes infinite poison-pill replay loop | ACK bad messages and log to error stream | M |
| I-01 | MEDIUM | implementation | N/A | No stream lag monitoring (XLEN vs acknowledged position) | Add periodic XLEN check; alert when backlog > threshold | M |
| Q-01 | MEDIUM | quality | All stream handlers | No inbound message schema validation — `data.get(key)` with no required-field checks | Add required-field validation at handler entry | S |
| I-02 | MEDIUM | implementation | N/A | No watchdog monitoring stream reader thread liveness | Monitor daemon threads; publish CRITICAL alert if dead | M |
| CP-03 | MEDIUM | completeness | `command/orchestrator.py:33` | `CH_TRADE_OUTCOMES` imported but never subscribed to — dead import | Remove unused import | S |
| Q-03 | LOW | quality | `b6_signal_output.py:271` | Signal publish has single-try — critical path should have at least one retry | Add 1-retry with backoff for signal delivery | S |
| I-03 | LOW | implementation | Offline orchestrator | Sequential polling of 3 streams (500ms + 1000ms + 2000ms blocks) serializes reads | Use separate threads per stream or shorter block times | M |

<!-- DATA-EXTENDED
{
  "pattern": "Pub/Sub Messaging",
  "gaps": {
    "missingComponents": [
      "No XPENDING recovery on startup (messages lost on crash)",
      "No dead-letter queue (poison pill vulnerability)",
      "No stream backlog monitoring",
      "No message schema validation"
    ],
    "inconsistencies": [
      "MANUAL_HALT published via pub/sub but Online only reads streams",
      "inject_test_signal.py and paper_trader.py use deprecated pub/sub channels",
      "CH_TRADE_OUTCOMES imported in Command but never used"
    ]
  }
}
-->
