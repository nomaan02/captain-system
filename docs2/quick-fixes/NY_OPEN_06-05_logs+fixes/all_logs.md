Isaac-logs:


isaac@captain-tower-2 ~/captain-system (main)> docker compose -f docker-compose.yml -f docker-compose.local.yml logs -f captain-online
captain-online-1 | [ONLINE] 2026-05-06 08:16:07,854 INFO main: Starting Captain Online...
captain-online-1 | [ONLINE] 2026-05-06 08:16:07,872 INFO shared.questdb_client: QuestDB reachable (attempt 1)
captain-online-1 | [ONLINE] 2026-05-06 08:16:07,877 INFO main: Redis: connected
captain-online-1 | [ONLINE] 2026-05-06 08:16:07,877 INFO main: Redis Stream consumer groups initialized
captain-online-1 | [ONLINE] 2026-05-06 08:16:07,891 INFO main: Clean restart — last checkpoint: SHUTDOWN
captain-online-1 | [ONLINE] 2026-05-06 08:16:08,827 INFO shared.topstep_client: TopstepX authenticated as isaach@euphroresources.co.uk (env=LIVE)
captain-online-1 | [ONLINE] 2026-05-06 08:16:08,827 INFO main: TopstepX API: authenticated
captain-online-1 | [ONLINE] 2026-05-06 08:16:08,828 INFO main: Resolved 10 contracts: ['ES', 'MES', 'NQ', 'MNQ', 'M2K', 'MYM', 'NKD', 'MGC', 'ZB', 'ZN']
captain-online-1 | [ONLINE] 2026-05-06 08:16:08,829 INFO pysignalr.transport: State change: disconnected -> connecting
captain-online-1 | [ONLINE] 2026-05-06 08:16:08,830 INFO main: MarketStream STARTED for 10 contracts
captain-online-1 | [ONLINE] 2026-05-06 08:16:08,924 INFO pysignalr.transport: State change: disconnected -> connecting
captain-online-1 | [ONLINE] 2026-05-06 08:16:08,924 INFO main: UserStream STARTED for account 150KTC-V2-478426-52758441 (id=20258288)
captain-online-1 | [ONLINE] 2026-05-06 08:16:08,949 INFO captain_online.blocks.b9_session_controller: Session registry loaded from /captain/config/session_registry.json
captain-online-1 | [ONLINE] 2026-05-06 08:16:08,950 INFO main: Starting session orchestrator...
captain-online-1 | [ONLINE] 2026-05-06 08:16:08,950 INFO captain_online.blocks.orchestrator: Online orchestrator starting...
captain-online-1 | [ONLINE] 2026-05-06 08:16:08,958 INFO captain_online.blocks.orchestrator: Position reconciliation: no positions found in Redis
captain-online-1 | [ONLINE] 2026-05-06 08:16:08,960 INFO captain_online.blocks.orchestrator: Online command stream consumer group ready
captain-online-1 | [ONLINE] 2026-05-06 08:16:09,202 INFO pysignalr.transport: Sending handshake to server
captain-online-1 | [ONLINE] 2026-05-06 08:16:09,203 INFO pysignalr.transport: Awaiting handshake from server
captain-online-1 | [ONLINE] 2026-05-06 08:16:09,288 INFO pysignalr.transport: State change: connecting -> connected
captain-online-1 | [ONLINE] 2026-05-06 08:16:09,288 INFO shared.topstep_stream: MarketStream CONNECTED — subscribing to 10 contract(s)
captain-online-1 | [ONLINE] 2026-05-06 08:16:09,308 INFO pysignalr.transport: Sending handshake to server
captain-online-1 | [ONLINE] 2026-05-06 08:16:09,308 INFO pysignalr.transport: Awaiting handshake from server
captain-online-1 | [ONLINE] 2026-05-06 08:16:09,395 INFO pysignalr.transport: State change: connecting -> connected
captain-online-1 | [ONLINE] 2026-05-06 08:16:09,395 INFO shared.topstep_stream: UserStream CONNECTED — subscribing to account 20258288
captain-online-1 has been recreated
captain-online-1 | [ONLINE] 2026-05-06 09:22:20,537 INFO main: Shutdown signal received
captain-online-1 | [ONLINE] 2026-05-06 09:22:20,537 INFO captain_online.blocks.orchestrator: Online orchestrator stopping...
captain-online-1 | [ONLINE] 2026-05-06 09:22:20,538 INFO shared.topstep_stream: UserStream stopped for account 20258288
captain-online-1 | [ONLINE] 2026-05-06 09:22:20,538 INFO shared.topstep_stream: MarketStream stopped (10 contracts)
captain-online-1 | [ONLINE] 2026-05-06 09:22:20,583 ERROR asyncio: Task was destroyed but it is pending!
captain-online-1 | task: <Task pending name='Task-3' coro=<Connection.keepalive() done, defined at /usr/local/lib/python3.12/site-packages/websockets/asyncio/connection.py:808> wait_for=>
captain-online-1 | [ONLINE] 2026-05-06 09:22:20,584 ERROR asyncio: Task was destroyed but it is pending!
captain-online-1 | task: <Task pending name='Task-6' coro=<Connection.keepalive() done, defined at /usr/local/lib/python3.12/site-packages/websockets/asyncio/connection.py:808> wait_for=>
captain-online-1 | [ONLINE] 2026-05-06 09:22:20,584 ERROR asyncio: Task was destroyed but it is pending!
captain-online-1 | task: <Task pending name='Task-9' coro=<<async_generator_athrow without name>()>>
captain-online-1 | [ONLINE] 2026-05-06 09:22:20,584 ERROR asyncio: Task was destroyed but it is pending!
captain-online-1 | task: <Task pending name='Task-10' coro=<<async_generator_athrow without name>()>>
captain-online-1 exited with code 0
captain-online-1 | [ONLINE] 2026-05-06 09:22:22,830 INFO main: Starting Captain Online...
captain-online-1 | [ONLINE] 2026-05-06 09:22:22,835 INFO shared.questdb_client: QuestDB reachable (attempt 1)
captain-online-1 | [ONLINE] 2026-05-06 09:22:22,839 INFO main: Redis: connected
captain-online-1 | [ONLINE] 2026-05-06 09:22:22,839 INFO main: Redis Stream consumer groups initialized
captain-online-1 | [ONLINE] 2026-05-06 09:22:22,850 INFO main: Clean restart — last checkpoint: SHUTDOWN
captain-online-1 | [ONLINE] 2026-05-06 09:22:23,668 INFO shared.topstep_client: TopstepX authenticated as isaach@euphroresources.co.uk (env=LIVE)
captain-online-1 | [ONLINE] 2026-05-06 09:22:23,668 INFO main: TopstepX API: authenticated
captain-online-1 | [ONLINE] 2026-05-06 09:22:23,670 INFO main: Resolved 10 contracts: ['ES', 'MES', 'NQ', 'MNQ', 'M2K', 'MYM', 'NKD', 'MGC', 'ZB', 'ZN']
captain-online-1 | [ONLINE] 2026-05-06 09:22:23,671 INFO pysignalr.transport: State change: disconnected -> connecting
captain-online-1 | [ONLINE] 2026-05-06 09:22:23,672 INFO main: MarketStream STARTED for 10 contracts
captain-online-1 | [ONLINE] 2026-05-06 09:22:23,766 INFO pysignalr.transport: State change: disconnected -> connecting
captain-online-1 | [ONLINE] 2026-05-06 09:22:23,766 INFO main: UserStream STARTED for account 150KTC-V2-478426-52758441 (id=20258288)
captain-online-1 | [ONLINE] 2026-05-06 09:22:23,799 INFO captain_online.blocks.b9_session_controller: Session registry loaded from /captain/config/session_registry.json
captain-online-1 | [ONLINE] 2026-05-06 09:22:23,799 INFO main: Starting session orchestrator...
captain-online-1 | [ONLINE] 2026-05-06 09:22:23,799 INFO captain_online.blocks.orchestrator: Online orchestrator starting...
captain-online-1 | [ONLINE] 2026-05-06 09:22:23,807 INFO captain_online.blocks.orchestrator: Position reconciliation: no positions found in Redis
captain-online-1 | [ONLINE] 2026-05-06 09:22:23,809 INFO captain_online.blocks.orchestrator: Online command stream consumer group ready
captain-online-1 | [ONLINE] 2026-05-06 09:22:24,041 INFO pysignalr.transport: Sending handshake to server
captain-online-1 | [ONLINE] 2026-05-06 09:22:24,041 INFO pysignalr.transport: Awaiting handshake from server
captain-online-1 | [ONLINE] 2026-05-06 09:22:24,131 INFO pysignalr.transport: State change: connecting -> connected
captain-online-1 | [ONLINE] 2026-05-06 09:22:24,131 INFO shared.topstep_stream: MarketStream CONNECTED — subscribing to 10 contract(s)
captain-online-1 | [ONLINE] 2026-05-06 09:22:24,138 INFO pysignalr.transport: Sending handshake to server
captain-online-1 | [ONLINE] 2026-05-06 09:22:24,139 INFO pysignalr.transport: Awaiting handshake from server
captain-online-1 | [ONLINE] 2026-05-06 09:22:24,223 INFO pysignalr.transport: State change: connecting -> connected
captain-online-1 | [ONLINE] 2026-05-06 09:22:24,223 INFO shared.topstep_stream: UserStream CONNECTED — subscribing to account 20258288
captain-online-1 | [ONLINE] 2026-05-06 09:25:00,978 INFO captain_online.blocks.orchestrator: Session NY (1) opening — beginning evaluation
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,169 INFO shared.vix_provider: VIX provider: loaded 9177 daily closes (1990-01-02 to 2026-05-04)
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,241 INFO shared.vix_provider: VXV provider: loaded 4181 daily closes (2009-09-18 to 2026-05-04)
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,284 INFO captain_online.blocks.orchestrator: ON-Orch: session NY init for 20258288 — eff_L_halt=750.00 eff_E=750.00 (SOD share=0.3163, completed=1 earlier sessions, carryover=275.59)
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,300 INFO captain_online.blocks.orchestrator: ON-Orch: session NY init for 20319811 — eff_L_halt=750.00 eff_E=750.00 (SOD share=0.3163, completed=1 earlier sessions, carryover=275.59)
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,345 INFO captain_online.blocks.orchestrator: ON-Orch: session NY init for 22020230 — eff_L_halt=750.00 eff_E=750.00 (SOD share=0.3163, completed=1 earlier sessions, carryover=275.59)
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,542 INFO captain_online.blocks.b8_or_tracker: Session registry loaded from /captain/config/session_registry.json
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,543 INFO captain_online.blocks.b8_or_tracker: OR tracker registered: MNQ (NY) OR 09:30:00–09:35:00 on 2026-05-06
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,543 INFO captain_online.blocks.b8_or_tracker: OR tracker registered: ES (NY) OR 09:30:00–09:35:00 on 2026-05-06
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,559 INFO captain_online.blocks.b8_or_tracker: OR tracker registered: NKD (APAC) OR 18:00:00–18:05:00 on 2026-05-06
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,561 INFO captain_online.blocks.b8_or_tracker: OR tracker registered: M2K (NY) OR 09:30:00–09:35:00 on 2026-05-06
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,562 INFO captain_online.blocks.b8_or_tracker: OR tracker registered: MES (NY) OR 09:30:00–09:35:00 on 2026-05-06
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,562 INFO captain_online.blocks.b8_or_tracker: OR tracker registered: MYM (NY) OR 09:30:00–09:35:00 on 2026-05-06
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,562 INFO captain_online.blocks.b8_or_tracker: OR tracker registered: NQ (NY) OR 09:30:00–09:35:00 on 2026-05-06
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,563 INFO captain_online.blocks.b8_or_tracker: OR tracker registered: ZB (NY) OR 09:30:00–09:35:00 on 2026-05-06
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,563 INFO captain_online.blocks.b8_or_tracker: OR tracker registered: ZN (NY) OR 09:30:00–09:35:00 on 2026-05-06
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,566 INFO captain_online.blocks.b8_or_tracker: OR tracker registered: MGC (LON) OR 03:00:00–03:05:00 on 2026-05-06
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,580 INFO captain_online.blocks.b8_or_tracker: OR tracker registered: P00-1777553734 (NY) OR 09:30:00–09:35:00 on 2026-05-06
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,581 INFO captain_online.blocks.b8_or_tracker: OR tracker registered: P00-1777462589 (NY) OR 09:30:00–09:35:00 on 2026-05-06
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,581 INFO captain_online.blocks.orchestrator: OR tracker: 12 assets registered at session open
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,597 INFO captain_online.blocks.b1_data_ingestion: ON-B1: Starting data ingestion for session NY (1)
captain-online-1 | [ONLINE] 2026-05-06 09:25:04,783 INFO captain_online.blocks.b1_data_ingestion: ON-B1: 8 assets eligible for session NY
captain-online-1 | [ONLINE] 2026-05-06 09:25:04,783 INFO captain_online.blocks.b1_data_ingestion: ON-B1: System timezone check passed (local: America/New_York)
captain-online-1 | [ONLINE] 2026-05-06 09:25:09,521 INFO captain_online.blocks.b1_features: ON-B1A: Options data unavailable (TopstepX futures-only) — AIM-02 pcr/put_skew and AIM-03 gex features will output neutral
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,551 INFO captain_online.blocks.b1_data_ingestion: ON-B1: Data ingestion complete. 8 active assets, 158 features computed
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,559 INFO captain_online.blocks.b2_regime_probability: ON-B2: Regime uncertainty for MNQ: max_prob=0.500 — robust Kelly will be used
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,559 INFO captain_online.blocks.b2_regime_probability: ON-B2: Regime uncertainty for ES: max_prob=0.500 — robust Kelly will be used
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,560 INFO captain_online.blocks.b2_regime_probability: ON-B2: Regime uncertainty for M2K: max_prob=0.500 — robust Kelly will be used
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,560 INFO captain_online.blocks.b2_regime_probability: ON-B2: Regime uncertainty for MES: max_prob=0.500 — robust Kelly will be used
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,560 INFO captain_online.blocks.b2_regime_probability: ON-B2: Regime uncertainty for MYM: max_prob=0.500 — robust Kelly will be used
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,560 INFO captain_online.blocks.b2_regime_probability: ON-B2: Regime uncertainty for NQ: max_prob=0.500 — robust Kelly will be used
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,560 INFO captain_online.blocks.b2_regime_probability: ON-B2: Regime uncertainty for ZB: max_prob=0.500 — robust Kelly will be used
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,560 INFO captain_online.blocks.b2_regime_probability: ON-B2: Regime uncertainty for ZN: max_prob=0.500 — robust Kelly will be used
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,560 INFO captain_online.blocks.b2_regime_probability: ON-B2: Regime probabilities computed for 8 assets (8 uncertain)
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,577 INFO shared.aim_compute: AIM MNQ: AIM-04(IVTS)=0.900×0.167 | AIM-06(EconCal)=1.000×0.167 | AIM-08(CrossCorr)=0.900×0.167 | AIM-11(RegimeWarn)=1.000×0.167 | AIM-12(DynCosts)=1.000×0.167 | AIM-15(OpenVol)=1.000×0.167
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,577 INFO shared.aim_compute: AIM ES: AIM-04(IVTS)=0.900×0.167 | AIM-06(EconCal)=1.000×0.167 | AIM-08(CrossCorr)=1.000×0.167 | AIM-11(RegimeWarn)=1.000×0.167 | AIM-12(DynCosts)=1.000×0.167 | AIM-15(OpenVol)=1.000×0.167
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,578 INFO shared.aim_compute: AIM M2K: AIM-04(IVTS)=0.900×0.167 | AIM-06(EconCal)=1.000×0.167 | AIM-08(CrossCorr)=1.000×0.167 | AIM-11(RegimeWarn)=1.000×0.167 | AIM-12(DynCosts)=1.000×0.167 | AIM-15(OpenVol)=1.000×0.167
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,578 INFO shared.aim_compute: AIM MES: AIM-04(IVTS)=0.900×0.167 | AIM-06(EconCal)=1.000×0.167 | AIM-08(CrossCorr)=1.000×0.167 | AIM-11(RegimeWarn)=1.000×0.167 | AIM-12(DynCosts)=1.000×0.167 | AIM-15(OpenVol)=1.000×0.167
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,578 INFO shared.aim_compute: AIM MYM: AIM-04(IVTS)=0.900×0.167 | AIM-06(EconCal)=1.000×0.167 | AIM-08(CrossCorr)=0.900×0.167 | AIM-11(RegimeWarn)=1.000×0.167 | AIM-12(DynCosts)=1.000×0.167 | AIM-15(OpenVol)=1.000×0.167
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,578 INFO shared.aim_compute: AIM NQ: AIM-04(IVTS)=0.900×0.167 | AIM-06(EconCal)=1.000×0.167 | AIM-08(CrossCorr)=0.900×0.167 | AIM-11(RegimeWarn)=1.000×0.167 | AIM-12(DynCosts)=1.000×0.167 | AIM-15(OpenVol)=1.000×0.167
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,578 INFO shared.aim_compute: AIM ZB: AIM-04(IVTS)=0.900×0.167 | AIM-06(EconCal)=1.000×0.167 | AIM-08(CrossCorr)=1.050×0.167 | AIM-11(RegimeWarn)=1.000×0.167 | AIM-12(DynCosts)=1.000×0.167 | AIM-15(OpenVol)=1.000×0.167
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,578 INFO shared.aim_compute: AIM ZN: AIM-04(IVTS)=0.855×0.167 | AIM-06(EconCal)=1.000×0.167 | AIM-08(CrossCorr)=1.000×0.167 | AIM-11(RegimeWarn)=1.000×0.167 | AIM-12(DynCosts)=1.000×0.167 | AIM-15(OpenVol)=1.000×0.167
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,578 INFO shared.aim_compute: AIM aggregation: 8 assets, 8 with active AIMs, 48 individual AIMs computed
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,693 INFO captain_online.blocks.hmm_inference_block: [aim16-online] D26 inference persist session_id=1 opp={'NY': 0.3162721139793591, 'LON': 0.367455772041282, 'APAC': 0.3162721139793589} schema=1
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,723 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: Kelly sizing for user primary_user (1 accounts, 8 assets)
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,728 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: pass_probability absent for account 20258288 (PASS_EVAL) — using default 0.85 Kelly multiplier; seed pass_probability once ≥30 Pseudotrader sessions exist
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,730 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: evaluation_end_date absent for account 20258288 — using default budget_divisor=10 (open-ended combine; no fixed deadline)
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,730 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: max_daily_loss absent for account 20258288 — max_by_mll=999 (no MLL on this combine; MDD-only risk limit applies)
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,731 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: MNQ ac=20258288 kelly=0.0669→0.0569(rg)→156.7(raw) risk/c=54.5 cap=150000 tsm=8 topstep=8 scale=999 → 8 contracts [TRADE]
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,734 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: pass_probability absent for account 20258288 (PASS_EVAL) — using default 0.85 Kelly multiplier; seed pass_probability once ≥30 Pseudotrader sessions exist
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,734 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: evaluation_end_date absent for account 20258288 — using default budget_divisor=10 (open-ended combine; no fixed deadline)
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,735 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: max_daily_loss absent for account 20258288 — max_by_mll=999 (no MLL on this combine; MDD-only risk limit applies)
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,735 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: ES ac=20258288 kelly=0.0382→0.0325(rg)→25.5(raw) risk/c=191.2 cap=150000 tsm=2 topstep=2 scale=999 → 2 contracts [TRADE]
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,736 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: pass_probability absent for account 20258288 (PASS_EVAL) — using default 0.85 Kelly multiplier; seed pass_probability once ≥30 Pseudotrader sessions exist
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,752 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: evaluation_end_date absent for account 20258288 — using default budget_divisor=10 (open-ended combine; no fixed deadline)
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,752 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: max_daily_loss absent for account 20258288 — max_by_mll=999 (no MLL on this combine; MDD-only risk limit applies)
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,752 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: M2K ac=20258288 kelly=0.0685→0.0583(rg)→428.3(raw) risk/c=20.4 cap=150000 tsm=15 topstep=26 scale=999 → 15 contracts [TRADE]
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,758 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: pass_probability absent for account 20258288 (PASS_EVAL) — using default 0.85 Kelly multiplier; seed pass_probability once ≥30 Pseudotrader sessions exist
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,758 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: evaluation_end_date absent for account 20258288 — using default budget_divisor=10 (open-ended combine; no fixed deadline)
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,759 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: max_daily_loss absent for account 20258288 — max_by_mll=999 (no MLL on this combine; MDD-only risk limit applies)
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,759 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: MES ac=20258288 kelly=0.0845→0.0718(rg)→547.8(raw) risk/c=19.7 cap=150000 tsm=15 topstep=25 scale=999 → 15 contracts [TRADE]
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,761 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: pass_probability absent for account 20258288 (PASS_EVAL) — using default 0.85 Kelly multiplier; seed pass_probability once ≥30 Pseudotrader sessions exist
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,761 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: evaluation_end_date absent for account 20258288 — using default budget_divisor=10 (open-ended combine; no fixed deadline)
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,761 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: max_daily_loss absent for account 20258288 — max_by_mll=999 (no MLL on this combine; MDD-only risk limit applies)
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,761 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: MYM ac=20258288 kelly=0.0932→0.0792(rg)→423.4(raw) risk/c=28.1 cap=150000 tsm=15 topstep=17 scale=999 → 15 contracts [TRADE]
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,764 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: pass_probability absent for account 20258288 (PASS_EVAL) — using default 0.85 Kelly multiplier; seed pass_probability once ≥30 Pseudotrader sessions exist
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,766 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: evaluation_end_date absent for account 20258288 — using default budget_divisor=10 (open-ended combine; no fixed deadline)
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,766 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: max_daily_loss absent for account 20258288 — max_by_mll=999 (no MLL on this combine; MDD-only risk limit applies)
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,766 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: NQ ac=20258288 kelly=0.0737→0.0627(rg)→17.7(raw) risk/c=531.3 cap=150000 tsm=0 topstep=0 scale=999 → 0 contracts [SKIP]
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,768 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: pass_probability absent for account 20258288 (PASS_EVAL) — using default 0.85 Kelly multiplier; seed pass_probability once ≥30 Pseudotrader sessions exist
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,769 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: evaluation_end_date absent for account 20258288 — using default budget_divisor=10 (open-ended combine; no fixed deadline)
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,769 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: max_daily_loss absent for account 20258288 — max_by_mll=999 (no MLL on this combine; MDD-only risk limit applies)
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,769 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: ZB ac=20258288 kelly=0.1218→0.1035(rg)→696.0(raw) risk/c=22.3 cap=150000 tsm=15 topstep=23 scale=999 → 15 contracts [TRADE]
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,793 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: pass_probability absent for account 20258288 (PASS_EVAL) — using default 0.85 Kelly multiplier; seed pass_probability once ≥30 Pseudotrader sessions exist
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,803 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: evaluation_end_date absent for account 20258288 — using default budget_divisor=10 (open-ended combine; no fixed deadline)
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,803 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: max_daily_loss absent for account 20258288 — max_by_mll=999 (no MLL on this combine; MDD-only risk limit applies)
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,803 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: ZN ac=20258288 kelly=0.1338→0.1137(rg)→1401.7(raw) risk/c=12.2 cap=150000 tsm=15 topstep=47 scale=999 → 15 contracts [TRADE]
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,817 INFO captain_online.blocks.b5_trade_selection: ON-B5: Trade selection for user primary_user: 5/8 assets selected
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,818 INFO captain_online.blocks.b5_trade_selection: ON-B5 HMM: session=NY weight=0.316 regime=HMM_FULL n_obs=240 (observability-only; budget enforcement at B4/B5C)
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,849 INFO captain_online.blocks.b5b_quality_gate: ON-B5B: Quality gate for user primary_user: 5 recommended, 0 below threshold
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,906 INFO captain_online.blocks.orchestrator: Phase A — user primary_user: 5 recommended, 0 below threshold
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,906 INFO captain_online.blocks.orchestrator: Phase A complete for NY — 8 assets tracked, 1 user(s) pending Phase B
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,938 WARNING captain_online.blocks.b8_or_tracker: OR EXPIRED (stuck WAITING): MGC — no ticks received before cutoff 03:35:00 (market stream may be disconnected for this contract)
captain-online-1 | [ONLINE] 2026-05-06 09:30:00,047 INFO captain_online.blocks.b8_or_tracker: OR FORMING: NQ — first tick 28389.2500 at 09:30:00.047926
captain-online-1 | [ONLINE] 2026-05-06 09:30:00,048 INFO captain_online.blocks.b8_or_tracker: OR FORMING: ES — first tick 7331.2500 at 09:30:00.048047
captain-online-1 | [ONLINE] 2026-05-06 09:30:00,050 INFO captain_online.blocks.b8_or_tracker: OR FORMING: MNQ — first tick 28389.7500 at 09:30:00.050598
captain-online-1 | [ONLINE] 2026-05-06 09:30:00,131 INFO captain_online.blocks.b8_or_tracker: OR FORMING: M2K — first tick 2879.9000 at 09:30:00.131260
captain-online-1 | [ONLINE] 2026-05-06 09:30:00,131 INFO captain_online.blocks.b8_or_tracker: OR FORMING: MES — first tick 7330.7500 at 09:30:00.131368
captain-online-1 | [ONLINE] 2026-05-06 09:30:00,154 INFO captain_online.blocks.b8_or_tracker: OR FORMING: MYM — first tick 49820.0000 at 09:30:00.154549
captain-online-1 | [ONLINE] 2026-05-06 09:30:00,298 INFO captain_online.blocks.b8_or_tracker: OR FORMING: ZN — first tick 110.7344 at 09:30:00.298956
captain-online-1 | [ONLINE] 2026-05-06 09:30:00,653 INFO captain_online.blocks.b8_or_tracker: OR FORMING: ZB — first tick 113.5312 at 09:30:00.653800
captain-online-1 | [ONLINE] 2026-05-06 09:35:00,050 INFO captain_online.blocks.b8_or_tracker: OR COMPLETE: NQ — high=28446.5000 low=28337.0000 range=109.5000 (4077 ticks)
captain-online-1 | [ONLINE] 2026-05-06 09:35:00,050 INFO captain_online.blocks.b8_or_tracker: OR COMPLETE: MNQ — high=28446.5000 low=28336.7500 range=109.7500 (5537 ticks)
captain-online-1 | [ONLINE] 2026-05-06 09:35:00,101 INFO captain_online.blocks.b8_or_tracker: OR COMPLETE: ES — high=7341.0000 low=7327.2500 range=13.7500 (3264 ticks)
captain-online-1 | [ONLINE] 2026-05-06 09:35:00,101 INFO captain_online.blocks.b8_or_tracker: OR COMPLETE: MES — high=7341.2500 low=7327.2500 range=14.0000 (3391 ticks)
captain-online-1 | [ONLINE] 2026-05-06 09:35:00,104 INFO captain_online.blocks.b8_or_tracker: OR COMPLETE: MYM — high=49910.0000 low=49808.0000 range=102.0000 (2318 ticks)
captain-online-1 | [ONLINE] 2026-05-06 09:35:00,197 INFO captain_online.blocks.b8_or_tracker: OR COMPLETE: M2K — high=2881.2000 low=2873.5000 range=7.7000 (1587 ticks)
captain-online-1 | [ONLINE] 2026-05-06 09:35:00,393 INFO captain_online.blocks.b8_or_tracker: OR BREAKOUT LONG: NQ — price=28447.0000 > OR high=28446.5000, or_range=109.5000
captain-online-1 | [ONLINE] 2026-05-06 09:35:00,393 INFO captain_online.blocks.b8_or_tracker: OR BREAKOUT LONG: ES — price=7341.5000 > OR high=7341.0000, or_range=13.7500
captain-online-1 | [ONLINE] 2026-05-06 09:35:00,494 INFO captain_online.blocks.b8_or_tracker: OR BREAKOUT LONG: MES — price=7341.5000 > OR high=7341.2500, or_range=14.0000
captain-online-1 | [ONLINE] 2026-05-06 09:35:00,746 INFO captain_online.blocks.b8_or_tracker: OR BREAKOUT LONG: MNQ — price=28446.7500 > OR high=28446.5000, or_range=109.7500
captain-online-1 | [ONLINE] 2026-05-06 09:35:01,247 INFO captain_online.blocks.b8_or_tracker: OR COMPLETE: ZB — high=113.5938 low=113.5000 range=0.0938 (87 ticks)
captain-online-1 | [ONLINE] 2026-05-06 09:35:02,082 INFO captain_online.blocks.b1_features: Stored daily OHLCV for ES: close=7295.50
captain-online-1 | [ONLINE] 2026-05-06 09:35:02,146 INFO captain_online.blocks.b8_or_tracker: OR COMPLETE: ZN — high=110.7656 low=110.7344 range=0.0312 (123 ticks)
captain-online-1 | [ONLINE] 2026-05-06 09:35:02,206 INFO captain_online.blocks.b1_features: Stored opening vol for ES: 0.000337
captain-online-1 | [ONLINE] 2026-05-06 09:35:02,665 INFO captain_online.blocks.b1_features: Stored daily OHLCV for NQ: close=28207.25
captain-online-1 | [ONLINE] 2026-05-06 09:35:02,764 INFO captain_online.blocks.b1_features: Stored opening vol for NQ: 0.000805
captain-online-1 | [ONLINE] 2026-05-06 09:35:03,202 INFO captain_online.blocks.b1_features: Stored daily OHLCV for MNQ: close=28208.00
captain-online-1 | [ONLINE] 2026-05-06 09:35:03,302 INFO captain_online.blocks.b1_features: Stored opening vol for MNQ: 0.000791
captain-online-1 | [ONLINE] 2026-05-06 09:35:03,711 INFO captain_online.blocks.b1_features: Stored daily OHLCV for MES: close=7295.75
captain-online-1 | [ONLINE] 2026-05-06 09:35:03,811 INFO captain_online.blocks.b1_features: Stored opening vol for MES: 0.000346
captain-online-1 | [ONLINE] 2026-05-06 09:35:03,836 INFO captain_online.blocks.b6_signal_output: ON-B6-SUMMARY user=primary_user session=1 recommended=2 built=2 below_threshold=0
captain-online-1 | [ONLINE] 2026-05-06 09:35:03,842 INFO captain_online.blocks.b6_signal_output: ON-B6: 2 signals published for user primary_user (session 1), 0 below threshold
captain-online-1 | [ONLINE] 2026-05-06 09:35:03,850 INFO captain_online.blocks.orchestrator: Phase B: generated signals for ['ES', 'NQ', 'MNQ', 'MES']
captain-online-1 | [ONLINE] 2026-05-06 09:35:05,847 INFO captain_online.blocks.b8_or_tracker: OR BREAKOUT LONG: M2K — price=2881.4000 > OR high=2881.2000, or_range=7.7000
captain-online-1 | [ONLINE] 2026-05-06 09:35:06,254 INFO captain_online.blocks.b1_features: Stored daily OHLCV for M2K: close=2849.30
captain-online-1 | [ONLINE] 2026-05-06 09:35:06,355 INFO captain_online.blocks.b1_features: Stored opening vol for M2K: 0.000582
captain-online-1 | [ONLINE] 2026-05-06 09:35:06,357 WARNING captain_online.blocks.orchestrator: ON-B6-SKIP user=primary_user session=1 assets_filter=['M2K'] recommended_trades=['ZB', 'ZN', 'MNQ', 'MYM', 'MES'] account_skip_reason={'MNQ': {'20258288': None}, 'ES': {'20258288': 'Removed by portfolio-level constraint (correlation or position limit)'}, 'M2K': {'20258288': 'Removed by portfolio-level constraint (correlation or position limit)'}, 'MES': {'20258288': None}, 'MYM': {'20258288': None}, 'NQ': {'20258288': 'Position size rounded to 0'}, 'ZB': {'20258288': None}, 'ZN': {'20258288': None}} — B6 short-circuited (no candidates)
captain-online-1 | [ONLINE] 2026-05-06 09:35:06,357 INFO captain_online.blocks.orchestrator: Phase B: generated signals for ['M2K']
captain-online-1 | [ONLINE] 2026-05-06 09:36:01,799 INFO captain_online.blocks.b8_or_tracker: OR BREAKOUT LONG: MYM — price=49912.0000 > OR high=49910.0000, or_range=102.0000
captain-online-1 | [ONLINE] 2026-05-06 09:36:03,052 INFO captain_online.blocks.b1_features: Stored daily OHLCV for MYM: close=49393.00
captain-online-1 | [ONLINE] 2026-05-06 09:36:03,152 INFO captain_online.blocks.b1_features: Stored opening vol for MYM: 0.000549
captain-online-1 | [ONLINE] 2026-05-06 09:36:03,156 INFO captain_online.blocks.b6_signal_output: ON-B6-SUMMARY user=primary_user session=1 recommended=1 built=1 below_threshold=0
captain-online-1 | [ONLINE] 2026-05-06 09:36:03,165 INFO captain_online.blocks.b6_signal_output: ON-B6: 1 signals published for user primary_user (session 1), 0 below threshold
captain-online-1 | [ONLINE] 2026-05-06 09:36:03,169 INFO captain_online.blocks.orchestrator: Phase B: generated signals for ['MYM']
captain-online-1 | [ONLINE] 2026-05-06 09:36:03,535 WARNING shared.topstep_stream: UserStream RAW order args=([{'action': 1, 'data': {'id': 2934939764, 'accountId': 20258288, 'contractId': 'CON.F.US.MYM.M26', 'symbolId': 'F.US.MYM', 'creationTimestamp': '2026-05-06T13:36:03.4962794+00:00', 'updateTimestamp': '2026-05-06T13:36:03.4962794+00:00', 'status': 6, 'type': 2, 'side': 0, 'size': 15, 'fillVolume': 0}}],) type=list
captain-online-1 | [ONLINE] 2026-05-06 09:36:03,535 INFO main: UserStream ORDER: id=2934939764 status=6 type=2
captain-online-1 | [ONLINE] 2026-05-06 09:36:03,535 WARNING main: UserStream ORDER REJECTED: id=2934939764 data={'id': 2934939764, 'accountId': 20258288, 'contractId': 'CON.F.US.MYM.M26', 'symbolId': 'F.US.MYM', 'creationTimestamp': '2026-05-06T13:36:03.4962794+00:00', 'updateTimestamp': '2026-05-06T13:36:03.4962794+00:00', 'status': 6, 'type': 2, 'side': 0, 'size': 15, 'fillVolume': 0}
captain-online-1 | [ONLINE] 2026-05-06 09:36:03,539 INFO main: UserStream ORDER: id=2934939764 status=5 type=2
captain-online-1 | [ONLINE] 2026-05-06 09:36:03,649 INFO main: UserStream ORDER: id=2934939816 status=6 type=2
captain-online-1 | [ONLINE] 2026-05-06 09:36:03,649 WARNING main: UserStream ORDER REJECTED: id=2934939816 data={'id': 2934939816, 'accountId': 20258288, 'contractId': 'CON.F.US.MYM.M26', 'symbolId': 'F.US.MYM', 'creationTimestamp': '2026-05-06T13:36:03.6112156+00:00', 'updateTimestamp': '2026-05-06T13:36:03.6112156+00:00', 'status': 6, 'type': 2, 'side': 0, 'size': 15, 'fillVolume': 0}
captain-online-1 | [ONLINE] 2026-05-06 09:36:03,659 WARNING shared.topstep_stream: UserStream RAW trade args=([{'action': 0, 'data': {'id': 2555492505, 'accountId': 20258288, 'contractId': 'CON.F.US.MYM.M26', 'creationTimestamp': '2026-05-06T13:36:03.6185676+00:00', 'price': 49909, 'fees': 5.55, 'commissions': 3.75, 'side': 0, 'size': 15, 'voided': False, 'orderId': 2934939816}}],) type=list
captain-online-1 | [ONLINE] 2026-05-06 09:36:03,659 INFO main: UserStream TRADE: price=49909 pnl=None fees=5.55
captain-online-1 | [ONLINE] 2026-05-06 09:36:03,660 INFO main: UserStream ORDER: id=2934939816 status=2 type=2
captain-online-1 | [ONLINE] 2026-05-06 09:36:03,666 WARNING shared.topstep_stream: UserStream RAW position args=([{'action': 1, 'data': {'id': 703034494, 'accountId': 20258288, 'contractId': 'CON.F.US.MYM.M26', 'contractDisplayName': 'MYMM26', 'creationTimestamp': '2026-05-06T13:36:03.6247335+00:00', 'type': 1, 'size': 15, 'averagePrice': 49909}}],) type=list
captain-online-1 | [ONLINE] 2026-05-06 09:36:03,667 INFO main: UserStream POSITION: contract=CON.F.US.MYM.M26 size=15 avgPrice=49909
captain-online-1 | [ONLINE] 2026-05-06 09:36:03,672 WARNING shared.topstep_stream: UserStream RAW account args=([{'action': 1, 'data': {'id': 20258288, 'name': '150KTC-V2-478426-52758441', 'balance': 150175.38, 'canTrade': True, 'isVisible': True, 'simulated': True}}],) type=list
captain-online-1 | [ONLINE] 2026-05-06 09:36:03,672 INFO main: UserStream ACCOUNT: balance=150175.38
captain-online-1 | [ONLINE] 2026-05-06 09:36:03,718 INFO main: UserStream ACCOUNT: balance=150175.38
captain-online-1 | [ONLINE] 2026-05-06 09:36:03,867 INFO main: UserStream ORDER: id=2934939941 status=1 type=4
captain-online-1 | [ONLINE] 2026-05-06 09:36:03,974 INFO main: UserStream ORDER: id=2934939996 status=1 type=1
captain-online-1 | [ONLINE] 2026-05-06 09:36:03,981 INFO captain_online.blocks.orchestrator: Position opened: MYM for user primary_user (15 contracts)
captain-online-1 | [ONLINE] 2026-05-06 09:36:04,064 INFO main: UserStream ACCOUNT: balance=150175.38
captain-online-1 | [ONLINE] 2026-05-06 09:36:04,065 INFO main: UserStream ACCOUNT: balance=150175.38
captain-online-1 | [ONLINE] 2026-05-06 09:36:43,043 INFO captain_online.blocks.b8_or_tracker: OR BREAKOUT LONG: ZN — price=110.7812 > OR high=110.7656, or_range=0.0312
captain-online-1 | [ONLINE] 2026-05-06 09:36:43,777 INFO captain_online.blocks.b1_features: Stored daily OHLCV for ZN: close=110.27
captain-online-1 | [ONLINE] 2026-05-06 09:36:43,878 INFO captain_online.blocks.b1_features: Stored opening vol for ZN: 0.000081
captain-online-1 | [ONLINE] 2026-05-06 09:36:43,885 INFO captain_online.blocks.b6_signal_output: ON-B6-SUMMARY user=primary_user session=1 recommended=1 built=1 below_threshold=0
captain-online-1 | [ONLINE] 2026-05-06 09:36:43,894 INFO captain_online.blocks.b6_signal_output: ON-B6: 1 signals published for user primary_user (session 1), 0 below threshold
captain-online-1 | [ONLINE] 2026-05-06 09:36:43,898 INFO captain_online.blocks.orchestrator: Phase B: generated signals for ['ZN']
captain-online-1 | [ONLINE] 2026-05-06 09:36:43,901 INFO captain_online.blocks.b7_shadow_monitor: Shadow resolved: ZN SL_HIT SIG-98FFF726C989 pnl=-312.50 (theoretical)
captain-online-1 | [ONLINE] 2026-05-06 09:38:00,480 INFO captain_online.blocks.b7_shadow_monitor: Shadow resolved: MNQ SL_HIT SIG-4D524C4EAE13 pnl=-629.33 (theoretical)
captain-online-1 | [ONLINE] 2026-05-06 09:38:31,534 INFO main: UserStream ORDER: id=2934939996 status=2 type=1
captain-online-1 | [ONLINE] 2026-05-06 09:38:31,535 INFO main: UserStream TRADE: price=49983.0 pnl=555.0 fees=5.55
captain-online-1 | [ONLINE] 2026-05-06 09:38:31,535 INFO main: UserStream TRADE: price=49909.0 pnl=None fees=5.55
captain-online-1 | [ONLINE] 2026-05-06 09:38:31,543 INFO main: UserStream POSITION: contract=CON.F.US.MYM.M26 size=0 avgPrice=49909.0
captain-online-1 | [ONLINE] 2026-05-06 09:38:31,551 INFO main: UserStream ACCOUNT: balance=150721.08
captain-online-1 | [ONLINE] 2026-05-06 09:38:31,602 INFO main: UserStream ACCOUNT: balance=150721.08
captain-online-1 | [ONLINE] 2026-05-06 09:38:34,422 INFO main: UserStream ACCOUNT: balance=150721.08
captain-online-1 | [ONLINE] 2026-05-06 09:38:34,423 INFO main: UserStream ACCOUNT: balance=150721.08
captain-online-1 | [ONLINE] 2026-05-06 09:39:16,168 ERROR captain_online.blocks.b7_position_monitor: ON-B7: cannot cancel orphan brackets for MYM — account_id unresolved (account=20258288)
captain-online-1 | [ONLINE] 2026-05-06 09:39:16,246 INFO captain_online.blocks.b7_position_monitor: ON-B7: Published trade outcome TRD-B873639F6F2D to stream
captain-online-1 | [ONLINE] 2026-05-06 09:39:16,246 INFO captain_online.blocks.b7_position_monitor: ON-B7: Position resolved — MYM TP_HIT primary_user net_pnl=618.90 trade_id=TRD-B873639F6F2D
captain-online-1 | [ONLINE] 2026-05-06 09:41:39,664 INFO main: UserStream ORDER: id=2934939941 status=3 type=4
captain-online-1 | [ONLINE] 2026-05-06 09:42:11,695 INFO captain_online.blocks.b8_or_tracker: OR BREAKOUT SHORT: ZB — price=113.4688 < OR low=113.5000, or_range=0.0938
captain-online-1 | [ONLINE] 2026-05-06 09:42:12,828 INFO captain_online.blocks.b1_features: Stored daily OHLCV for ZB: close=112.66
captain-online-1 | [ONLINE] 2026-05-06 09:42:12,931 INFO captain_online.blocks.b1_features: Stored opening vol for ZB: 0.000138
captain-online-1 | [ONLINE] 2026-05-06 09:42:12,936 INFO captain_online.blocks.b6_signal_output: ON-B6-SUMMARY user=primary_user session=1 recommended=1 built=1 below_threshold=0
captain-online-1 | [ONLINE] 2026-05-06 09:42:12,946 INFO captain_online.blocks.b6_signal_output: ON-B6: 1 signals published for user primary_user (session 1), 0 below threshold
captain-online-1 | [ONLINE] 2026-05-06 09:42:12,949 INFO captain_online.blocks.orchestrator: Phase B: generated signals for ['ZB']
captain-online-1 | [ONLINE] 2026-05-06 09:42:12,980 INFO captain_online.blocks.b9_capacity_evaluation: ON-B9: Capacity eval — supply ratio=70.0, quality rate=100%, 1 constraints
captain-online-1 | [ONLINE] 2026-05-06 09:42:12,981 INFO captain_online.blocks.orchestrator: Session NY Phase B complete — all assets resolved
captain-online-1 | [ONLINE] 2026-05-06 09:42:13,071 INFO captain_online.blocks.b7_shadow_monitor: Shadow resolved: ZB SL_HIT SIG-93D26B847466 pnl=-937.50 (theoretical)
captain-online-1 | [ONLINE] 2026-05-06 09:42:13,348 INFO main: UserStream ORDER: id=2935091326 status=6 type=2
captain-online-1 | [ONLINE] 2026-05-06 09:42:13,348 WARNING main: UserStream ORDER REJECTED: id=2935091326 data={'id': 2935091326, 'accountId': 20258288, 'contractId': 'CON.F.US.USA.M26', 'symbolId': 'F.US.USA', 'creationTimestamp': '2026-05-06T13:42:13.309393+00:00', 'updateTimestamp': '2026-05-06T13:42:13.309393+00:00', 'status': 6, 'type': 2, 'side': 1, 'size': 15, 'fillVolume': 0}
captain-online-1 | [ONLINE] 2026-05-06 09:42:13,351 INFO main: UserStream ORDER: id=2935091326 status=5 type=2
captain-online-1 | [ONLINE] 2026-05-06 09:42:13,454 INFO main: UserStream ORDER: id=2935091381 status=6 type=2
captain-online-1 | [ONLINE] 2026-05-06 09:42:13,454 WARNING main: UserStream ORDER REJECTED: id=2935091381 data={'id': 2935091381, 'accountId': 20258288, 'contractId': 'CON.F.US.USA.M26', 'symbolId': 'F.US.USA', 'creationTimestamp': '2026-05-06T13:42:13.4174941+00:00', 'updateTimestamp': '2026-05-06T13:42:13.4174941+00:00', 'status': 6, 'type': 2, 'side': 1, 'size': 15, 'fillVolume': 0}
captain-online-1 | [ONLINE] 2026-05-06 09:42:13,464 INFO main: UserStream TRADE: price=113.46875 pnl=None fees=13.35
captain-online-1 | [ONLINE] 2026-05-06 09:42:13,465 INFO main: UserStream ORDER: id=2935091381 status=2 type=2
captain-online-1 | [ONLINE] 2026-05-06 09:42:13,471 INFO main: UserStream POSITION: contract=CON.F.US.USA.M26 size=15 avgPrice=113.46875
captain-online-1 | [ONLINE] 2026-05-06 09:42:13,480 INFO main: UserStream ACCOUNT: balance=150700.23
captain-online-1 | [ONLINE] 2026-05-06 09:42:13,513 INFO main: UserStream ACCOUNT: balance=150700.23
captain-online-1 | [ONLINE] 2026-05-06 09:42:13,686 INFO main: UserStream ORDER: id=2935091577 status=1 type=4
captain-online-1 | [ONLINE] 2026-05-06 09:42:13,791 INFO main: UserStream ORDER: id=2935091659 status=1 type=1
captain-online-1 | [ONLINE] 2026-05-06 09:42:13,813 INFO captain_online.blocks.orchestrator: Position opened: ZB for user primary_user (15 contracts)
captain-online-1 | [ONLINE] 2026-05-06 09:42:13,879 INFO main: UserStream TRADE: price=113.5 pnl=-468.75 fees=13.35
captain-online-1 | [ONLINE] 2026-05-06 09:42:13,888 INFO main: UserStream TRADE: price=113.46875 pnl=None fees=13.35
captain-online-1 | [ONLINE] 2026-05-06 09:42:13,890 INFO main: UserStream ORDER: id=2935091577 status=2 type=4
captain-online-1 | [ONLINE] 2026-05-06 09:42:13,892 INFO main: UserStream POSITION: contract=CON.F.US.USA.M26 size=0 avgPrice=113.46875
captain-online-1 | [ONLINE] 2026-05-06 09:42:13,893 INFO main: UserStream ACCOUNT: balance=150210.63
captain-online-1 | [ONLINE] 2026-05-06 09:42:13,922 INFO main: UserStream ACCOUNT: balance=150210.63
captain-online-1 | [ONLINE] 2026-05-06 09:42:14,171 ERROR captain_online.blocks.b7_position_monitor: ON-B7: cannot cancel orphan brackets for ZB — account_id unresolved (account=20258288)
captain-online-1 | [ONLINE] 2026-05-06 09:42:14,184 INFO captain_online.blocks.b7_position_monitor: ON-B7: Published trade outcome TRD-910AE8FDB95E to stream
captain-online-1 | [ONLINE] 2026-05-06 09:42:14,184 INFO captain_online.blocks.b7_position_monitor: ON-B7: Position resolved — ZB SL_HIT primary_user net_pnl=-502.65 trade_id=TRD-910AE8FDB95E
captain-online-1 | [ONLINE] 2026-05-06 09:42:14,204 INFO main: UserStream ACCOUNT: balance=150210.63
captain-online-1 | [ONLINE] 2026-05-06 09:42:14,205 INFO main: UserStream ACCOUNT: balance=150210.63
captain-online-1 | [ONLINE] 2026-05-06 09:45:35,530 INFO main: UserStream ORDER: id=2935091659 status=2 type=1
captain-online-1 | [ONLINE] 2026-05-06 09:45:35,531 INFO main: UserStream TRADE: price=113.40625 pnl=None fees=13.35
captain-online-1 | [ONLINE] 2026-05-06 09:45:35,537 INFO main: UserStream POSITION: contract=CON.F.US.USA.M26 size=15 avgPrice=113.40625
captain-online-1 | [ONLINE] 2026-05-06 09:45:35,544 INFO main: UserStream ACCOUNT: balance=150189.78
captain-online-1 | [ONLINE] 2026-05-06 09:45:35,564 INFO main: UserStream ACCOUNT: balance=150189.78
captain-online-1 | [ONLINE] 2026-05-06 09:45:36,587 INFO main: UserStream ACCOUNT: balance=150189.78
captain-online-1 | [ONLINE] 2026-05-06 09:45:36,588 INFO main: UserStream ACCOUNT: balance=150189.78
captain-online-1 | [ONLINE] 2026-05-06 09:46:27,200 INFO main: UserStream ORDER: id=2935194612 status=6 type=2
captain-online-1 | [ONLINE] 2026-05-06 09:46:27,200 WARNING main: UserStream ORDER REJECTED: id=2935194612 data={'id': 2935194612, 'accountId': 20258288, 'contractId': 'CON.F.US.USA.M26', 'symbolId': 'F.US.USA', 'creationTimestamp': '2026-05-06T13:46:27.1615066+00:00', 'updateTimestamp': '2026-05-06T13:46:27.1615066+00:00', 'status': 6, 'type': 2, 'side': 1, 'size': 15, 'fillVolume': 0}
captain-online-1 | [ONLINE] 2026-05-06 09:46:27,205 INFO main: UserStream TRADE: price=113.40625 pnl=0.0 fees=13.35
captain-online-1 | [ONLINE] 2026-05-06 09:46:27,206 INFO main: UserStream TRADE: price=113.40625 pnl=None fees=13.35
captain-online-1 | [ONLINE] 2026-05-06 09:46:27,207 INFO main: UserStream ORDER: id=2935194612 status=2 type=2
captain-online-1 | [ONLINE] 2026-05-06 09:46:27,209 INFO main: UserStream POSITION: contract=CON.F.US.USA.M26 size=0 avgPrice=113.40625
captain-online-1 | [ONLINE] 2026-05-06 09:46:27,215 INFO main: UserStream ACCOUNT: balance=150168.93
captain-online-1 | [ONLINE] 2026-05-06 09:46:27,260 INFO main: UserStream ACCOUNT: balance=150168.93
captain-online-1 | [ONLINE] 2026-05-06 09:46:27,676 INFO main: UserStream ACCOUNT: balance=150168.93
captain-online-1 | [ONLINE] 2026-05-06 09:46:29,850 INFO main: UserStream ACCOUNT: balance=150168.93
captain-online-1 | [ONLINE] 2026-05-06 09:50:51,821 INFO captain_online.blocks.b7_shadow_monitor: Shadow resolved: MES SL_HIT SIG-AD90E5324AE5 pnl=-550.00 (theoretical)

aptain-command-1 | INFO: 127.0.0.1:60504 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:47086 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:52664 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:55764 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | [COMMAND] 2026-05-06 09:35:03,840 INFO captain_command.blocks.orchestrator: PARITY CHECK: trade_number=1, signal_parity=0, my_parity=1, skip=True, assets=['MNQ', 'MES']
captain-command-1 | INFO: 127.0.0.1:55296 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:45032 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | [COMMAND] 2026-05-06 09:36:03,166 INFO captain_command.blocks.orchestrator: PARITY CHECK: trade_number=2, signal_parity=1, my_parity=1, skip=False, assets=['MYM']
captain-command-1 | [COMMAND] 2026-05-06 09:36:03,172 INFO captain_command.blocks.orchestrator: AUTO-EXECUTE: BUY MYM x15 (account=20258288, TP=49983.0, SL=49877.0)
captain-command-1 | [COMMAND] 2026-05-06 09:36:03,432 INFO captain_command.blocks.b3_api_adapter: Bracket order: BUY MYM x15, SL=35 ticks, TP=71 ticks (tick_size=1.0, entry_est=49912)
captain-command-1 | [COMMAND] 2026-05-06 09:36:03,539 ERROR captain_command.blocks.b3_api_adapter: Bracket order FAILED (errorCode=2): Brackets cannot be used with Position Brackets. You must enable Auto OCO Brackets. [asset=MYM account=20258288 side=BUY size=15 SL_ticks=35 TP_ticks=71 entry_est=49912] — falling back to NON-OCO separate orders. Orphan SL/TP cleanup will be attempted by B7 on resolution.
captain-command-1 | [COMMAND] 2026-05-06 09:36:03,974 INFO captain_command.blocks.b3_api_adapter: TopstepX FALLBACK order PLACED: entry=2934939816 sl=2934939941 tp=2934939996 (BUY x15 @ CON.F.US.MYM.M26)
captain-command-1 | [COMMAND] 2026-05-06 09:36:03,974 INFO captain_command.blocks.orchestrator: AUTO-EXECUTE SUCCESS: order_id=2934939816 fill_price=49909.0
captain-command-1 | INFO: 127.0.0.1:57016 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:60144 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | [COMMAND] 2026-05-06 09:36:43,897 INFO captain_command.blocks.orchestrator: PARITY CHECK: trade_number=3, signal_parity=0, my_parity=1, skip=True, assets=['ZN']
captain-command-1 | INFO: 127.0.0.1:35842 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:49598 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:36732 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:56746 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:54170 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:60148 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:36092 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:38558 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:49892 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:54406 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | [COMMAND] 2026-05-06 09:42:12,945 INFO captain_command.blocks.orchestrator: PARITY CHECK: trade_number=4, signal_parity=1, my_parity=1, skip=False, assets=['ZB']
captain-command-1 | [COMMAND] 2026-05-06 09:42:12,955 INFO captain_command.blocks.orchestrator: AUTO-EXECUTE: SELL ZB x15 (account=20258288, TP=113.40625, SL=113.5)
captain-command-1 | [COMMAND] 2026-05-06 09:42:13,244 WARNING captain_command.blocks.b1_core_routing: Unknown command type: SESSION_CLOSE from user SYSTEM
captain-command-1 | [COMMAND] 2026-05-06 09:42:13,244 INFO captain_command.blocks.b3_api_adapter: Bracket order: SELL ZB x15, SL=1 ticks, TP=2 ticks (tick_size=0.03125, entry_est=113.46875)
captain-command-1 | [COMMAND] 2026-05-06 09:42:13,349 ERROR captain_command.blocks.b3_api_adapter: Bracket order FAILED (errorCode=2): Brackets cannot be used with Position Brackets. You must enable Auto OCO Brackets. [asset=ZB account=20258288 side=SELL size=15 SL_ticks=1 TP_ticks=2 entry_est=113.46875] — falling back to NON-OCO separate orders. Orphan SL/TP cleanup will be attempted by B7 on resolution.
captain-command-1 | [COMMAND] 2026-05-06 09:42:13,794 INFO captain_command.blocks.b3_api_adapter: TopstepX FALLBACK order PLACED: entry=2935091381 sl=2935091577 tp=2935091659 (SELL x15 @ CON.F.US.USA.M26)
captain-command-1 | [COMMAND] 2026-05-06 09:42:13,794 INFO captain_command.blocks.orchestrator: AUTO-EXECUTE SUCCESS: order_id=2935091381 fill_price=113.46875
captain-command-1 | INFO: 127.0.0.1:60920 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:42662 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:43748 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:48596 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:48356 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:43930 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:51264 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:36620 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:35374 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:60586 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:39784 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:41154 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:52760 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:39252 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:36576 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:55954 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:38010 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:35284 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:44150 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:60662 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:58164 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:53758 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:46474 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:46150 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:57722 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:36412 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:40282 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:59420 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 172.19.0.7:50216 - "POST /api/signals/clear HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:39386 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:50690 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:58232 - "GET /api/health HTTP/1.1" 200 OK

isaac@captain-tower-2 ~/captain-system (main)> docker compose -f docker-compose.yml -f docker-compose.local.yml logs -f captain-offline
captain-offline-1 | [OFFLINE] 2026-05-06 08:16:07,798 INFO main: Starting Captain Offline...
captain-offline-1 | [OFFLINE] 2026-05-06 08:16:07,817 INFO shared.questdb_client: QuestDB reachable (attempt 1)
captain-offline-1 | [OFFLINE] 2026-05-06 08:16:07,828 INFO main: Redis: connected
captain-offline-1 | [OFFLINE] 2026-05-06 08:16:07,831 INFO main: Redis Stream consumer groups initialized
captain-offline-1 | [OFFLINE] 2026-05-06 08:16:07,847 INFO main: Resuming from: SHUTDOWN — next: shutdown
captain-offline-1 | [OFFLINE] 2026-05-06 08:16:08,134 INFO main: AIM seed complete: 0 new rows (19 assets × 16 AIMs, 304 pre-existing)
captain-offline-1 | [OFFLINE] 2026-05-06 08:16:08,175 INFO main: Starting orchestrator (event loop + Redis subscriber)...
captain-offline-1 | [OFFLINE] 2026-05-06 08:16:08,175 INFO captain_offline.blocks.orchestrator: Offline orchestrator starting...
captain-offline-1 | [OFFLINE] 2026-05-06 08:16:09,726 INFO captain_offline.blocks.orchestrator: Restored detector state for 12 assets: ['P00-1777462589', 'P00-1777553734', 'M2K', 'MGC', 'NQ', 'MES', 'ZN', 'MNQ', 'NKD', 'ZB', 'MYM', 'ES']
captain-offline-1 | [OFFLINE] 2026-05-06 08:17:00,037 INFO captain_offline.blocks.orchestrator: Offline stream consumer groups ready
captain-offline-1 | [OFFLINE] 2026-05-06 09:36:43,900 INFO captain_offline.blocks.orchestrator: Theoretical signal outcome: ZN pnl=-312.50 (Category A learning)
captain-offline-1 | [OFFLINE] 2026-05-06 09:36:43,923 ERROR captain_offline.blocks.orchestrator: Error processing signal outcome for ZN: cannot import name 'qexecute' from 'shared.questdb_client' (/app/shared/questdb_client.py)
captain-offline-1 | Traceback (most recent call last):
captain-offline-1 | File "/app/captain_offline/blocks/orchestrator.py", line 394, in _handle_signal_outcome
captain-offline-1 | from captain_offline.blocks.b1_dma_update import run_dma_update
captain-offline-1 | File "/app/captain_offline/blocks/b1_dma_update.py", line 24, in
captain-offline-1 | from shared.questdb_client import get_cursor, qexecute
captain-offline-1 | ImportError: cannot import name 'qexecute' from 'shared.questdb_client' (/app/shared/questdb_client.py)
captain-offline-1 | [OFFLINE] 2026-05-06 09:38:01,595 INFO captain_offline.blocks.orchestrator: Theoretical signal outcome: MNQ pnl=-629.33 (Category A learning)
captain-offline-1 | [OFFLINE] 2026-05-06 09:38:01,604 ERROR captain_offline.blocks.orchestrator: Error processing signal outcome for MNQ: cannot import name 'qexecute' from 'shared.questdb_client' (/app/shared/questdb_client.py)
captain-offline-1 | Traceback (most recent call last):
captain-offline-1 | File "/app/captain_offline/blocks/orchestrator.py", line 394, in _handle_signal_outcome
captain-offline-1 | from captain_offline.blocks.b1_dma_update import run_dma_update
captain-offline-1 | File "/app/captain_offline/blocks/b1_dma_update.py", line 24, in
captain-offline-1 | from shared.questdb_client import get_cursor, qexecute
captain-offline-1 | ImportError: cannot import name 'qexecute' from 'shared.questdb_client' (/app/shared/questdb_client.py)
captain-offline-1 | [OFFLINE] 2026-05-06 09:39:16,245 ERROR captain_offline.blocks.orchestrator: Stream listener error: float() argument must be a string or a real number, not 'dict' — reconnecting in 1s
captain-offline-1 | [OFFLINE] 2026-05-06 09:39:17,247 INFO captain_offline.blocks.orchestrator: Offline stream consumer groups ready
captain-offline-1 | [OFFLINE] 2026-05-06 09:42:13,067 INFO captain_offline.blocks.orchestrator: [pg01c] session_close received session_id=1 closed_at=2026-05-06T09:42:13.014434-04:00; dispatching AIM-16 HMM training (skeleton)
captain-offline-1 | [OFFLINE] 2026-05-06 09:42:14,276 ERROR captain_offline.blocks.orchestrator: [pg01c] training dispatch failed: cannot import name 'qexecute' from 'shared.questdb_client' (/app/shared/questdb_client.py)
captain-offline-1 | Traceback (most recent call last):
captain-offline-1 | File "/app/captain_offline/blocks/orchestrator.py", line 615, in _handle_session_close
captain-offline-1 | self._run_aim16_hmm_training(session_id, closed_at)
captain-offline-1 | File "/app/captain_offline/blocks/orchestrator.py", line 631, in _run_aim16_hmm_training
captain-offline-1 | from captain_offline.blocks.b1_aim16_hmm import (
captain-offline-1 | File "/app/captain_offline/blocks/b1_aim16_hmm.py", line 35, in
captain-offline-1 | from shared.questdb_client import get_cursor, qexecute
captain-offline-1 | ImportError: cannot import name 'qexecute' from 'shared.questdb_client' (/app/shared/questdb_client.py)
captain-offline-1 | [OFFLINE] 2026-05-06 09:42:14,279 ERROR captain_offline.blocks.orchestrator: Stream listener error: float() argument must be a string or a real number, not 'dict' — reconnecting in 1s
captain-offline-1 | [OFFLINE] 2026-05-06 09:42:15,280 INFO captain_offline.blocks.orchestrator: Offline stream consumer groups ready
captain-offline-1 | [OFFLINE] 2026-05-06 09:42:16,310 INFO captain_offline.blocks.orchestrator: Theoretical signal outcome: ZB pnl=-937.50 (Category A learning)
captain-offline-1 | [OFFLINE] 2026-05-06 09:42:16,326 ERROR captain_offline.blocks.orchestrator: Error processing signal outcome for ZB: cannot import name 'qexecute' from 'shared.questdb_client' (/app/shared/questdb_client.py)
captain-offline-1 | Traceback (most recent call last):
captain-offline-1 | File "/app/captain_offline/blocks/orchestrator.py", line 394, in _handle_signal_outcome
captain-offline-1 | from captain_offline.blocks.b1_dma_update import run_dma_update
captain-offline-1 | File "/app/captain_offline/blocks/b1_dma_update.py", line 24, in
captain-offline-1 | from shared.questdb_client import get_cursor, qexecute
captain-offline-1 | ImportError: cannot import name 'qexecute' from 'shared.questdb_client' (/app/shared/questdb_client.py)
captain-offline-1 | [OFFLINE] 2026-05-06 09:50:53,809 INFO captain_offline.blocks.orchestrator: Theoretical signal outcome: MES pnl=-550.00 (Category A learning)
captain-offline-1 | [OFFLINE] 2026-05-06 09:50:53,818 ERROR captain_offline.blocks.orchestrator: Error processing signal outcome for MES: cannot import name 'qexecute' from 'shared.questdb_client' (/app/shared/questdb_client.py)
captain-offline-1 | Traceback (most recent call last):
captain-offline-1 | File "/app/captain_offline/blocks/orchestrator.py", line 394, in _handle_signal_outcome
captain-offline-1 | from captain_offline.blocks.b1_dma_update import run_dma_update
captain-offline-1 | File "/app/captain_offline/blocks/b1_dma_update.py", line 24, in
captain-offline-1 | from shared.questdb_client import get_cursor, qexecute
captain-offline-1 | ImportError: cannot import name 'qexecute' from 'shared.questdb_client' (/app/shared/questdb_client.py)


Nomaan - logs:

nomaan@captain-tower-1 ~/captain-system (main)> docker compose -f docker-compose.yml -f docker-compose.local.yml logs -f captain-online
captain-online-1 | [ONLINE] 2026-05-06 08:18:41,407 INFO main: Starting Captain Online...
captain-online-1 | [ONLINE] 2026-05-06 08:18:41,496 INFO shared.questdb_client: QuestDB reachable (attempt 1)
captain-online-1 | [ONLINE] 2026-05-06 08:18:41,502 INFO main: Redis: connected
captain-online-1 | [ONLINE] 2026-05-06 08:18:41,504 INFO main: Redis Stream consumer groups initialized
captain-online-1 | [ONLINE] 2026-05-06 08:18:41,558 INFO main: Clean restart — last checkpoint: SHUTDOWN
captain-online-1 | [ONLINE] 2026-05-06 08:18:42,478 INFO shared.topstep_client: TopstepX authenticated as nomaanakram4@gmail.com (env=LIVE)
captain-online-1 | [ONLINE] 2026-05-06 08:18:42,478 INFO main: TopstepX API: authenticated
captain-online-1 | [ONLINE] 2026-05-06 08:18:42,480 INFO main: Resolved 10 contracts: ['ES', 'MES', 'NQ', 'MNQ', 'M2K', 'MYM', 'NKD', 'MGC', 'ZB', 'ZN']
captain-online-1 | [ONLINE] 2026-05-06 08:18:42,481 INFO main: MarketStream STARTED for 10 contracts
captain-online-1 | [ONLINE] 2026-05-06 08:18:42,482 INFO pysignalr.transport: State change: disconnected -> connecting
captain-online-1 | [ONLINE] 2026-05-06 08:18:42,569 INFO pysignalr.transport: State change: disconnected -> connecting
captain-online-1 | [ONLINE] 2026-05-06 08:18:42,570 INFO main: UserStream STARTED for account 150KTC-V2-551001-86041837 (id=21855714)
captain-online-1 | [ONLINE] 2026-05-06 08:18:42,615 INFO captain_online.blocks.b9_session_controller: Session registry loaded from /captain/config/session_registry.json
captain-online-1 | [ONLINE] 2026-05-06 08:18:42,616 INFO main: Starting session orchestrator...
captain-online-1 | [ONLINE] 2026-05-06 08:18:42,616 INFO captain_online.blocks.orchestrator: Online orchestrator starting...
captain-online-1 | [ONLINE] 2026-05-06 08:18:42,647 INFO captain_online.blocks.orchestrator: Position reconciliation: no positions found in Redis
captain-online-1 | [ONLINE] 2026-05-06 08:18:42,649 INFO captain_online.blocks.orchestrator: Online command stream consumer group ready
captain-online-1 | [ONLINE] 2026-05-06 08:18:42,803 INFO pysignalr.transport: Sending handshake to server
captain-online-1 | [ONLINE] 2026-05-06 08:18:42,804 INFO pysignalr.transport: Awaiting handshake from server
captain-online-1 | [ONLINE] 2026-05-06 08:18:42,880 INFO pysignalr.transport: State change: connecting -> connected
captain-online-1 | [ONLINE] 2026-05-06 08:18:42,880 INFO shared.topstep_stream: MarketStream CONNECTED — subscribing to 10 contract(s)
captain-online-1 | [ONLINE] 2026-05-06 08:18:42,881 INFO pysignalr.transport: Sending handshake to server
captain-online-1 | [ONLINE] 2026-05-06 08:18:42,881 INFO pysignalr.transport: Awaiting handshake from server
captain-online-1 | [ONLINE] 2026-05-06 08:18:42,956 INFO pysignalr.transport: State change: connecting -> connected
captain-online-1 | [ONLINE] 2026-05-06 08:18:42,957 INFO shared.topstep_stream: UserStream CONNECTED — subscribing to account 21855714
captain-online-1 has been recreated
captain-online-1 | [ONLINE] 2026-05-06 09:22:22,508 INFO main: Shutdown signal received
captain-online-1 | [ONLINE] 2026-05-06 09:22:22,509 INFO captain_online.blocks.orchestrator: Online orchestrator stopping...
captain-online-1 | [ONLINE] 2026-05-06 09:22:22,509 INFO shared.topstep_stream: UserStream stopped for account 21855714
captain-online-1 | [ONLINE] 2026-05-06 09:22:22,510 INFO shared.topstep_stream: MarketStream stopped (10 contracts)
captain-online-1 | [ONLINE] 2026-05-06 09:22:22,561 ERROR asyncio: Task was destroyed but it is pending!
captain-online-1 | task: <Task pending name='Task-3' coro=<Connection.keepalive() done, defined at /usr/local/lib/python3.12/site-packages/websockets/asyncio/connection.py:808> wait_for=>
captain-online-1 | [ONLINE] 2026-05-06 09:22:22,562 ERROR asyncio: Task was destroyed but it is pending!
captain-online-1 | task: <Task pending name='Task-4' coro=<Connection.keepalive() done, defined at /usr/local/lib/python3.12/site-packages/websockets/asyncio/connection.py:808> wait_for=>
captain-online-1 | [ONLINE] 2026-05-06 09:22:22,562 ERROR asyncio: Task was destroyed but it is pending!
captain-online-1 | task: <Task pending name='Task-9' coro=<<async_generator_athrow without name>()>>
captain-online-1 | [ONLINE] 2026-05-06 09:22:22,562 ERROR asyncio: Task was destroyed but it is pending!
captain-online-1 | task: <Task pending name='Task-10' coro=<<async_generator_athrow without name>()>>
captain-online-1 exited with code 0
captain-online-1 | [ONLINE] 2026-05-06 09:22:24,659 INFO main: Starting Captain Online...
captain-online-1 | [ONLINE] 2026-05-06 09:22:24,672 INFO shared.questdb_client: QuestDB reachable (attempt 1)
captain-online-1 | [ONLINE] 2026-05-06 09:22:24,678 INFO main: Redis: connected
captain-online-1 | [ONLINE] 2026-05-06 09:22:24,678 INFO main: Redis Stream consumer groups initialized
captain-online-1 | [ONLINE] 2026-05-06 09:22:24,780 INFO main: Clean restart — last checkpoint: SHUTDOWN
captain-online-1 | [ONLINE] 2026-05-06 09:22:25,623 INFO shared.topstep_client: TopstepX authenticated as nomaanakram4@gmail.com (env=LIVE)
captain-online-1 | [ONLINE] 2026-05-06 09:22:25,623 INFO main: TopstepX API: authenticated
captain-online-1 | [ONLINE] 2026-05-06 09:22:25,625 INFO main: Resolved 10 contracts: ['ES', 'MES', 'NQ', 'MNQ', 'M2K', 'MYM', 'NKD', 'MGC', 'ZB', 'ZN']
captain-online-1 | [ONLINE] 2026-05-06 09:22:25,626 INFO pysignalr.transport: State change: disconnected -> connecting
captain-online-1 | [ONLINE] 2026-05-06 09:22:25,627 INFO main: MarketStream STARTED for 10 contracts
captain-online-1 | [ONLINE] 2026-05-06 09:22:25,718 INFO pysignalr.transport: State change: disconnected -> connecting
captain-online-1 | [ONLINE] 2026-05-06 09:22:25,718 INFO main: UserStream STARTED for account 150KTC-V2-551001-86041837 (id=21855714)
captain-online-1 | [ONLINE] 2026-05-06 09:22:25,801 INFO captain_online.blocks.b9_session_controller: Session registry loaded from /captain/config/session_registry.json
captain-online-1 | [ONLINE] 2026-05-06 09:22:25,803 INFO main: Starting session orchestrator...
captain-online-1 | [ONLINE] 2026-05-06 09:22:25,803 INFO captain_online.blocks.orchestrator: Online orchestrator starting...
captain-online-1 | [ONLINE] 2026-05-06 09:22:25,834 INFO captain_online.blocks.orchestrator: Position reconciliation: no positions found in Redis
captain-online-1 | [ONLINE] 2026-05-06 09:22:25,837 INFO captain_online.blocks.orchestrator: Online command stream consumer group ready
captain-online-1 | [ONLINE] 2026-05-06 09:22:25,953 INFO pysignalr.transport: Sending handshake to server
captain-online-1 | [ONLINE] 2026-05-06 09:22:25,954 INFO pysignalr.transport: Awaiting handshake from server
captain-online-1 | [ONLINE] 2026-05-06 09:22:26,031 INFO pysignalr.transport: State change: connecting -> connected
captain-online-1 | [ONLINE] 2026-05-06 09:22:26,031 INFO shared.topstep_stream: MarketStream CONNECTED — subscribing to 10 contract(s)
captain-online-1 | [ONLINE] 2026-05-06 09:22:26,033 INFO pysignalr.transport: Sending handshake to server
captain-online-1 | [ONLINE] 2026-05-06 09:22:26,035 INFO pysignalr.transport: Awaiting handshake from server
captain-online-1 | [ONLINE] 2026-05-06 09:22:26,123 INFO pysignalr.transport: State change: connecting -> connected
captain-online-1 | [ONLINE] 2026-05-06 09:22:26,123 INFO shared.topstep_stream: UserStream CONNECTED — subscribing to account 21855714
captain-online-1 | [ONLINE] 2026-05-06 09:25:00,821 INFO captain_online.blocks.orchestrator: Session NY (1) opening — beginning evaluation
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,052 INFO shared.vix_provider: VIX provider: loaded 9177 daily closes (1990-01-02 to 2026-05-04)
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,094 INFO shared.vix_provider: VXV provider: loaded 4181 daily closes (2009-09-18 to 2026-05-04)
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,258 INFO captain_online.blocks.b8_or_tracker: Session registry loaded from /captain/config/session_registry.json
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,259 INFO captain_online.blocks.b8_or_tracker: OR tracker registered: MES (NY) OR 09:30:00–09:35:00 on 2026-05-06
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,259 INFO captain_online.blocks.b8_or_tracker: OR tracker registered: MYM (NY) OR 09:30:00–09:35:00 on 2026-05-06
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,259 INFO captain_online.blocks.b8_or_tracker: OR tracker registered: ES (NY) OR 09:30:00–09:35:00 on 2026-05-06
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,259 INFO captain_online.blocks.b8_or_tracker: OR tracker registered: MGC (LON) OR 03:00:00–03:05:00 on 2026-05-06
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,259 INFO captain_online.blocks.b8_or_tracker: OR tracker registered: ZB (NY) OR 09:30:00–09:35:00 on 2026-05-06
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,261 INFO captain_online.blocks.b8_or_tracker: OR tracker registered: NKD (APAC) OR 18:00:00–18:05:00 on 2026-05-06
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,261 INFO captain_online.blocks.b8_or_tracker: OR tracker registered: M2K (NY) OR 09:30:00–09:35:00 on 2026-05-06
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,262 INFO captain_online.blocks.b8_or_tracker: OR tracker registered: MNQ (NY) OR 09:30:00–09:35:00 on 2026-05-06
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,262 INFO captain_online.blocks.b8_or_tracker: OR tracker registered: NQ (NY) OR 09:30:00–09:35:00 on 2026-05-06
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,262 INFO captain_online.blocks.b8_or_tracker: OR tracker registered: ZN (NY) OR 09:30:00–09:35:00 on 2026-05-06
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,284 INFO captain_online.blocks.b8_or_tracker: OR tracker registered: P00-1777555230 (NY) OR 09:30:00–09:35:00 on 2026-05-06
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,284 INFO captain_online.blocks.b8_or_tracker: OR tracker registered: P00-1777462581 (NY) OR 09:30:00–09:35:00 on 2026-05-06
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,284 INFO captain_online.blocks.b8_or_tracker: OR tracker registered: P00-1777462054 (NY) OR 09:30:00–09:35:00 on 2026-05-06
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,284 INFO captain_online.blocks.orchestrator: OR tracker: 13 assets registered at session open
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,303 INFO captain_online.blocks.b1_data_ingestion: ON-B1: Starting data ingestion for session NY (1)
captain-online-1 | [ONLINE] 2026-05-06 09:25:01,656 INFO captain_online.blocks.b8_or_tracker: OR FORMING: MGC — first tick 4696.2000 at 09:25:01.656314
captain-online-1 | [ONLINE] 2026-05-06 09:25:02,247 INFO captain_online.blocks.b8_or_tracker: OR COMPLETE: MGC — high=4696.2000 low=4696.2000 range=0.0000 (1 ticks)
captain-online-1 | [ONLINE] 2026-05-06 09:25:02,247 INFO captain_online.blocks.b8_or_tracker: OR BREAKOUT LONG: MGC — price=4696.6000 > OR high=4696.2000, or_range=0.0000
captain-online-1 | [ONLINE] 2026-05-06 09:25:05,002 INFO captain_online.blocks.b1_data_ingestion: ON-B1: 8 assets eligible for session NY
captain-online-1 | [ONLINE] 2026-05-06 09:25:05,003 INFO captain_online.blocks.b1_data_ingestion: ON-B1: System timezone check passed (local: America/New_York)
captain-online-1 | [ONLINE] 2026-05-06 09:25:09,858 INFO captain_online.blocks.b1_features: ON-B1A: Options data unavailable (TopstepX futures-only) — AIM-02 pcr/put_skew and AIM-03 gex features will output neutral
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,495 INFO captain_online.blocks.b1_data_ingestion: ON-B1: Data ingestion complete. 8 active assets, 158 features computed
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,501 INFO captain_online.blocks.b2_regime_probability: ON-B2: Regime uncertainty for MES: max_prob=0.500 — robust Kelly will be used
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,501 INFO captain_online.blocks.b2_regime_probability: ON-B2: Regime uncertainty for MYM: max_prob=0.500 — robust Kelly will be used
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,501 INFO captain_online.blocks.b2_regime_probability: ON-B2: Regime uncertainty for ES: max_prob=0.500 — robust Kelly will be used
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,501 INFO captain_online.blocks.b2_regime_probability: ON-B2: Regime uncertainty for ZB: max_prob=0.500 — robust Kelly will be used
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,501 INFO captain_online.blocks.b2_regime_probability: ON-B2: Regime uncertainty for M2K: max_prob=0.500 — robust Kelly will be used
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,501 INFO captain_online.blocks.b2_regime_probability: ON-B2: Regime uncertainty for MNQ: max_prob=0.500 — robust Kelly will be used
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,501 INFO captain_online.blocks.b2_regime_probability: ON-B2: Regime uncertainty for NQ: max_prob=0.500 — robust Kelly will be used
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,501 INFO captain_online.blocks.b2_regime_probability: ON-B2: Regime uncertainty for ZN: max_prob=0.500 — robust Kelly will be used
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,501 INFO captain_online.blocks.b2_regime_probability: ON-B2: Regime probabilities computed for 8 assets (8 uncertain)
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,520 INFO shared.aim_compute: AIM MES: AIM-04(IVTS)=0.900×0.167 | AIM-06(EconCal)=1.000×0.167 | AIM-08(CrossCorr)=1.000×0.167 | AIM-11(RegimeWarn)=1.000×0.167 | AIM-12(DynCosts)=1.000×0.167 | AIM-15(OpenVol)=1.000×0.167
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,520 INFO shared.aim_compute: AIM MYM: AIM-04(IVTS)=0.900×0.167 | AIM-06(EconCal)=1.000×0.167 | AIM-08(CrossCorr)=0.800×0.167 | AIM-11(RegimeWarn)=1.000×0.167 | AIM-12(DynCosts)=0.950×0.167 | AIM-15(OpenVol)=1.000×0.167
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,520 INFO shared.aim_compute: AIM ES: AIM-04(IVTS)=0.900×0.167 | AIM-06(EconCal)=1.000×0.167 | AIM-08(CrossCorr)=1.000×0.167 | AIM-11(RegimeWarn)=1.000×0.167 | AIM-12(DynCosts)=1.000×0.167 | AIM-15(OpenVol)=1.000×0.167
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,520 INFO shared.aim_compute: AIM ZB: AIM-04(IVTS)=0.900×0.167 | AIM-06(EconCal)=1.000×0.167 | AIM-08(CrossCorr)=1.000×0.167 | AIM-11(RegimeWarn)=1.000×0.167 | AIM-12(DynCosts)=1.000×0.167 | AIM-15(OpenVol)=1.000×0.167
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,520 INFO shared.aim_compute: AIM M2K: AIM-04(IVTS)=0.900×0.167 | AIM-06(EconCal)=1.000×0.167 | AIM-08(CrossCorr)=0.900×0.167 | AIM-11(RegimeWarn)=1.000×0.167 | AIM-12(DynCosts)=1.000×0.167 | AIM-15(OpenVol)=1.000×0.167
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,520 INFO shared.aim_compute: AIM MNQ: AIM-04(IVTS)=0.900×0.167 | AIM-06(EconCal)=1.000×0.167 | AIM-08(CrossCorr)=0.800×0.167 | AIM-11(RegimeWarn)=1.000×0.167 | AIM-12(DynCosts)=1.000×0.167 | AIM-15(OpenVol)=1.000×0.167
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,520 INFO shared.aim_compute: AIM NQ: AIM-04(IVTS)=0.900×0.167 | AIM-06(EconCal)=1.000×0.167 | AIM-08(CrossCorr)=0.800×0.167 | AIM-11(RegimeWarn)=1.000×0.167 | AIM-12(DynCosts)=1.000×0.167 | AIM-15(OpenVol)=1.000×0.167
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,520 INFO shared.aim_compute: AIM ZN: AIM-04(IVTS)=0.855×0.167 | AIM-06(EconCal)=1.000×0.167 | AIM-08(CrossCorr)=1.000×0.167 | AIM-11(RegimeWarn)=1.000×0.167 | AIM-12(DynCosts)=1.000×0.167 | AIM-15(OpenVol)=1.000×0.167
captain-online-1 | [ONLINE] 2026-05-06 09:25:10,521 INFO shared.aim_compute: AIM aggregation: 8 assets, 8 with active AIMs, 48 individual AIMs computed
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,043 INFO captain_online.blocks.hmm_inference_block: [aim16-online] D26 inference persist session_id=1 opp={'NY': 0.3162721139793589, 'LON': 0.36745577204128177, 'APAC': 0.31627211397935934} schema=1
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,107 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: Kelly sizing for user primary_user (1 accounts, 8 assets)
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,111 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: pass_probability absent for account 21855714 (PASS_EVAL) — using default 0.85 Kelly multiplier; seed pass_probability once ≥30 Pseudotrader sessions exist
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,114 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: evaluation_end_date absent for account 21855714 — using default budget_divisor=10 (open-ended combine; no fixed deadline)
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,115 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: max_daily_loss absent for account 21855714 — max_by_mll=999 (no MLL on this combine; MDD-only risk limit applies)
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,115 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: MES ac=21855714 kelly=0.0845→0.0718(rg)→547.8(raw) risk/c=19.7 cap=150000 tsm=15 topstep=999 scale=999 → 15 contracts [TRADE]
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,117 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: pass_probability absent for account 21855714 (PASS_EVAL) — using default 0.85 Kelly multiplier; seed pass_probability once ≥30 Pseudotrader sessions exist
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,117 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: evaluation_end_date absent for account 21855714 — using default budget_divisor=10 (open-ended combine; no fixed deadline)
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,117 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: max_daily_loss absent for account 21855714 — max_by_mll=999 (no MLL on this combine; MDD-only risk limit applies)
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,117 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: MYM ac=21855714 kelly=0.0908→0.0772(rg)→412.4(raw) risk/c=28.1 cap=150000 tsm=15 topstep=999 scale=999 → 15 contracts [TRADE]
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,119 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: pass_probability absent for account 21855714 (PASS_EVAL) — using default 0.85 Kelly multiplier; seed pass_probability once ≥30 Pseudotrader sessions exist
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,119 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: evaluation_end_date absent for account 21855714 — using default budget_divisor=10 (open-ended combine; no fixed deadline)
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,119 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: max_daily_loss absent for account 21855714 — max_by_mll=999 (no MLL on this combine; MDD-only risk limit applies)
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,119 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: ES ac=21855714 kelly=0.0382→0.0325(rg)→25.5(raw) risk/c=191.2 cap=150000 tsm=2 topstep=999 scale=999 → 2 contracts [TRADE]
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,121 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: pass_probability absent for account 21855714 (PASS_EVAL) — using default 0.85 Kelly multiplier; seed pass_probability once ≥30 Pseudotrader sessions exist
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,121 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: evaluation_end_date absent for account 21855714 — using default budget_divisor=10 (open-ended combine; no fixed deadline)
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,121 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: max_daily_loss absent for account 21855714 — max_by_mll=999 (no MLL on this combine; MDD-only risk limit applies)
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,121 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: ZB ac=21855714 kelly=0.1208→0.1027(rg)→690.1(raw) risk/c=22.3 cap=150000 tsm=15 topstep=999 scale=999 → 15 contracts [TRADE]
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,123 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: pass_probability absent for account 21855714 (PASS_EVAL) — using default 0.85 Kelly multiplier; seed pass_probability once ≥30 Pseudotrader sessions exist
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,123 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: evaluation_end_date absent for account 21855714 — using default budget_divisor=10 (open-ended combine; no fixed deadline)
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,123 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: max_daily_loss absent for account 21855714 — max_by_mll=999 (no MLL on this combine; MDD-only risk limit applies)
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,123 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: M2K ac=21855714 kelly=0.0674→0.0573(rg)→421.1(raw) risk/c=20.4 cap=150000 tsm=15 topstep=999 scale=999 → 15 contracts [TRADE]
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,125 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: pass_probability absent for account 21855714 (PASS_EVAL) — using default 0.85 Kelly multiplier; seed pass_probability once ≥30 Pseudotrader sessions exist
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,125 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: evaluation_end_date absent for account 21855714 — using default budget_divisor=10 (open-ended combine; no fixed deadline)
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,126 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: max_daily_loss absent for account 21855714 — max_by_mll=999 (no MLL on this combine; MDD-only risk limit applies)
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,126 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: MNQ ac=21855714 kelly=0.0658→0.0559(rg)→154.0(raw) risk/c=54.5 cap=150000 tsm=8 topstep=999 scale=999 → 8 contracts [TRADE]
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,127 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: pass_probability absent for account 21855714 (PASS_EVAL) — using default 0.85 Kelly multiplier; seed pass_probability once ≥30 Pseudotrader sessions exist
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,127 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: evaluation_end_date absent for account 21855714 — using default budget_divisor=10 (open-ended combine; no fixed deadline)
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,127 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: max_daily_loss absent for account 21855714 — max_by_mll=999 (no MLL on this combine; MDD-only risk limit applies)
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,127 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: NQ ac=21855714 kelly=0.0724→0.0616(rg)→17.4(raw) risk/c=531.3 cap=150000 tsm=0 topstep=999 scale=999 → 0 contracts [SKIP]
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,129 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: pass_probability absent for account 21855714 (PASS_EVAL) — using default 0.85 Kelly multiplier; seed pass_probability once ≥30 Pseudotrader sessions exist
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,129 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: evaluation_end_date absent for account 21855714 — using default budget_divisor=10 (open-ended combine; no fixed deadline)
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,129 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: max_daily_loss absent for account 21855714 — max_by_mll=999 (no MLL on this combine; MDD-only risk limit applies)
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,129 INFO captain_online.blocks.b4_kelly_sizing: ON-B4: ZN ac=21855714 kelly=0.1338→0.1137(rg)→1401.7(raw) risk/c=12.2 cap=150000 tsm=15 topstep=999 scale=999 → 15 contracts [TRADE]
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,132 INFO captain_online.blocks.b5_trade_selection: ON-B5: Trade selection for user primary_user: 5/8 assets selected
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,133 INFO captain_online.blocks.b5_trade_selection: ON-B5 HMM: session=NY weight=0.316 regime=HMM_FULL n_obs=240 (observability-only; budget enforcement at B4/B5C)
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,143 INFO captain_online.blocks.b5b_quality_gate: ON-B5B: Quality gate for user primary_user: 5 recommended, 0 below threshold
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,155 WARNING captain_online.blocks.b5c_circuit_breaker: ON-B5C: L1 falling back to live L_halt=1500.00000 for 21855714 session=1 (no SOD per-session value)
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,155 WARNING captain_online.blocks.b5c_circuit_breaker: ON-B5C: L2 falling back to live E=1500.0000 for 21855714 session=1 (no SOD per-session value)
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,164 WARNING captain_online.blocks.b5c_circuit_breaker: ON-B5C: L1 falling back to live L_halt=1500.00000 for 21855714 session=1 (no SOD per-session value)
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,165 WARNING captain_online.blocks.b5c_circuit_breaker: ON-B5C: L2 falling back to live E=1500.0000 for 21855714 session=1 (no SOD per-session value)
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,174 WARNING captain_online.blocks.b5c_circuit_breaker: ON-B5C: L1 falling back to live L_halt=1500.00000 for 21855714 session=1 (no SOD per-session value)
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,174 WARNING captain_online.blocks.b5c_circuit_breaker: ON-B5C: L2 falling back to live E=1500.0000 for 21855714 session=1 (no SOD per-session value)
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,184 WARNING captain_online.blocks.b5c_circuit_breaker: ON-B5C: L1 falling back to live L_halt=1500.00000 for 21855714 session=1 (no SOD per-session value)
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,184 WARNING captain_online.blocks.b5c_circuit_breaker: ON-B5C: L2 falling back to live E=1500.0000 for 21855714 session=1 (no SOD per-session value)
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,189 WARNING captain_online.blocks.b5c_circuit_breaker: ON-B5C: L1 falling back to live L_halt=1500.00000 for 21855714 session=1 (no SOD per-session value)
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,189 WARNING captain_online.blocks.b5c_circuit_breaker: ON-B5C: L2 falling back to live E=1500.0000 for 21855714 session=1 (no SOD per-session value)
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,202 INFO captain_online.blocks.orchestrator: Phase A — user primary_user: 5 recommended, 0 below threshold
captain-online-1 | [ONLINE] 2026-05-06 09:25:11,202 INFO captain_online.blocks.orchestrator: Phase A complete for NY — 8 assets tracked, 1 user(s) pending Phase B
captain-online-1 | [ONLINE] 2026-05-06 09:30:00,048 INFO captain_online.blocks.b8_or_tracker: OR FORMING: NQ — first tick 28389.2500 at 09:30:00.048163
captain-online-1 | [ONLINE] 2026-05-06 09:30:00,048 INFO captain_online.blocks.b8_or_tracker: OR FORMING: ES — first tick 7331.2500 at 09:30:00.048358
captain-online-1 | [ONLINE] 2026-05-06 09:30:00,049 INFO captain_online.blocks.b8_or_tracker: OR FORMING: MNQ — first tick 28389.7500 at 09:30:00.049663
captain-online-1 | [ONLINE] 2026-05-06 09:30:00,114 INFO captain_online.blocks.b8_or_tracker: OR FORMING: M2K — first tick 2879.9000 at 09:30:00.114347
captain-online-1 | [ONLINE] 2026-05-06 09:30:00,114 INFO captain_online.blocks.b8_or_tracker: OR FORMING: MES — first tick 7330.7500 at 09:30:00.114456
captain-online-1 | [ONLINE] 2026-05-06 09:30:00,130 INFO captain_online.blocks.b8_or_tracker: OR FORMING: MYM — first tick 49820.0000 at 09:30:00.130923
captain-online-1 | [ONLINE] 2026-05-06 09:30:00,299 INFO captain_online.blocks.b8_or_tracker: OR FORMING: ZN — first tick 110.7344 at 09:30:00.299661
captain-online-1 | [ONLINE] 2026-05-06 09:30:00,654 INFO captain_online.blocks.b8_or_tracker: OR FORMING: ZB — first tick 113.5312 at 09:30:00.654695
captain-online-1 | [ONLINE] 2026-05-06 09:35:00,045 INFO captain_online.blocks.b8_or_tracker: OR COMPLETE: NQ — high=28446.5000 low=28337.0000 range=109.5000 (4077 ticks)
captain-online-1 | [ONLINE] 2026-05-06 09:35:00,046 INFO captain_online.blocks.b8_or_tracker: OR COMPLETE: MNQ — high=28446.5000 low=28336.7500 range=109.7500 (5537 ticks)
captain-online-1 | [ONLINE] 2026-05-06 09:35:00,099 INFO captain_online.blocks.b8_or_tracker: OR COMPLETE: ES — high=7341.0000 low=7327.2500 range=13.7500 (3264 ticks)
captain-online-1 | [ONLINE] 2026-05-06 09:35:00,099 INFO captain_online.blocks.b8_or_tracker: OR COMPLETE: MES — high=7341.2500 low=7327.2500 range=14.0000 (3391 ticks)
captain-online-1 | [ONLINE] 2026-05-06 09:35:00,102 INFO captain_online.blocks.b8_or_tracker: OR COMPLETE: MYM — high=49910.0000 low=49808.0000 range=102.0000 (2318 ticks)
captain-online-1 | [ONLINE] 2026-05-06 09:35:00,199 INFO captain_online.blocks.b8_or_tracker: OR COMPLETE: M2K — high=2881.2000 low=2873.5000 range=7.7000 (1587 ticks)
captain-online-1 | [ONLINE] 2026-05-06 09:35:00,395 INFO captain_online.blocks.b8_or_tracker: OR BREAKOUT LONG: NQ — price=28447.0000 > OR high=28446.5000, or_range=109.5000
captain-online-1 | [ONLINE] 2026-05-06 09:35:00,396 INFO captain_online.blocks.b8_or_tracker: OR BREAKOUT LONG: ES — price=7341.5000 > OR high=7341.0000, or_range=13.7500
captain-online-1 | [ONLINE] 2026-05-06 09:35:00,496 INFO captain_online.blocks.b8_or_tracker: OR BREAKOUT LONG: MES — price=7341.5000 > OR high=7341.2500, or_range=14.0000
captain-online-1 | [ONLINE] 2026-05-06 09:35:00,748 INFO captain_online.blocks.b8_or_tracker: OR BREAKOUT LONG: MNQ — price=28446.7500 > OR high=28446.5000, or_range=109.7500
captain-online-1 | [ONLINE] 2026-05-06 09:35:01,249 INFO captain_online.blocks.b8_or_tracker: OR COMPLETE: ZB — high=113.5938 low=113.5000 range=0.0938 (87 ticks)
captain-online-1 | [ONLINE] 2026-05-06 09:35:01,493 INFO captain_online.blocks.b1_features: Stored daily OHLCV for MNQ: close=28208.00
captain-online-1 | [ONLINE] 2026-05-06 09:35:01,602 INFO captain_online.blocks.b1_features: Stored opening vol for MNQ: 0.000791
captain-online-1 | [ONLINE] 2026-05-06 09:35:01,963 INFO captain_online.blocks.b1_features: Stored daily OHLCV for ES: close=7295.50
captain-online-1 | [ONLINE] 2026-05-06 09:35:02,058 INFO captain_online.blocks.b1_features: Stored opening vol for ES: 0.000337
captain-online-1 | [ONLINE] 2026-05-06 09:35:02,150 INFO captain_online.blocks.b8_or_tracker: OR COMPLETE: ZN — high=110.7656 low=110.7344 range=0.0312 (123 ticks)
captain-online-1 | [ONLINE] 2026-05-06 09:35:02,612 INFO captain_online.blocks.b1_features: Stored daily OHLCV for NQ: close=28207.25
captain-online-1 | [ONLINE] 2026-05-06 09:35:02,705 INFO captain_online.blocks.b1_features: Stored opening vol for NQ: 0.000805
captain-online-1 | [ONLINE] 2026-05-06 09:35:03,057 INFO captain_online.blocks.b1_features: Stored daily OHLCV for MES: close=7295.75
captain-online-1 | [ONLINE] 2026-05-06 09:35:03,233 INFO captain_online.blocks.b1_features: Stored opening vol for MES: 0.000346
captain-online-1 | [ONLINE] 2026-05-06 09:35:03,268 INFO captain_online.blocks.b6_signal_output: ON-B6-SUMMARY user=primary_user session=1 recommended=2 built=2 below_threshold=0
captain-online-1 | [ONLINE] 2026-05-06 09:35:03,271 INFO captain_online.blocks.b6_signal_output: ON-B6: 2 signals published for user primary_user (session 1), 0 below threshold
captain-online-1 | [ONLINE] 2026-05-06 09:35:03,285 INFO captain_online.blocks.orchestrator: Phase B: generated signals for ['MNQ', 'ES', 'NQ', 'MES']
captain-online-1 | [ONLINE] 2026-05-06 09:35:05,849 INFO captain_online.blocks.b8_or_tracker: OR BREAKOUT LONG: M2K — price=2881.4000 > OR high=2881.2000, or_range=7.7000
captain-online-1 | [ONLINE] 2026-05-06 09:35:07,160 INFO captain_online.blocks.b1_features: Stored daily OHLCV for M2K: close=2849.30
captain-online-1 | [ONLINE] 2026-05-06 09:35:07,255 INFO captain_online.blocks.b1_features: Stored opening vol for M2K: 0.000582
captain-online-1 | [ONLINE] 2026-05-06 09:35:07,256 WARNING captain_online.blocks.orchestrator: ON-B6-SKIP user=primary_user session=1 assets_filter=['M2K'] recommended_trades=['ZB', 'ZN', 'MNQ', 'MYM', 'MES'] account_skip_reason={'MES': {'21855714': None}, 'MYM': {'21855714': None}, 'ES': {'21855714': 'Removed by portfolio-level constraint (correlation or position limit)'}, 'ZB': {'21855714': None}, 'M2K': {'21855714': 'Removed by portfolio-level constraint (correlation or position limit)'}, 'MNQ': {'21855714': None}, 'NQ': {'21855714': 'Position size rounded to 0'}, 'ZN': {'21855714': None}} — B6 short-circuited (no candidates)
captain-online-1 | [ONLINE] 2026-05-06 09:35:07,257 INFO captain_online.blocks.orchestrator: Phase B: generated signals for ['M2K']
captain-online-1 | [ONLINE] 2026-05-06 09:36:01,802 INFO captain_online.blocks.b8_or_tracker: OR BREAKOUT LONG: MYM — price=49912.0000 > OR high=49910.0000, or_range=102.0000
captain-online-1 | [ONLINE] 2026-05-06 09:36:02,879 INFO captain_online.blocks.b1_features: Stored daily OHLCV for MYM: close=49393.00
captain-online-1 | [ONLINE] 2026-05-06 09:36:02,971 INFO captain_online.blocks.b1_features: Stored opening vol for MYM: 0.000549
captain-online-1 | [ONLINE] 2026-05-06 09:36:02,977 INFO captain_online.blocks.b6_signal_output: ON-B6-SUMMARY user=primary_user session=1 recommended=1 built=1 below_threshold=0
captain-online-1 | [ONLINE] 2026-05-06 09:36:02,988 INFO captain_online.blocks.b6_signal_output: ON-B6: 1 signals published for user primary_user (session 1), 0 below threshold
captain-online-1 | [ONLINE] 2026-05-06 09:36:02,990 INFO captain_online.blocks.orchestrator: Phase B: generated signals for ['MYM']
captain-online-1 | [ONLINE] 2026-05-06 09:36:03,321 WARNING shared.topstep_stream: UserStream RAW order args=([{'action': 1, 'data': {'id': 2934939667, 'accountId': 21855714, 'contractId': 'CON.F.US.MYM.M26', 'symbolId': 'F.US.MYM', 'creationTimestamp': '2026-05-06T13:36:03.2647798+00:00', 'updateTimestamp': '2026-05-06T13:36:03.2647798+00:00', 'status': 6, 'type': 2, 'side': 0, 'size': 15, 'fillVolume': 0}}],) type=list
captain-online-1 | [ONLINE] 2026-05-06 09:36:03,322 INFO main: UserStream ORDER: id=2934939667 status=6 type=2
captain-online-1 | [ONLINE] 2026-05-06 09:36:03,322 WARNING main: UserStream ORDER REJECTED: id=2934939667 data={'id': 2934939667, 'accountId': 21855714, 'contractId': 'CON.F.US.MYM.M26', 'symbolId': 'F.US.MYM', 'creationTimestamp': '2026-05-06T13:36:03.2647798+00:00', 'updateTimestamp': '2026-05-06T13:36:03.2647798+00:00', 'status': 6, 'type': 2, 'side': 0, 'size': 15, 'fillVolume': 0}
captain-online-1 | [ONLINE] 2026-05-06 09:36:03,324 INFO main: UserStream ORDER: id=2934939669 status=8 type=4
captain-online-1 | [ONLINE] 2026-05-06 09:36:03,325 INFO main: UserStream ORDER: id=2934939670 status=8 type=1
captain-online-1 | [ONLINE] 2026-05-06 09:36:03,330 WARNING shared.topstep_stream: UserStream RAW trade args=([{'action': 0, 'data': {'id': 2555492434, 'accountId': 21855714, 'contractId': 'CON.F.US.MYM.M26', 'creationTimestamp': '2026-05-06T13:36:03.2874814+00:00', 'price': 49909, 'fees': 5.55, 'commissions': 3.75, 'side': 0, 'size': 15, 'voided': False, 'orderId': 2934939667}}],) type=list
captain-online-1 | [ONLINE] 2026-05-06 09:36:03,331 INFO main: UserStream TRADE: price=49909 pnl=None fees=5.55
captain-online-1 | [ONLINE] 2026-05-06 09:36:03,332 INFO main: UserStream ORDER: id=2934939667 status=2 type=2
captain-online-1 | [ONLINE] 2026-05-06 09:36:03,337 WARNING shared.topstep_stream: UserStream RAW position args=([{'action': 1, 'data': {'id': 703034461, 'accountId': 21855714, 'contractId': 'CON.F.US.MYM.M26', 'contractDisplayName': 'MYMM26', 'creationTimestamp': '2026-05-06T13:36:03.2936136+00:00', 'type': 1, 'size': 15, 'averagePrice': 49909}}],) type=list
captain-online-1 | [ONLINE] 2026-05-06 09:36:03,337 INFO main: UserStream POSITION: contract=CON.F.US.MYM.M26 size=15 avgPrice=49909
captain-online-1 | [ONLINE] 2026-05-06 09:36:03,343 WARNING shared.topstep_stream: UserStream RAW account args=([{'action': 1, 'data': {'id': 21855714, 'name': '150KTC-V2-551001-86041837', 'balance': 150051.73, 'canTrade': True, 'isVisible': True, 'simulated': True}}],) type=list
captain-online-1 | [ONLINE] 2026-05-06 09:36:03,343 INFO main: UserStream ACCOUNT: balance=150051.73
captain-online-1 | [ONLINE] 2026-05-06 09:36:03,347 INFO main: UserStream ORDER: id=2934939669 status=1 type=4
captain-online-1 | [ONLINE] 2026-05-06 09:36:03,348 INFO main: UserStream ORDER: id=2934939670 status=1 type=1
captain-online-1 | [ONLINE] 2026-05-06 09:36:03,438 INFO captain_online.blocks.orchestrator: Position opened: MYM for user primary_user (15 contracts)
captain-online-1 | [ONLINE] 2026-05-06 09:36:04,069 INFO main: UserStream ACCOUNT: balance=150051.73
captain-online-1 | [ONLINE] 2026-05-06 09:36:43,046 INFO captain_online.blocks.b8_or_tracker: OR BREAKOUT LONG: ZN — price=110.7812 > OR high=110.7656, or_range=0.0312
captain-online-1 | [ONLINE] 2026-05-06 09:36:43,556 INFO captain_online.blocks.b1_features: Stored daily OHLCV for ZN: close=110.27
captain-online-1 | [ONLINE] 2026-05-06 09:36:43,645 INFO captain_online.blocks.b1_features: Stored opening vol for ZN: 0.000081
captain-online-1 | [ONLINE] 2026-05-06 09:36:43,652 INFO captain_online.blocks.b6_signal_output: ON-B6-SUMMARY user=primary_user session=1 recommended=1 built=1 below_threshold=0
captain-online-1 | [ONLINE] 2026-05-06 09:36:43,656 INFO captain_online.blocks.b6_signal_output: ON-B6: 1 signals published for user primary_user (session 1), 0 below threshold
captain-online-1 | [ONLINE] 2026-05-06 09:36:43,660 INFO captain_online.blocks.orchestrator: Phase B: generated signals for ['ZN']
captain-online-1 | [ONLINE] 2026-05-06 09:36:43,661 INFO captain_online.blocks.b7_shadow_monitor: Shadow resolved: ZN SL_HIT SIG-0ACBEC9745FE pnl=-312.50 (theoretical)
captain-online-1 | [ONLINE] 2026-05-06 09:38:01,213 INFO captain_online.blocks.b7_shadow_monitor: Shadow resolved: MNQ SL_HIT SIG-3FF4EE9A1B09 pnl=-625.33 (theoretical)
captain-online-1 | [ONLINE] 2026-05-06 09:38:30,951 INFO main: UserStream ORDER: id=2934939670 status=2 type=1
captain-online-1 | [ONLINE] 2026-05-06 09:38:30,952 INFO main: UserStream TRADE: price=49980 pnl=532.5 fees=5.55
captain-online-1 | [ONLINE] 2026-05-06 09:38:30,953 INFO main: UserStream TRADE: price=49909.0 pnl=None fees=5.55
captain-online-1 | [ONLINE] 2026-05-06 09:38:30,958 INFO main: UserStream POSITION: contract=CON.F.US.MYM.M26 size=0 avgPrice=49909.0
captain-online-1 | [ONLINE] 2026-05-06 09:38:30,964 INFO main: UserStream ACCOUNT: balance=150574.93
captain-online-1 | [ONLINE] 2026-05-06 09:38:30,969 INFO main: UserStream ORDER: id=2934939669 status=3 type=4
captain-online-1 | [ONLINE] 2026-05-06 09:38:34,428 INFO main: UserStream ACCOUNT: balance=150574.93
captain-online-1 | [ONLINE] 2026-05-06 09:39:16,000 WARNING captain_online.blocks.b7_position_monitor: ON-B7: cannot resolve int account_id for MYM — falling back to polled price for exit (account=21855714)
captain-online-1 | [ONLINE] 2026-05-06 09:39:16,064 INFO captain_online.blocks.b7_position_monitor: ON-B7: Published trade outcome TRD-17315DE23E16 to stream
captain-online-1 | [ONLINE] 2026-05-06 09:39:16,064 INFO captain_online.blocks.b7_position_monitor: ON-B7: Position resolved — MYM TP_HIT primary_user net_pnl=618.90 trade_id=TRD-17315DE23E16
captain-online-1 | [ONLINE] 2026-05-06 09:42:11,698 INFO captain_online.blocks.b8_or_tracker: OR BREAKOUT SHORT: ZB — price=113.4688 < OR low=113.5000, or_range=0.0938
captain-online-1 | [ONLINE] 2026-05-06 09:42:12,510 INFO captain_online.blocks.b1_features: Stored daily OHLCV for ZB: close=112.66
captain-online-1 | [ONLINE] 2026-05-06 09:42:12,601 INFO captain_online.blocks.b1_features: Stored opening vol for ZB: 0.000138
captain-online-1 | [ONLINE] 2026-05-06 09:42:12,605 INFO captain_online.blocks.b6_signal_output: ON-B6-SUMMARY user=primary_user session=1 recommended=1 built=1 below_threshold=0
captain-online-1 | [ONLINE] 2026-05-06 09:42:12,614 INFO captain_online.blocks.b6_signal_output: ON-B6: 1 signals published for user primary_user (session 1), 0 below threshold
captain-online-1 | [ONLINE] 2026-05-06 09:42:12,617 INFO captain_online.blocks.orchestrator: Phase B: generated signals for ['ZB']
captain-online-1 | [ONLINE] 2026-05-06 09:42:12,635 INFO captain_online.blocks.b9_capacity_evaluation: ON-B9: Capacity eval — supply ratio=85.0, quality rate=100%, 1 constraints
captain-online-1 | [ONLINE] 2026-05-06 09:42:12,635 INFO captain_online.blocks.orchestrator: Session NY Phase B complete — all assets resolved
captain-online-1 | [ONLINE] 2026-05-06 09:42:12,652 INFO captain_online.blocks.b7_shadow_monitor: Shadow resolved: ZB SL_HIT SIG-75117AE16859 pnl=-937.50 (theoretical)
captain-online-1 | [ONLINE] 2026-05-06 09:42:12,923 INFO main: UserStream ORDER: id=2935091141 status=6 type=2
captain-online-1 | [ONLINE] 2026-05-06 09:42:12,923 WARNING main: UserStream ORDER REJECTED: id=2935091141 data={'id': 2935091141, 'accountId': 21855714, 'contractId': 'CON.F.US.USA.M26', 'symbolId': 'F.US.USA', 'creationTimestamp': '2026-05-06T13:42:12.8821461+00:00', 'updateTimestamp': '2026-05-06T13:42:12.8821461+00:00', 'status': 6, 'type': 2, 'side': 1, 'size': 15, 'fillVolume': 0}
captain-online-1 | [ONLINE] 2026-05-06 09:42:12,926 INFO main: UserStream ORDER: id=2935091141 status=5 type=2
captain-online-1 | [ONLINE] 2026-05-06 09:42:13,018 INFO main: UserStream ORDER: id=2935091179 status=6 type=2
captain-online-1 | [ONLINE] 2026-05-06 09:42:13,019 WARNING main: UserStream ORDER REJECTED: id=2935091179 data={'id': 2935091179, 'accountId': 21855714, 'contractId': 'CON.F.US.USA.M26', 'symbolId': 'F.US.USA', 'creationTimestamp': '2026-05-06T13:42:12.9771494+00:00', 'updateTimestamp': '2026-05-06T13:42:12.9771494+00:00', 'status': 6, 'type': 2, 'side': 1, 'size': 15, 'fillVolume': 0}
captain-online-1 | [ONLINE] 2026-05-06 09:42:13,038 INFO main: UserStream ORDER: id=2935091179 status=2 type=2
captain-online-1 | [ONLINE] 2026-05-06 09:42:13,039 INFO main: UserStream TRADE: price=113.46875 pnl=None fees=13.35
captain-online-1 | [ONLINE] 2026-05-06 09:42:13,043 INFO main: UserStream POSITION: contract=CON.F.US.USA.M26 size=15 avgPrice=113.46875
captain-online-1 | [ONLINE] 2026-05-06 09:42:13,046 INFO main: UserStream ACCOUNT: balance=150554.08
captain-online-1 | [ONLINE] 2026-05-06 09:42:13,222 INFO main: UserStream ORDER: id=2935091274 status=1 type=4
captain-online-1 | [ONLINE] 2026-05-06 09:42:13,334 INFO captain_online.blocks.orchestrator: Position opened: ZB for user primary_user (15 contracts)
captain-online-1 | [ONLINE] 2026-05-06 09:42:13,335 INFO main: UserStream ORDER: id=2935091319 status=1 type=1
captain-online-1 | [ONLINE] 2026-05-06 09:42:13,772 ERROR captain_online.blocks.b7_position_monitor: ON-B7: cannot cancel orphan brackets for ZB — account_id unresolved (account=21855714)
captain-online-1 | [ONLINE] 2026-05-06 09:42:13,836 INFO captain_online.blocks.b7_position_monitor: ON-B7: Published trade outcome TRD-06D1A31AA9FC to stream
captain-online-1 | [ONLINE] 2026-05-06 09:42:13,836 INFO captain_online.blocks.b7_position_monitor: ON-B7: Position resolved — ZB SL_HIT primary_user net_pnl=-502.65 trade_id=TRD-06D1A31AA9FC
captain-online-1 | [ONLINE] 2026-05-06 09:42:13,882 INFO main: UserStream TRADE: price=113.46875 pnl=None fees=13.35
captain-online-1 | [ONLINE] 2026-05-06 09:42:13,883 INFO main: UserStream TRADE: price=113.5 pnl=-468.75 fees=13.35
captain-online-1 | [ONLINE] 2026-05-06 09:42:13,883 INFO main: UserStream ORDER: id=2935091274 status=2 type=4
captain-online-1 | [ONLINE] 2026-05-06 09:42:13,889 INFO main: UserStream POSITION: contract=CON.F.US.USA.M26 size=0 avgPrice=113.46875
captain-online-1 | [ONLINE] 2026-05-06 09:42:13,895 INFO main: UserStream ACCOUNT: balance=150064.48
captain-online-1 | [ONLINE] 2026-05-06 09:42:14,209 INFO main: UserStream ACCOUNT: balance=150064.48
captain-online-1 | [ONLINE] 2026-05-06 09:45:35,533 INFO main: UserStream ORDER: id=2935091319 status=2 type=1
captain-online-1 | [ONLINE] 2026-05-06 09:45:35,534 INFO main: UserStream TRADE: price=113.40625 pnl=None fees=13.35
captain-online-1 | [ONLINE] 2026-05-06 09:45:35,542 INFO main: UserStream POSITION: contract=CON.F.US.USA.M26 size=15 avgPrice=113.40625
captain-online-1 | [ONLINE] 2026-05-06 09:45:35,549 INFO main: UserStream ACCOUNT: balance=150043.63
captain-online-1 | [ONLINE] 2026-05-06 09:45:36,139 INFO main: UserStream ORDER: id=2935091319 status=2 type=1
captain-online-1 | [ONLINE] 2026-05-06 09:45:36,593 INFO main: UserStream ACCOUNT: balance=150043.63
captain-online-1 | [ONLINE] 2026-05-06 09:46:23,178 INFO main: UserStream ORDER: id=2935192895 status=6 type=2
captain-online-1 | [ONLINE] 2026-05-06 09:46:23,178 WARNING main: UserStream ORDER REJECTED: id=2935192895 data={'id': 2935192895, 'accountId': 21855714, 'contractId': 'CON.F.US.USA.M26', 'symbolId': 'F.US.USA', 'creationTimestamp': '2026-05-06T13:46:23.1369685+00:00', 'updateTimestamp': '2026-05-06T13:46:23.1369685+00:00', 'status': 6, 'type': 2, 'side': 1, 'size': 15, 'fillVolume': 0}
captain-online-1 | [ONLINE] 2026-05-06 09:46:23,185 INFO main: UserStream TRADE: price=113.40625 pnl=None fees=13.35
captain-online-1 | [ONLINE] 2026-05-06 09:46:23,186 INFO main: UserStream ORDER: id=2935192895 status=2 type=2
captain-online-1 | [ONLINE] 2026-05-06 09:46:23,187 INFO main: UserStream TRADE: price=113.40625 pnl=0.0 fees=13.35
captain-online-1 | [ONLINE] 2026-05-06 09:46:23,191 INFO main: UserStream POSITION: contract=CON.F.US.USA.M26 size=0 avgPrice=113.40625
captain-online-1 | [ONLINE] 2026-05-06 09:46:23,197 INFO main: UserStream ACCOUNT: balance=150022.78
captain-online-1 | [ONLINE] 2026-05-06 09:46:26,593 INFO main: UserStream ACCOUNT: balance=150022.78
captain-online-1 | [ONLINE] 2026-05-06 09:50:51,370 INFO captain_online.blocks.b7_shadow_monitor: Shadow resolved: MES SL_HIT SIG-98C6A745A630 pnl=-643.75 (theoretical)

nomaan@captain-tower-1 ~/captain-system (main) [SIGINT]> docker compose -f docker-compose.yml -f docker-compose.local.yml logs -f captain-command
captain-command-1 | [COMMAND] 2026-05-06 09:03:22,983 INFO main: Starting Captain Command...
captain-command-1 | [COMMAND] 2026-05-06 09:03:22,985 INFO shared.questdb_client: QuestDB reachable (attempt 1)
captain-command-1 | [COMMAND] 2026-05-06 09:03:22,990 INFO main: Redis: connected
captain-command-1 | [COMMAND] 2026-05-06 09:03:22,990 INFO main: Redis Stream consumer groups initialized
captain-command-1 | [COMMAND] 2026-05-06 09:03:22,999 INFO main: Resuming from: ORCHESTRATOR_STOP — next: stopped
captain-command-1 | [COMMAND] 2026-05-06 09:03:23,028 WARNING captain_command.blocks.b4_tsm_manager: TSM topstep_150k_live.json has errors: ['Missing required field: starting_balance', 'Missing required field: max_drawdown_limit']
captain-command-1 | [COMMAND] 2026-05-06 09:03:23,028 INFO main: TSM files loaded: 3/4 valid
captain-command-1 | [COMMAND] 2026-05-06 09:03:23,036 INFO captain_command.blocks.b4_tsm_manager: TSM stored in D08: account=20319811 tsm=Topstep 150K Trading Combine
captain-command-1 | [COMMAND] 2026-05-06 09:03:23,036 INFO captain_command.blocks.b4_tsm_manager: TSM config refreshed in D08 for account 20319811 from 'Topstep 150K Trading Combine'
captain-command-1 | [COMMAND] 2026-05-06 09:03:23,040 INFO captain_command.blocks.b4_tsm_manager: TSM stored in D08: account=21855714 tsm=Topstep 150K Trading Combine
captain-command-1 | [COMMAND] 2026-05-06 09:03:23,040 INFO captain_command.blocks.b4_tsm_manager: TSM config refreshed in D08 for account 21855714 from 'Topstep 150K Trading Combine'
captain-command-1 | [COMMAND] 2026-05-06 09:03:23,040 INFO main: TSM config refreshed in D08 for 2 account(s)
captain-command-1 | [COMMAND] 2026-05-06 09:03:23,801 INFO captain_command.blocks.telegram_bot: Telegram bot thread started
captain-command-1 | [COMMAND] 2026-05-06 09:03:23,801 INFO main: Telegram bot: ACTIVE
captain-command-1 | [COMMAND] 2026-05-06 09:03:23,807 INFO main: Telegram chat_id already set in D16 for primary_user
captain-command-1 | [COMMAND] 2026-05-06 09:03:23,991 INFO captain_command.blocks.telegram_bot: Telegram bot polling started
captain-command-1 | [COMMAND] 2026-05-06 09:03:24,062 INFO telegram.ext.Application: Application started
captain-command-1 | [COMMAND] 2026-05-06 09:03:24,184 INFO shared.topstep_client: TopstepX authenticated as nomaanakram4@gmail.com (env=LIVE)
captain-command-1 | [COMMAND] 2026-05-06 09:03:24,184 INFO main: TopstepX API: authenticated
captain-command-1 | [COMMAND] 2026-05-06 09:03:24,264 INFO main: TopstepX account: 150KTC-V2-551001-86041837 (id=21855714, balance=150061.03)
captain-command-1 | [COMMAND] 2026-05-06 09:03:24,360 INFO shared.topstep_client: TopstepX authenticated as nomaanakram4@gmail.com (env=LIVE)
captain-command-1 | [COMMAND] 2026-05-06 09:03:24,440 INFO captain_command.blocks.b3_api_adapter: TopstepX CONNECTED: account=150KTC-V2-551001-86041837 (id=21855714), balance=150061.03, canTrade=True
captain-command-1 | [COMMAND] 2026-05-06 09:03:24,441 INFO main: Resolved 10 contracts: ['ES', 'MES', 'NQ', 'MNQ', 'M2K', 'MYM', 'NKD', 'MGC', 'ZB', 'ZN']
captain-command-1 | [COMMAND] 2026-05-06 09:03:24,441 INFO main: TopstepX WebSocket streams: SKIPPED (owned by captain-online)
captain-command-1 | [COMMAND] 2026-05-06 09:03:24,442 INFO main: TSM link check: account=150KTC-V2-551001-86041837, tsm_count=4
captain-command-1 | [COMMAND] 2026-05-06 09:03:24,444 INFO main: TSM already linked for account 150KTC-V2-551001-86041837 — skipping
captain-command-1 | [COMMAND] 2026-05-06 09:03:24,492 INFO captain_command.blocks.orchestrator: Command Orchestrator starting
captain-command-1 | [COMMAND] 2026-05-06 09:03:24,494 INFO captain_command.blocks.orchestrator: Redis pub/sub listener started (alerts + status)
captain-command-1 | [COMMAND] 2026-05-06 09:03:24,495 INFO captain_command.blocks.orchestrator: Signal stream consumer group ready
captain-command-1 | [COMMAND] 2026-05-06 09:03:24,495 INFO captain_command.blocks.orchestrator: Process log forwarder started
captain-command-1 | [COMMAND] 2026-05-06 09:03:24,496 INFO captain_command.blocks.orchestrator: Trade outcomes GUI forwarder started
captain-command-1 | [COMMAND] 2026-05-06 09:03:24,497 INFO captain_command.blocks.orchestrator: CommandOrchestrator ready — API health gate opened
captain-command-1 | [COMMAND] 2026-05-06 09:03:24,498 INFO captain_command.blocks.orchestrator: Scheduler started
captain-command-1 | [COMMAND] 2026-05-06 09:03:24,500 INFO captain_command.blocks.orchestrator: Subscribed to pub/sub: captain:commands, captain:alerts, captain:status
captain-command-1 | [COMMAND] 2026-05-06 09:03:24,501 INFO captain_command.blocks.orchestrator: Command stream consumer group ready
captain-command-1 | [COMMAND] 2026-05-06 09:03:24,530 INFO main: Starting API server on port 8000...
captain-command-1 | INFO: Started server process [1]
captain-command-1 | INFO: Waiting for application startup.
captain-command-1 | INFO: Application startup complete.
captain-command-1 | INFO: Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
captain-command-1 | INFO: 172.19.0.7:57812 - "WebSocket /ws/primary_user?token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJwcmltYXJ5X3VzZXIiLCJpYXQiOjE3Nzc5OTU0NTgsImV4cCI6MTc3ODA4MTg1OH0.bE2G0Hqs8r94fMXyjNdHrHwd5mLVSdtdlWNUBhNddCg" [accepted]
captain-command-1 | [COMMAND] 2026-05-06 09:03:27,053 INFO captain_command.api: WebSocket connected: user=primary_user (sessions=1, evicted=0)
captain-command-1 | INFO: connection open
captain-command-1 | INFO: 172.19.0.7:57822 - "GET /api/accounts HTTP/1.1" 200 OK
captain-command-1 | INFO: 172.19.0.7:57836 - "GET /api/dashboard/primary_user HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:46006 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 172.19.0.7:60828 - "POST /api/signals/clear HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:34350 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:49970 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:48172 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:56244 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:36506 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:41772 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:60042 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:44658 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | [COMMAND] 2026-05-06 09:07:56,671 INFO captain_command.api: WebSocket disconnected: user=primary_user (remaining=0)
captain-command-1 | INFO: connection closed
captain-command-1 | INFO: 172.19.0.7:41260 - "WebSocket /ws/primary_user?token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJwcmltYXJ5X3VzZXIiLCJpYXQiOjE3Nzc5OTU0NTgsImV4cCI6MTc3ODA4MTg1OH0.bE2G0Hqs8r94fMXyjNdHrHwd5mLVSdtdlWNUBhNddCg" [accepted]
captain-command-1 | [COMMAND] 2026-05-06 09:07:56,683 INFO captain_command.api: WebSocket connected: user=primary_user (sessions=1, evicted=0)
captain-command-1 | INFO: connection open
captain-command-1 | INFO: 172.19.0.7:41256 - "GET /api/replay/history HTTP/1.1" 200 OK
captain-command-1 | INFO: 172.19.0.7:41270 - "GET /api/replay/presets HTTP/1.1" 200 OK
captain-command-1 | INFO: 172.19.0.7:41274 - "GET /api/replay/history HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:51920 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | [COMMAND] 2026-05-06 09:07:59,928 INFO captain_command.blocks.b11_replay_runner: Replay started: id=0e73cbf601af user=primary_user date=2026-05-06 speed=50.0
captain-command-1 | INFO: 172.19.0.7:41288 - "POST /api/replay/start HTTP/1.1" 200 OK
captain-command-1 | [COMMAND] 2026-05-06 09:08:00,047 INFO shared.topstep_client: TopstepX authenticated as nomaanakram4@gmail.com (env=LIVE)
captain-command-1 | [COMMAND] 2026-05-06 09:08:09,285 WARNING shared.sizing_helpers: resolve_sizing_sl: NKD using DEFAULT_SL_POINTS=4.0 (no D29 history, no strategy.threshold). pv=5.0.
captain-command-1 | [COMMAND] 2026-05-06 09:08:09,286 INFO shared.replay_engine: SIZING NKD: kelly=0.0704 aim_mod=1.000 → raw=1928, mdd_cap=11, daily_cap=112, max=15 → final=11 (binding: mdd_cap)
captain-command-1 | [COMMAND] 2026-05-06 09:08:09,619 WARNING shared.sizing_helpers: resolve_sizing_sl: MGC using DEFAULT_SL_POINTS=4.0 (no D29 history, no strategy.threshold). pv=10.0.
captain-command-1 | [COMMAND] 2026-05-06 09:08:09,620 INFO shared.replay_engine: SIZING MGC: kelly=0.0261 aim_mod=1.000 → raw=720, mdd_cap=5, daily_cap=56, max=15 → final=5 (binding: mdd_cap)
captain-command-1 | [COMMAND] 2026-05-06 09:08:21,789 INFO captain_command.api: WebSocket disconnected: user=primary_user (remaining=0)
captain-command-1 | INFO: connection closed
captain-command-1 | INFO: 172.19.0.7:41902 - "WebSocket /ws/primary_user?token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJwcmltYXJ5X3VzZXIiLCJpYXQiOjE3Nzc5OTU0NTgsImV4cCI6MTc3ODA4MTg1OH0.bE2G0Hqs8r94fMXyjNdHrHwd5mLVSdtdlWNUBhNddCg" [accepted]
captain-command-1 | [COMMAND] 2026-05-06 09:08:21,803 INFO captain_command.api: WebSocket connected: user=primary_user (sessions=1, evicted=0)
captain-command-1 | INFO: connection open
captain-command-1 | INFO: 172.19.0.7:41914 - "GET /api/accounts HTTP/1.1" 200 OK
captain-command-1 | INFO: 172.19.0.7:41924 - "GET /api/accounts HTTP/1.1" 200 OK
captain-command-1 | INFO: 172.19.0.7:41932 - "GET /api/accounts HTTP/1.1" 200 OK
captain-command-1 | INFO: 172.19.0.7:41918 - "GET /api/dashboard/primary_user HTTP/1.1" 200 OK
captain-command-1 | INFO: 172.19.0.7:41948 - "GET /api/dashboard/primary_user HTTP/1.1" 200 OK
captain-command-1 | INFO: 172.19.0.7:41956 - "GET /api/dashboard/primary_user HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:48128 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | [COMMAND] 2026-05-06 09:08:36,007 INFO captain_command.api: WebSocket disconnected: user=primary_user (remaining=0)
captain-command-1 | INFO: connection closed
captain-command-1 | INFO: 172.19.0.7:43700 - "WebSocket /ws/primary_user?token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJwcmltYXJ5X3VzZXIiLCJpYXQiOjE3Nzc5OTU0NTgsImV4cCI6MTc3ODA4MTg1OH0.bE2G0Hqs8r94fMXyjNdHrHwd5mLVSdtdlWNUBhNddCg" [accepted]
captain-command-1 | [COMMAND] 2026-05-06 09:08:36,025 INFO captain_command.api: WebSocket connected: user=primary_user (sessions=1, evicted=0)
captain-command-1 | INFO: connection open
captain-command-1 | INFO: 172.19.0.7:43690 - "GET /api/replay/history HTTP/1.1" 200 OK
captain-command-1 | INFO: 172.19.0.7:43710 - "GET /api/replay/presets HTTP/1.1" 200 OK
captain-command-1 | INFO: 172.19.0.7:43722 - "GET /api/replay/history HTTP/1.1" 200 OK
captain-command-1 | [COMMAND] 2026-05-06 09:08:57,520 INFO captain_command.blocks.b11_replay_runner: Replay started: id=bbe8745b705e user=primary_user date=2026-05-05 speed=50.0
captain-command-1 | INFO: 172.19.0.7:51704 - "POST /api/replay/start HTTP/1.1" 200 OK
captain-command-1 | [COMMAND] 2026-05-06 09:08:57,869 INFO shared.topstep_client: TopstepX authenticated as nomaanakram4@gmail.com (env=LIVE)
captain-command-1 | [COMMAND] 2026-05-06 09:08:58,086 INFO shared.vix_provider: VIX provider: loaded 9177 daily closes (1990-01-02 to 2026-05-04)
captain-command-1 | [COMMAND] 2026-05-06 09:08:58,128 INFO shared.vix_provider: VXV provider: loaded 4181 daily closes (2009-09-18 to 2026-05-04)
captain-command-1 | INFO: 127.0.0.1:44572 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | [COMMAND] 2026-05-06 09:08:59,377 INFO shared.aim_compute: AIM ES: AIM-04(IVTS)=0.900×0.167 | AIM-06(EconCal)=1.000×0.167 | AIM-08(CrossCorr)=1.000×0.167 | AIM-11(RegimeWarn)=1.000×0.167 | AIM-12(DynCosts)=1.000×0.167 | AIM-15(OpenVol)=1.000×0.167
captain-command-1 | [COMMAND] 2026-05-06 09:08:59,377 INFO shared.aim_compute: AIM MES: AIM-04(IVTS)=0.900×0.167 | AIM-06(EconCal)=1.000×0.167 | AIM-08(CrossCorr)=0.800×0.167 | AIM-11(RegimeWarn)=1.000×0.167 | AIM-12(DynCosts)=1.000×0.167 | AIM-15(OpenVol)=1.000×0.167
captain-command-1 | [COMMAND] 2026-05-06 09:08:59,377 INFO shared.aim_compute: AIM NQ: AIM-04(IVTS)=0.900×0.167 | AIM-06(EconCal)=1.000×0.167 | AIM-08(CrossCorr)=0.800×0.167 | AIM-11(RegimeWarn)=1.000×0.167 | AIM-12(DynCosts)=1.000×0.167 | AIM-15(OpenVol)=1.000×0.167
captain-command-1 | [COMMAND] 2026-05-06 09:08:59,377 INFO shared.aim_compute: AIM MNQ: AIM-04(IVTS)=0.900×0.167 | AIM-06(EconCal)=1.000×0.167 | AIM-08(CrossCorr)=0.800×0.167 | AIM-11(RegimeWarn)=1.000×0.167 | AIM-12(DynCosts)=1.000×0.167 | AIM-15(OpenVol)=1.000×0.167
captain-command-1 | [COMMAND] 2026-05-06 09:08:59,377 INFO shared.aim_compute: AIM M2K: AIM-04(IVTS)=0.900×0.167 | AIM-06(EconCal)=1.000×0.167 | AIM-08(CrossCorr)=0.800×0.167 | AIM-11(RegimeWarn)=1.000×0.167 | AIM-12(DynCosts)=1.000×0.167 | AIM-15(OpenVol)=1.050×0.167
captain-command-1 | [COMMAND] 2026-05-06 09:08:59,377 INFO shared.aim_compute: AIM MYM: AIM-04(IVTS)=0.900×0.167 | AIM-06(EconCal)=1.000×0.167 | AIM-08(CrossCorr)=0.800×0.167 | AIM-11(RegimeWarn)=1.000×0.167 | AIM-12(DynCosts)=1.000×0.167 | AIM-15(OpenVol)=1.000×0.167
captain-command-1 | [COMMAND] 2026-05-06 09:08:59,377 INFO shared.aim_compute: AIM NKD: AIM-04(IVTS)=0.900×0.167 | AIM-06(EconCal)=1.000×0.167 | AIM-08(CrossCorr)=0.800×0.167 | AIM-11(RegimeWarn)=1.000×0.167 | AIM-12(DynCosts)=1.000×0.167 | AIM-15(OpenVol)=0.800×0.167
captain-command-1 | [COMMAND] 2026-05-06 09:08:59,377 INFO shared.aim_compute: AIM MGC: AIM-04(IVTS)=0.900×0.167 | AIM-06(EconCal)=1.000×0.167 | AIM-08(CrossCorr)=0.900×0.167 | AIM-11(RegimeWarn)=1.000×0.167 | AIM-12(DynCosts)=1.000×0.167 | AIM-15(OpenVol)=0.800×0.167
captain-command-1 | [COMMAND] 2026-05-06 09:08:59,377 INFO shared.aim_compute: AIM aggregation: 8 assets, 8 with active AIMs, 48 individual AIMs computed
captain-command-1 | [COMMAND] 2026-05-06 09:08:59,711 WARNING shared.sizing_helpers: resolve_sizing_sl: ES using DEFAULT_SL_POINTS=4.0 (no D29 history, no strategy.threshold). pv=50.0.
captain-command-1 | [COMMAND] 2026-05-06 09:08:59,711 INFO shared.replay_engine: SIZING ES: kelly=0.0142 aim_mod=0.983 → raw=388, mdd_cap=2, daily_cap=11, max=15 → final=2 (binding: mdd_cap)
captain-command-1 | [COMMAND] 2026-05-06 09:09:00,038 WARNING shared.sizing_helpers: resolve_sizing_sl: MES using DEFAULT_SL_POINTS=4.0 (no D29 history, no strategy.threshold). pv=5.0.
captain-command-1 | [COMMAND] 2026-05-06 09:09:00,038 INFO shared.replay_engine: SIZING MES: kelly=0.0435 aim_mod=0.950 → raw=1162, mdd_cap=22, daily_cap=112, max=15 → final=15 (binding: max_contracts)
captain-command-1 | [COMMAND] 2026-05-06 09:09:00,376 WARNING shared.sizing_helpers: resolve_sizing_sl: NQ using DEFAULT_SL_POINTS=4.0 (no D29 history, no strategy.threshold). pv=20.0.
captain-command-1 | [COMMAND] 2026-05-06 09:09:00,377 INFO shared.replay_engine: SIZING NQ: kelly=0.0279 aim_mod=0.950 → raw=735, mdd_cap=5, daily_cap=28, max=15 → final=5 (binding: mdd_cap)
captain-command-1 | [COMMAND] 2026-05-06 09:09:00,720 WARNING shared.sizing_helpers: resolve_sizing_sl: MNQ using DEFAULT_SL_POINTS=4.0 (no D29 history, no strategy.threshold). pv=2.0.
captain-command-1 | [COMMAND] 2026-05-06 09:09:00,721 INFO shared.replay_engine: SIZING MNQ: kelly=0.0243 aim_mod=0.950 → raw=639, mdd_cap=56, daily_cap=281, max=15 → final=15 (binding: max_contracts)
captain-command-1 | [COMMAND] 2026-05-06 09:09:01,047 WARNING shared.sizing_helpers: resolve_sizing_sl: M2K using DEFAULT_SL_POINTS=4.0 (no D29 history, no strategy.threshold). pv=5.0.
captain-command-1 | [COMMAND] 2026-05-06 09:09:01,048 INFO shared.replay_engine: SIZING M2K: kelly=0.0375 aim_mod=0.958 → raw=1022, mdd_cap=22, daily_cap=112, max=15 → final=15 (binding: max_contracts)
captain-command-1 | [COMMAND] 2026-05-06 09:09:01,380 WARNING shared.sizing_helpers: resolve_sizing_sl: MYM using DEFAULT_SL_POINTS=4.0 (no D29 history, no strategy.threshold). pv=0.5.
captain-command-1 | [COMMAND] 2026-05-06 09:09:01,381 INFO shared.replay_engine: SIZING MYM: kelly=0.0364 aim_mod=0.950 → raw=957, mdd_cap=225, daily_cap=1125, max=15 → final=15 (binding: max_contracts)
captain-command-1 | [COMMAND] 2026-05-06 09:09:01,701 INFO shared.replay_engine: SIZING NKD: kelly=0.0704 aim_mod=0.917 → raw=1767, mdd_cap=22, daily_cap=112, max=15 → final=15 (binding: max_contracts)
captain-command-1 | [COMMAND] 2026-05-06 09:09:02,034 INFO shared.replay_engine: SIZING MGC: kelly=0.0261 aim_mod=0.933 → raw=672, mdd_cap=11, daily_cap=56, max=15 → final=11 (binding: mdd_cap)
captain-command-1 | [COMMAND] 2026-05-06 09:09:16,161 INFO captain_command.api: WebSocket disconnected: user=primary_user (remaining=0)
captain-command-1 | INFO: connection closed
captain-command-1 | INFO: 172.19.0.7:46658 - "WebSocket /ws/primary_user?token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJwcmltYXJ5X3VzZXIiLCJpYXQiOjE3Nzc5OTU0NTgsImV4cCI6MTc3ODA4MTg1OH0.bE2G0Hqs8r94fMXyjNdHrHwd5mLVSdtdlWNUBhNddCg" [accepted]
captain-command-1 | [COMMAND] 2026-05-06 09:09:16,172 INFO captain_command.api: WebSocket connected: user=primary_user (sessions=1, evicted=0)
captain-command-1 | INFO: 172.19.0.7:46646 - "GET /api/accounts HTTP/1.1" 200 OK
captain-command-1 | INFO: connection open
captain-command-1 | INFO: 172.19.0.7:46670 - "GET /api/accounts HTTP/1.1" 200 OK
captain-command-1 | INFO: 172.19.0.7:46638 - "GET /api/dashboard/primary_user HTTP/1.1" 200 OK
captain-command-1 | INFO: 172.19.0.7:46672 - "GET /api/dashboard/primary_user HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:44454 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:57862 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:51618 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:33836 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:49174 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:33246 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:44970 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:58506 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:47244 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:45800 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:37826 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:37906 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:57914 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:59634 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:50886 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:60080 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:46480 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:38620 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:47316 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:42760 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:52924 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:41342 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:39832 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:55072 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:32998 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:48284 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:38318 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:44552 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:58626 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:44918 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:59260 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:60078 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:39832 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:40732 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:57938 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:55414 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:50592 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:51166 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:35048 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:54304 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:53680 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:59776 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:39468 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:59882 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:57456 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:48724 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:34864 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:58054 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:49708 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:45364 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:54132 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:49542 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | [COMMAND] 2026-05-06 09:35:03,275 INFO captain_command.blocks.orchestrator: PARITY CHECK: trade_number=2, signal_parity=1, my_parity=0, skip=True, assets=['MNQ', 'MES']
captain-command-1 | [COMMAND] 2026-05-06 09:35:03,392 INFO captain_command.blocks.telegram_bot: Telegram sent [HIGH] to chat 8616119618
captain-command-1 | [COMMAND] 2026-05-06 09:35:03,484 INFO captain_command.blocks.telegram_bot: Telegram sent [HIGH] to chat 8616119618
captain-command-1 | [COMMAND] 2026-05-06 09:35:03,504 INFO captain_command.blocks.telegram_bot: Telegram sent [HIGH] to chat 8616119618
captain-command-1 | [COMMAND] 2026-05-06 09:35:03,573 INFO captain_command.blocks.telegram_bot: Telegram sent [HIGH] to chat 8616119618
captain-command-1 | INFO: 127.0.0.1:55162 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:58272 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | [COMMAND] 2026-05-06 09:36:02,988 INFO captain_command.blocks.orchestrator: PARITY CHECK: trade_number=3, signal_parity=0, my_parity=0, skip=False, assets=['MYM']
captain-command-1 | [COMMAND] 2026-05-06 09:36:02,993 INFO captain_command.blocks.orchestrator: AUTO-EXECUTE: BUY MYM x15 (account=21855714, TP=49983.0, SL=49877.0)
captain-command-1 | [COMMAND] 2026-05-06 09:36:03,211 INFO captain_command.blocks.b3_api_adapter: Bracket order: BUY MYM x15, SL=35 ticks, TP=71 ticks (tick_size=1.0, entry_est=49912)
captain-command-1 | [COMMAND] 2026-05-06 09:36:03,434 INFO captain_command.blocks.b3_api_adapter: TopstepX BRACKET order PLACED: entry=2934939667 fill=49909.0 SL=35t TP=71t (BUY x15 @ CON.F.US.MYM.M26)
captain-command-1 | [COMMAND] 2026-05-06 09:36:03,434 INFO captain_command.blocks.orchestrator: AUTO-EXECUTE SUCCESS: order_id=2934939667 fill_price=49909.0
captain-command-1 | [COMMAND] 2026-05-06 09:36:03,544 INFO captain_command.blocks.telegram_bot: Telegram sent [HIGH] to chat 8616119618
captain-command-1 | [COMMAND] 2026-05-06 09:36:03,641 INFO captain_command.blocks.telegram_bot: Telegram sent [HIGH] to chat 8616119618
captain-command-1 | INFO: 127.0.0.1:48092 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | [COMMAND] 2026-05-06 09:36:43,657 INFO captain_command.blocks.orchestrator: PARITY CHECK: trade_number=4, signal_parity=1, my_parity=0, skip=True, assets=['ZN']
captain-command-1 | [COMMAND] 2026-05-06 09:36:43,754 INFO captain_command.blocks.telegram_bot: Telegram sent [HIGH] to chat 8616119618
captain-command-1 | [COMMAND] 2026-05-06 09:36:43,835 INFO captain_command.blocks.telegram_bot: Telegram sent [HIGH] to chat 8616119618
captain-command-1 | INFO: 127.0.0.1:36668 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:55716 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:58986 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:57928 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | [COMMAND] 2026-05-06 09:38:55,840 INFO captain_command.blocks.telegram_bot: Telegram sent [HIGH] to chat 8616119618
captain-command-1 | INFO: 127.0.0.1:55650 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | [COMMAND] 2026-05-06 09:39:16,122 INFO captain_command.blocks.telegram_bot: Telegram sent [CRITICAL] to chat 8616119618
captain-command-1 | INFO: 127.0.0.1:42888 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:55400 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:55820 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:39834 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:39132 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:51220 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | [COMMAND] 2026-05-06 09:42:12,608 INFO captain_command.blocks.orchestrator: PARITY CHECK: trade_number=5, signal_parity=0, my_parity=0, skip=False, assets=['ZB']
captain-command-1 | [COMMAND] 2026-05-06 09:42:12,618 INFO captain_command.blocks.orchestrator: AUTO-EXECUTE: SELL ZB x15 (account=21855714, TP=113.40625, SL=113.5)
captain-command-1 | [COMMAND] 2026-05-06 09:42:12,652 WARNING captain_command.blocks.b1_core_routing: Unknown command type: SESSION_CLOSE from user SYSTEM
captain-command-1 | [COMMAND] 2026-05-06 09:42:12,833 INFO captain_command.blocks.b3_api_adapter: Bracket order: SELL ZB x15, SL=1 ticks, TP=2 ticks (tick_size=0.03125, entry_est=113.46875)
captain-command-1 | [COMMAND] 2026-05-06 09:42:12,926 ERROR captain_command.blocks.b3_api_adapter: Bracket order FAILED (errorCode=2): Invalid stop loss ticks (1). Price should be at least 4 ticks away. [asset=ZB account=21855714 side=SELL size=15 SL_ticks=1 TP_ticks=2 entry_est=113.46875] — falling back to NON-OCO separate orders. Orphan SL/TP cleanup will be attempted by B7 on resolution.
captain-command-1 | [COMMAND] 2026-05-06 09:42:13,328 INFO captain_command.blocks.b3_api_adapter: TopstepX FALLBACK order PLACED: entry=2935091179 sl=2935091274 tp=2935091319 (SELL x15 @ CON.F.US.USA.M26)
captain-command-1 | [COMMAND] 2026-05-06 09:42:13,328 INFO captain_command.blocks.orchestrator: AUTO-EXECUTE SUCCESS: order_id=2935091179 fill_price=113.46875
captain-command-1 | [COMMAND] 2026-05-06 09:42:13,440 INFO captain_command.blocks.telegram_bot: Telegram sent [HIGH] to chat 8616119618
captain-command-1 | [COMMAND] 2026-05-06 09:42:13,805 INFO captain_command.blocks.telegram_bot: Telegram sent [CRITICAL] to chat 8616119618
captain-command-1 | [COMMAND] 2026-05-06 09:42:13,886 INFO captain_command.blocks.telegram_bot: Telegram sent [HIGH] to chat 8616119618
captain-command-1 | [COMMAND] 2026-05-06 09:42:13,970 INFO captain_command.blocks.telegram_bot: Telegram sent [CRITICAL] to chat 8616119618
captain-command-1 | [COMMAND] 2026-05-06 09:42:14,082 INFO captain_command.blocks.telegram_bot: Telegram sent [CRITICAL] to chat 8616119618
captain-command-1 | INFO: 127.0.0.1:56932 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:56758 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:52026 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:59446 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 172.19.0.7:44710 - "GET /api/aim/15/detail HTTP/1.1" 200 OK
captain-command-1 | INFO: 172.19.0.7:44718 - "GET /api/aim/11/detail HTTP/1.1" 200 OK
captain-command-1 | INFO: 172.19.0.7:44722 - "GET /api/aim/12/detail HTTP/1.1" 200 OK
captain-command-1 | INFO: 172.19.0.7:53130 - "GET /api/aim/8/detail HTTP/1.1" 200 OK
captain-command-1 | INFO: 172.19.0.7:53136 - "GET /api/aim/6/detail HTTP/1.1" 200 OK
captain-command-1 | INFO: 172.19.0.7:53138 - "GET /api/aim/4/detail HTTP/1.1" 200 OK
captain-command-1 | INFO: 172.19.0.7:36692 - "POST /api/signals/clear HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:45960 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:46808 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:34426 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:54470 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:56214 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:32800 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:36912 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:46520 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:42352 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:33438 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:58884 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:42532 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:47332 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:58342 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:38290 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:59210 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:50796 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:39468 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:54464 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:37714 - "GET /api/health HTTP/1.1" 200 OK
captain-command-1 | INFO: 127.0.0.1:50168 - "GET /api/health HTTP/1.1" 200 OK

captain-offline-1 | [OFFLINE] 2026-05-06 08:54:38,886 WARNING captain_offline.blocks.version_snapshot: Could not prune old versions for P3-D01: unexpected token [FROM]
captain-offline-1 | LINE 1: DELETE FROM p3_d18_version_history
captain-offline-1 | ^
captain-offline-1 | (manual cleanup needed)
captain-offline-1 | [OFFLINE] 2026-05-06 08:54:38,957 INFO captain_offline.blocks.orchestrator: AIM 15 ACTIVE for 20 assets
captain-offline-1 | [OFFLINE] 2026-05-06 09:36:44,881 INFO captain_offline.blocks.orchestrator: Theoretical signal outcome: ZN pnl=-312.50 (Category A learning)
captain-offline-1 | [OFFLINE] 2026-05-06 09:36:44,898 ERROR captain_offline.blocks.orchestrator: Error processing signal outcome for ZN: cannot import name 'qexecute' from 'shared.questdb_client' (/app/shared/questdb_client.py)
captain-offline-1 | Traceback (most recent call last):
captain-offline-1 | File "/app/captain_offline/blocks/orchestrator.py", line 394, in _handle_signal_outcome
captain-offline-1 | from captain_offline.blocks.b1_dma_update import run_dma_update
captain-offline-1 | File "/app/captain_offline/blocks/b1_dma_update.py", line 24, in
captain-offline-1 | from shared.questdb_client import get_cursor, qexecute
captain-offline-1 | ImportError: cannot import name 'qexecute' from 'shared.questdb_client' (/app/shared/questdb_client.py)
captain-offline-1 | [OFFLINE] 2026-05-06 09:38:02,649 INFO captain_offline.blocks.orchestrator: Theoretical signal outcome: MNQ pnl=-625.33 (Category A learning)
captain-offline-1 | [OFFLINE] 2026-05-06 09:38:02,674 ERROR captain_offline.blocks.orchestrator: Error processing signal outcome for MNQ: cannot import name 'qexecute' from 'shared.questdb_client' (/app/shared/questdb_client.py)
captain-offline-1 | Traceback (most recent call last):
captain-offline-1 | File "/app/captain_offline/blocks/orchestrator.py", line 394, in _handle_signal_outcome
captain-offline-1 | from captain_offline.blocks.b1_dma_update import run_dma_update
captain-offline-1 | File "/app/captain_offline/blocks/b1_dma_update.py", line 24, in
captain-offline-1 | from shared.questdb_client import get_cursor, qexecute
captain-offline-1 | ImportError: cannot import name 'qexecute' from 'shared.questdb_client' (/app/shared/questdb_client.py)
captain-offline-1 | [OFFLINE] 2026-05-06 09:39:17,022 ERROR captain_offline.blocks.orchestrator: Stream listener error: float() argument must be a string or a real number, not 'dict' — reconnecting in 1s
captain-offline-1 | [OFFLINE] 2026-05-06 09:39:18,023 INFO captain_offline.blocks.orchestrator: Offline stream consumer groups ready
captain-offline-1 | [OFFLINE] 2026-05-06 09:42:12,951 INFO captain_offline.blocks.orchestrator: Theoretical signal outcome: ZB pnl=-937.50 (Category A learning)
captain-offline-1 | [OFFLINE] 2026-05-06 09:42:12,969 ERROR captain_offline.blocks.orchestrator: Error processing signal outcome for ZB: cannot import name 'qexecute' from 'shared.questdb_client' (/app/shared/questdb_client.py)
captain-offline-1 | Traceback (most recent call last):
captain-offline-1 | File "/app/captain_offline/blocks/orchestrator.py", line 394, in _handle_signal_outcome
captain-offline-1 | from captain_offline.blocks.b1_dma_update import run_dma_update
captain-offline-1 | File "/app/captain_offline/blocks/b1_dma_update.py", line 24, in
captain-offline-1 | from shared.questdb_client import get_cursor, qexecute
captain-offline-1 | ImportError: cannot import name 'qexecute' from 'shared.questdb_client' (/app/shared/questdb_client.py)
captain-offline-1 | [OFFLINE] 2026-05-06 09:42:12,980 INFO captain_offline.blocks.orchestrator: [pg01c] session_close received session_id=1 closed_at=2026-05-06T09:42:12.650980-04:00; dispatching AIM-16 HMM training (skeleton)
captain-offline-1 | [OFFLINE] 2026-05-06 09:42:14,021 ERROR captain_offline.blocks.orchestrator: [pg01c] training dispatch failed: cannot import name 'qexecute' from 'shared.questdb_client' (/app/shared/questdb_client.py)
captain-offline-1 | Traceback (most recent call last):
captain-offline-1 | File "/app/captain_offline/blocks/orchestrator.py", line 615, in _handle_session_close
captain-offline-1 | self._run_aim16_hmm_training(session_id, closed_at)
captain-offline-1 | File "/app/captain_offline/blocks/orchestrator.py", line 631, in _run_aim16_hmm_training
captain-offline-1 | from captain_offline.blocks.b1_aim16_hmm import (
captain-offline-1 | File "/app/captain_offline/blocks/b1_aim16_hmm.py", line 35, in
captain-offline-1 | from shared.questdb_client import get_cursor, qexecute
captain-offline-1 | ImportError: cannot import name 'qexecute' from 'shared.questdb_client' (/app/shared/questdb_client.py)
captain-offline-1 | [OFFLINE] 2026-05-06 09:42:14,022 ERROR captain_offline.blocks.orchestrator: Stream listener error: float() argument must be a string or a real number, not 'dict' — reconnecting in 1s
captain-offline-1 | [OFFLINE] 2026-05-06 09:42:15,024 INFO captain_offline.blocks.orchestrator: Offline stream consumer groups ready
captain-offline-1 | [OFFLINE] 2026-05-06 09:50:52,010 INFO captain_offline.blocks.orchestrator: Theoretical signal outcome: MES pnl=-643.75 (Category A learning)
captain-offline-1 | [OFFLINE] 2026-05-06 09:50:52,028 ERROR captain_offline.blocks.orchestrator: Error processing signal outcome for MES: cannot import name 'qexecute' from 'shared.questdb_client' (/app/shared/questdb_client.py)
captain-offline-1 | Traceback (most recent call last):
captain-offline-1 | File "/app/captain_offline/blocks/orchestrator.py", line 394, in _handle_signal_outcome
captain-offline-1 | from captain_offline.blocks.b1_dma_update import run_dma_update
captain-offline-1 | File "/app/captain_offline/blocks/b1_dma_update.py", line 24, in
captain-offline-1 | from shared.questdb_client import get_cursor, qexecute
captain-offline-1 | ImportError: cannot import name 'qexecute' from 'shared.questdb_client' (/app/shared/questdb_client.py)