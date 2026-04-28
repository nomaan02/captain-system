Below is an issues log where ive extracted causes for concerns from the 
'replay_full_pipeline.py' script that tests the full captain pipeline flow 
e2e before live tarding to ensure all computations are completed correctly.

ISSUE_1:

- Data missing for asset timezone offset - unsure what this refers to or how big of an issue it is but it is a flag

[REPLAY] 21:42:14 WARNING captain_online.blocks.b1_data_ingestion: Incident INC-41B9B94D created: [P2_HIGH] DATA_QUALITY — Data for ZB missing timezone offset. Rejecting.
[REPLAY] 21:42:14 WARNING captain_online.blocks.b1_data_ingestion: Incident INC-CAB03D00 created: [P2_HIGH] DATA_QUALITY — Data for M2K missing timezone offset. Rejecting.
[REPLAY] 21:42:14 WARNING captain_online.blocks.b1_data_ingestion: Incident INC-BB17BF88 created: [P2_HIGH] DATA_QUALITY — Data for MES missing timezone offset. Rejecting.
[REPLAY] 21:42:14 WARNING captain_online.blocks.b1_data_ingestion: Incident INC-6CAF432E created: [P2_HIGH] DATA_QUALITY — Data for MNQ missing timezone offset. Rejecting.
[REPLAY] 21:42:14 WARNING captain_online.blocks.b1_data_ingestion: Incident INC-36B5EB40 created: [P2_HIGH] DATA_QUALITY — Data for MYM missing timezone offset. Rejecting.
[REPLAY] 21:42:14 WARNING captain_online.blocks.b1_data_ingestion: Incident INC-1D337970 created: [P2_HIGH] DATA_QUALITY — Data for NQ missing timezone offset. Rejecting.
[REPLAY] 21:42:14 WARNING captain_online.blocks.b1_data_ingestion: Incident INC-6D9219F7 created: [P2_HIGH] DATA_QUALITY — Data for ZN missing timezone offset. Rejecting.
[REPLAY] 21:42:14 WARNING captain_online.blocks.b1_data_ingestion: Incident INC-04040481 created: [P2_HIGH] DATA_QUALITY — Data for ES missing timezone offset. Rejecting.


-----------------------


ISSUE_2:

is the circuit breaker behaving correctly and within bounds? it seems to be blockign everything but i am unsure: 

[REPLAY] 21:28:24 INFO captain_online.blocks.b5b_quality_gate: ON-B5B: Quality gate for user primary_user: 5 recommended, 0 below threshold
[REPLAY] 21:28:24 INFO replay: B5B: 5 recommended, 0 below threshold
[REPLAY] 21:28:24 INFO captain_online.blocks.b5c_circuit_breaker: ON-B5C: CB blocked MNQ for account 20319784: L1: preemptive halt — |L_t|=0 + rho_j=1004 = 1004 >= L_halt=750
[REPLAY] 21:28:24 INFO captain_online.blocks.b5c_circuit_breaker: ON-B5C: CB blocked MES for account 20319784: L1: preemptive halt — |L_t|=0 + rho_j=2208 = 2208 >= L_halt=750
[REPLAY] 21:28:24 INFO captain_online.blocks.b5c_circuit_breaker: ON-B5C: CB blocked M2K for account 20319784: L1: preemptive halt — |L_t|=0 + rho_j=1825 = 1825 >= L_halt=750
[REPLAY] 21:28:24 INFO captain_online.blocks.b5c_circuit_breaker: ON-B5C: CB blocked MYM for account 20319784: L1: preemptive halt — |L_t|=0 + rho_j=811 = 811 >= L_halt=750
[REPLAY] 21:28:24 INFO captain_online.blocks.b5c_circuit_breaker: ON-B5C: Circuit breaker blocked 4 account-asset pairs


-----------------------


ISSUE_3***:

I've just pasted the first few lines as it is the same across all of the rest of the assets for this section aswell but the OR doesn't seem to be computing and is resolving to 0.000 for every asset. The hihg and the low from the opening range seem to be recording as exactly the same value so there is actually no opening range defined? this seems like a very serious backend error and I'd highlight this as the most critical one so far.

REPLAY] 21:28:24 INFO replay: ============================================================
[REPLAY] 21:28:24 INFO replay: REPLAYING TICKS — OR detection active
[REPLAY] 21:28:24 INFO replay: ============================================================
[REPLAY] 21:28:24 INFO captain_online.blocks.b8_or_tracker: OR FORMING: ES — first tick 7070.5000 at 16:28:24.196678
[REPLAY] 21:28:24 INFO captain_online.blocks.b8_or_tracker: OR COMPLETE: ES — high=7070.5000 low=7070.5000 range=0.0000 (1 ticks)
[REPLAY] 21:28:24 INFO captain_online.blocks.b8_or_tracker: OR BREAKOUT SHORT: ES — price=7067.5000 < OR low=7070.5000, or_range=0.0000
[REPLAY] 21:28:24 INFO replay: *** OR BREAKOUT: ES SHORT at 7067.50 (range=0.0000) at 09:25:00 ET ***
[REPLAY] 21:28:24 INFO captain_online.blocks.b8_or_tracker: OR FORMING: MES — first tick 7070.5000 at 16:28:24.196962
[REPLAY] 21:28:24 INFO captain_online.blocks.b8_or_tracker: OR COMPLETE: MES — high=7070.5000 low=7070.5000 range=0.0000 (1 ticks)
[REPLAY] 21:28:24 INFO captain_online.blocks.b8_or_tracker: OR BREAKOUT SHORT: MES — price=7067.7500 < OR low=7070.5000, or_range=0.0000
[REPLAY] 21:28:24 INFO replay: *** OR BREAKOUT: MES SHORT at 7067.75 (range=0.0000) at 09:25:00 ET ***
[REPLAY] 21:28:24 INFO captain_online.blocks.b8_or_tracker: OR FORMING: NQ — first tick 26419.2500 at 16:28:24.197131
[REPLAY] 21:28:24 INFO captain_online.blocks.b8_or_tracker: OR COMPLETE: NQ — high=26419.2500 low=26419.2500 range=0.0000 (1 ticks)
[REPLAY] 21:28:24 INFO captain_online.blocks.b8_or_tracker: OR BREAKOUT SHORT: NQ — price=26400.2500 < OR low=26419.2500, or_range=0.0000


-----------------------


ISSUE_4:

the generated signals following seem to all place and go through but with no OR - i dont know how the actual TP and SL size is resolved as there is not actually a number there? 

[REPLAY] 21:42:27 INFO replay: ============================================================
[REPLAY] 21:42:27 INFO replay: PHASE B: Generating signals for 8 resolved assets
[REPLAY] 21:42:27 INFO replay: ============================================================
[REPLAY] 21:42:27 INFO captain_online.blocks.b1_features: Stored opening volume for NQ: 14769 contracts in first 15 min
[REPLAY] 21:42:27 INFO replay: AIM-15 Phase B (replay) for NQ: or_vol=14769, hist_avg=12948, ratio=1.14, mod=1.05, combined 0.983->1.032
[REPLAY] 21:42:27 INFO replay: PHASE B: Running B6 for NQ — direction=SHORT, entry=25662.50, or_range=0.00
[REPLAY] 21:42:27 WARNING captain_online.blocks.b6_signal_output: ON-B6: Skipping ES — no breakout direction resolved (or_direction=None, default_direction=0)
[REPLAY] 21:42:27 INFO captain_online.blocks.b6_signal_output: ON-B6: 0 signals published for user primary_user (session 1), 0 below threshold
[REPLAY] 21:42:27 INFO replay: B6: Published 0 signals to Redis
[REPLAY] 21:42:27 INFO captain_online.blocks.b1_features: Stored opening volume for MNQ: 43157 contracts in first 15 min
[REPLAY] 21:42:27 INFO replay: AIM-15 Phase B (replay) for MNQ: or_vol=43157, hist_avg=37792, ratio=1.14, mod=1.05, combined 0.983->1.032
[REPLAY] 21:42:27 INFO replay: PHASE B: Running B6 for MNQ — direction=SHORT, entry=25662.75, or_range=0.00
[REPLAY] 21:42:27 WARNING captain_online.blocks.b6_signal_output: ON-B6: Skipping ES — no breakout direction resolved (or_direction=None, default_direction=0)
[REPLAY] 21:42:27 INFO captain_online.blocks.b6_signal_output: ON-B6: 0 signals published for user primary_user (session 1), 0 below threshold
[REPLAY] 21:42:27 INFO replay: B6: Published 0 signals to Redis
[REPLAY] 21:42:27 INFO captain_online.blocks.b1_features: Stored opening volume for ES: 38588 contracts in first 15 min
[REPLAY] 21:42:27 INFO replay: AIM-15 Phase B (replay) for ES: or_vol=38588, hist_avg=35583, ratio=1.08, mod=1.05, combined 0.983->1.032
[REPLAY] 21:42:27 INFO replay: PHASE B: Running B6 for ES — direction=SHORT, entry=6940.25, or_range=0.00
[REPLAY] 21:42:27 INFO captain_online.blocks.b6_signal_output: ON-B6: 1 signals published for user primary_user (session 1), 0 below threshold
[REPLAY] 21:42:27 INFO replay: B6: Published 1 signals to Redis


-----------------------

ISSUE_05:

from there there seems to be a recurring logging error that presents itself in this sequence for every asset afterwards:

[REPLAY] 21:42:27 INFO captain_online.blocks.b1_features: Stored opening volume for ES: 38588 contracts in first 15 min
[REPLAY] 21:42:27 INFO replay: AIM-15 Phase B (replay) for ES: or_vol=38588, hist_avg=35583, ratio=1.08, mod=1.05, combined 0.983->1.032
[REPLAY] 21:42:27 INFO replay: PHASE B: Running B6 for ES — direction=SHORT, entry=6940.25, or_range=0.00
[REPLAY] 21:42:27 INFO captain_online.blocks.b6_signal_output: ON-B6: 1 signals published for user primary_user (session 1), 0 below threshold
[REPLAY] 21:42:27 INFO replay: B6: Published 1 signals to Redis
--- Logging error ---
Traceback (most recent call last):
  File "/usr/lib/python3.12/logging/__init__.py", line 1160, in emit
    msg = self.format(record)
          ^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.12/logging/__init__.py", line 999, in format
    return fmt.format(record)
           ^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.12/logging/__init__.py", line 703, in format
    record.message = record.getMessage()
                     ^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.12/logging/__init__.py", line 392, in getMessage
    msg = msg % self.args
          ~~~~^~~~~~~~~~~
TypeError: must be real number, not NoneType
Call stack:
  File "/home/isaac/captain-system/scripts/replay_full_pipeline.py", line 619, in <module>
    main()
  File "/home/isaac/captain-system/scripts/replay_full_pipeline.py", line 615, in main
    run_replay(target, args.session)
  File "/home/isaac/captain-system/scripts/replay_full_pipeline.py", line 587, in run_replay
    run_phase_b(asset, state_dict, phase_a,
  File "/home/isaac/captain-system/scripts/replay_full_pipeline.py", line 450, in run_phase_b
    logger.info("  SIGNAL: %s %s x%s — TP=%.2f SL=%.2f confidence=%s",
Message: '  SIGNAL: %s %s x%s — TP=%.2f SL=%.2f confidence=%s'
Arguments: (-1, 'ES', 1, None, None, '?')


end:

the replay then finished and ended here:

[REPLAY] 21:42:28 INFO replay: 
[REPLAY] 21:42:28 INFO replay: ============================================================
[REPLAY] 21:42:28 INFO replay: REPLAY COMPLETE
[REPLAY] 21:42:28 INFO replay:   Date: 2026-04-14, Session: NY
[REPLAY] 21:42:28 INFO replay:   Assets with bars: 8
[REPLAY] 21:42:28 INFO replay:   OR breakouts: 8
[REPLAY] 21:42:28 INFO replay:   OR expired: 0
[REPLAY] 21:42:28 INFO replay:   Signals published to Redis → check GUI
[REPLAY] 21:42:28 INFO replay: ============================================================


I am very unconfident with the amount of errors and discrepancies in the replay and would like you to work through them sequentially, either confirming that they are blocks and stages that have knowingly been deferred and wont affect the performance of the captain system for now, or whether they are real errors and need to be changed. I would like you to pay specific attention to error ISSUE_03 as the fact that OR isn't actually being created, critically impacts the performance of the program and the metrics recorded and signals acted on. 

If any of these errors including error 3 are only behaving in the way they are due to the fact that this is a pipeline replay sim, and they would actually not be an issue in the live trading program then flag this.