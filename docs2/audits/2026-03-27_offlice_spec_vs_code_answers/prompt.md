I'm executing a 12-phase fix campaign on Captain Offline (Python quantitative trading codebase). The Phase 1 prompt for Claude Code has already been generated and used. I need the remaining 11 phase prompts in one go so I can execute them sequentially.
Workflow per phase:

I paste the Claude Code prompt you write into a fresh Claude Code CLI session
Claude Code reads the attached audit + decisions log + relevant spec docs + the codebase
Claude Code does an audit pass, stops at an approval gate, then generates a granular build plan as a markdown file
I feed that plan into Cursor Composer 2 to execute modularly
I commit, regression test, then move to the next phase

Your job in this chat: produce 11 Claude Code prompts, one per phase, for Phases 2 through 12. Output them as 11 clearly delimited code blocks I can copy-paste individually.
Authoritative inputs (will be attached to every Claude Code session)
Every Claude Code prompt you write must reference these documents by name as authoritative inputs. Do not include their contents in your prompts — Claude Code will read them directly:

2026-04-22_offline_spec_vs_code_audit_copy.md — the 43-finding audit. Each phase's prompt must list the specific F-finding IDs that phase resolves, and instruct Claude Code to read each F-finding's full entry (Severity, Spec reference, Current code, Proposed fix, Tests sections) before planning.
captain_offline_audit_decisions_2026-04-27.md — authoritative decisions log. Each phase's prompt must reference §2 (the relevant Group row) and §5 (the Phase delta row) for that phase. The decisions log is what resolves "what should this fix do" when audit and code disagree.

Phase-specific spec documents to attach (per phase)
Each Claude Code prompt should also tell me which spec documents I need to attach to that specific session. Don't over-attach; lean context = better output. Use this map:

Phase 2 (persistence contracts): add 32_P3_Offline_Full_Pseudocode.md, 33_P3_Online_Full_Pseudocode_1.md
Phase 3 (orchestrator wiring): add 32_P3_Offline_Full_Pseudocode.md, P3_Offline.canvas, P3_Online.canvas
Phase 4 (AIM lifecycle/DMA/HDWM): add 32_P3_Offline_Full_Pseudocode.md, DMA_MoE_Meta-Learning_Pipeline.canvas, AIM_System.canvas
Phase 5 (BOCPD/CUSUM): add 32_P3_Offline_Full_Pseudocode.md, BOCPD_Implementation_Guide.md, Kelly_7_Layer_Pipeline.canvas
Phase 6 (AIM modifier realignment): add AIM_System.canvas, AIM_System_1.canvas, 33_P3_Online_Full_Pseudocode_1.md
Phase 7 (PG-09/10/13 pseudotrader chain): add 32_P3_Offline_Full_Pseudocode.md, 33_P3_Online_Full_Pseudocode_1.md, P3_Offline.canvas
Phase 8 (TSM PG-14 + CB params): add 32_P3_Offline_Full_Pseudocode.md, Kelly_7_Layer_Pipeline.canvas
Phase 9 (Block 9 diagnostic): add 32_P3_Offline_Full_Pseudocode.md (Block 9 section)
Phase 10 (HMM/AIM-16): add 22_HMM_Opportunity_Regime_1.md, 32_P3_Offline_Full_Pseudocode.md, 33_P3_Online_Full_Pseudocode_1.md
Phase 11 (governance/safety): add 32_P3_Offline_Full_Pseudocode.md (Version Snapshot Policy section)
Phase 12 (hygiene refactor): add AIM_System.canvas, AIM_System_1.canvas

Phase scope (use this as your source of truth for what each phase covers)
PhaseScope summaryFindingsDecisions log refsSpecial notes2Persistence contracts: versioned snapshots, partial-row INSERT fix, AIM-13 dict envelope, decay alert payload, trade-outcome bus nameF-02, F-03, F-05, F-17, F-18§2 Group D (Q-05), §2 Group J (Q-12-transport), §5 Phase 2 rowStreams kept (not pub/sub). F-05 uses JSON dict envelope option (a). F-18 deprecates pub/sub publisher.3Orchestrator wiring & dispatchF-01, F-04, F-13, F-20, F-21, F-42§2 Group B (Q-03 cadence), §2 Group C (Q-04 — flagged partial), §2 Group E (Q-13)F-21 closes by doc-edit not code (reclassify as by-design). F-04 has pending re-ask in §3.2 — flag if Isaac hasn't answered. PG-01C runs after every market session globally per Q-03.4AIM lifecycle / DMA / HDWM correctionsF-09, F-10, F-11, F-12§2 Group D (Q-09, Q-26 partial, Q-27 partial)Q-09 = single-gate restoration. Q-26 / Q-27 are §3.2 re-asks — Phase 4 may need to wait, or proceed with explicit deferral markers.5BOCPD / CUSUM / Level EscalationF-07, F-19§2 Group E (Q-07, Q-29)Q-07 = Redis canonical for bocpd:{asset}; add Redis writer in b2_bocpd. Q-29 = literal nested-loop CUSUM, no shortcuts. Doc 32 PG-15 needs amending — flag as doc edit for Isaac.6AIM modifier realignmentF-38, F-39, F-40, F-41§2 Group F (Q-22 partial, Q-23 partial, Q-24, Q-05)AIM-7 stays disabled (Q-24). Q-22 / Q-23 sub-points are §3.2 re-asks — Phase 6 partly blocked until resolved. F-38 has potential sign-flip (DEC-01 vs canvas) — must not ship until clarified.7PG-09 / PG-10 / PG-13 pseudotrader / injection / auto-expansion chainF-22, F-23, F-24, F-25, F-26, F-27, F-28, F-29§2 Group C (Q-14, Q-15), §2 Resolved Q-16Two-pass session: design doc first (captain_online_replay architecture), then implementation plan. Q-14 = build replay against real online B1–B6, not SignalReplayEngine. Q-15 = realised P&L from D03. Largest single-phase scope.8TSM PG-14 + Circuit Breaker paramsF-30, F-31, F-32, F-33, F-34§2 Group G (Q-17, Q-31, Q-32, Q-33), §2 Resolved Q-18Q-31 = honour D12.sizing_override in MC. Q-32 = Offline owns RPT-07. Q-33 = drop p_value gate, keep n<10 + cold_start. Q-17 has soft confirmation flag — proceed with loss-only interpretation, flag if Isaac corrects.9Block 9 system health diagnosticF-35, F-36, F-37§2 Group H (Q-19, Q-20, Q-21, Q-34)D7 deferred (Q-21). D4 = monthly hit rate (Q-20). D3 needs schema column from Phase 1. Equal weights for overall_health (Q-34).10HMM / AIM-16 end-to-endF-14, F-15, F-16§2 Group B (Q-10 engineering call, Q-11 partial)Gated on Nomaan's Q-10 decision (TVTP in v1 vs v1b). Q-11 dual-write boundary is §3.2 re-ask — affects D26 writer split. F-01 already wired in Phase 3; Phase 10 makes it correct.11Governance / safetyF-08, F-43§2 Group I (Q-08 resolved, Q-25, Q-28 soft)F-08 = two-phase request_rollback → admin signal → commit_rollback. F-43 = doc edit reclassifying "RESOLVED" to "checkpoint logging only — replay deferred". Q-28 cold-storage soft flag.12Hygiene refactor (per-AIM module split)None (no findings)§2 Group J (Q-36)Mechanical extraction of shared/aim_compute.py into aim_NN_*.py modules per canvas. No semantic changes. Tests split per module. Update canvases after refactor lands.
Required structure for every Claude Code prompt you write
Each of the 11 prompts must follow this exact shape — keep them tight, concise, and Cursor-ready:

Role line: "You are generating a Phase N build plan for a 12-phase fix campaign on Captain Offline. The plan will be executed by Cursor Composer 2."
Inputs section: numbered list, in priority order, of: decisions log (§2 Group rows + §5 Phase row), audit (specific F-IDs), phase-specific spec docs, codebase access.
Workflow section: two-stage with explicit approval gate.

Stage 1 = AUDIT PASS (read-only): inspect current code state for every affected file, list writers/readers, cross-check against decisions log, flag any pending re-asks from §3.2 that block this phase, output findings as a markdown summary, STOP and wait for "approved, continue".
Stage 2 = PLAN GENERATION: produce phaseN_<scope>_build_plan.md at repo root.


Plan structure: the build plan must be organised as numbered batches, where each batch addresses one finding (or one tightly-coupled group). Each batch must contain: pre-flight checks, file paths + line ranges to modify, exact change shape (what becomes what), test additions (what to write, where to put it, what it asserts), exit criteria, and rollback procedure.
Anti-hallucination rule: "Do not guess file paths, line ranges, or spec citations. Verify against the actual codebase or attached documents. When ambiguous, flag rather than invent."
Spec authority chain: "Decisions log §2 supersedes audit; audit supersedes spec; spec supersedes code. Where the decisions log is silent, follow audit. Where audit is silent, follow spec. Never resolve a conflict by inventing a third option."
Pending-question handling: "If a finding's resolution depends on a pending §3.2 re-ask that has not been answered, mark the corresponding batch as BLOCKED and proceed with the rest of the phase. Do not invent the missing decision."
Deliverable filename and location: specified per phase.
Phase-specific notes: copy the "Special notes" column from the table above into a Phase-specific constraints section near the bottom.

Phase 7 special handling
Phase 7 is the only phase that warrants two Claude Code passes. The Phase 7 prompt must instruct Claude Code to:

Pass 1 (design doc): produce phase7_design_captain_online_replay.md covering the architecture for captain_online_replay — how online B1–B6 are reused against historical bars without breaking the live path, what the replay harness looks like, what state needs to be reconstructible per session, and how the audit's RESOLVED status on G-OFF-016 gets satisfied. Stop. Wait for design approval.
Pass 2 (implementation plan): once design is approved, produce phase7_pseudotrader_chain_build_plan.md with batches.

All other phases are single-pass.
Output format from this chat
Produce 11 sections, one per phase (Phases 2 through 12). Each section is:

A short H2 header naming the phase
A one-paragraph context line stating which findings the phase closes and which spec docs the user needs to attach
The full Claude Code prompt in a single fenced code block, ready to paste

Keep each prompt as concise as Phase 1's was. Direct, actionable, no padding. Do not generate the build plans themselves — only the prompts that will instruct Claude Code to generate them.