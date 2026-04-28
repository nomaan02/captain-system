Phase 0 done. Skill written to .claude/skills/captain-spec-audit/SKILL.md. Below is the corpus-prep summary so you can sanity-check before I fan out Phase 2.

Phase 0 — Corpus Prep Deliverable
Corpus inventory (docs2/spec-docs-02/offline/)
File	Type	Nodes/Edges	Coverage
32_P3_Offline_Full_Pseudocode.md
MD (803 lines)
—
Full pseudocode, all 9 blocks, PG-01..PG-17, Version Snapshot Policy. Authoritative.
22_HMM_Opportunity_Regime 1.md
MD (162 lines)
—
AIM-16 deep dive (Baum-Welch, K=3, TVTP, α=0.3). Authoritative for PG-01C.
P3 Offline.canvas
Canvas
1 text node / 0 edges
Block-level arch with explicit MODULE: x.py / R/W: P3-D** / DEPS: per PG.
Kelly 7 Layer Pipeline.canvas
Canvas
1 text node / 0 edges
L1 (Offline B8) → L2–L7 (Online B4). Side inputs + module names.
DMA MoE Meta-Learning Pipeline.canvas
Canvas
1 text node / 0 edges
Offline DMA → Online MoE → Kelly L5.
AIM System.canvas
Canvas
22 nodes / 8 edges
Per-AIM register by seed-type with formulas, warm-up days, tier, dispatch, DMA/MoE. Authoritative for individual AIM modifier semantics.
AIM System 1.canvas
Canvas
2 nodes (duplicates) / 0 edges
Flat ASCII version of AIM System with explicit MODULE: aim_NN_xxx.py / R/W tags.
Spec self-consistency findings (already detected; will appear in §1 of the audit)
SC-01 AIM System 1.canvas is a flat-text duplicate of AIM System.canvas. The structured one is canonical; the flat one provides the aim_NN_*.py filename hints that the implementation does not actually follow (see SC-05).
SC-02 22_HMM_Opportunity_Regime 1.md carries Obsidian's collision suffix " 1". Cosmetic.
SC-03 (spec gap → Q for Isaac) Doc 32 cross-references seven external docs (24 Schemas, 31 AIM Individual Specs, 21 Implementation Guides, Part-1 docs 04/05/07/08, doc 33 Online). None are in the offline corpus. Schemas are filled by shared/canonical_schemas.py; AIM specs are partially filled by the canvas. Q: confirm canonical_schemas.py is authoritative for D26 and that doc 31 is not needed.
SC-04 (naming-only, not a finding) Spec uses bocpd.py, cusum.py, dma_engine.py, kelly_pipeline.py etc. Code uses block-prefixed b2_bocpd.py, b2_cusum.py, b1_dma_update.py, b8_kelly_update.py. Translation table is in the skill; subagents will use it.
SC-05 (likely Phase-2 finding) Spec/canvas describe one file per AIM (aim_01_vrp.py … aim_15_volume.py). Code consolidates all 16 modifiers into shared/aim_compute.py (_aim01_vrp … _aim15_volume, _aim16_hmm). Likely intentional consolidation; flag CV-01 to Isaac.
SC-06 (spec gap → Q for Isaac) Spec/canvas reference standalone kelly_pipeline.py, aim_aggregator.py, moe_gating.py, cb_replay.py, cb_grid.py, transition.py. Code consolidates Kelly into b8_kelly_update.py/b4_kelly_sizing.py, AIM aggregation into shared/aim_compute.py, transition/CB-replay/CB-grid into block files. Possible structural divergence vs intentional consolidation — Phase 2 will resolve.
Spec → Code → QuestDB coverage matrix (full version in skill)
20 PGs spread across 9 spec blocks → 16 implementation files in captain-offline/captain_offline/blocks/ plus shared/aim_compute.py. Every PG has a confirmed implementation file. Tables touched by Offline (all confirmed present in shared/canonical_schemas.py): D00, D01, D02, D03, D04, D05, D06, D06b, D08, D11, D12, D13, D17, D18, D22, D25, D26.

Note: P2-D06 / P2-D07 are read by Block 4 (PG-10) and Block 9, but no p2_d* table exists in canonical_schemas.py. Phase 2 will need to determine if they live in data/p2_outputs/ JSON or are genuinely missing — either way it's a finding.

Captain-spec-audit skill (created)
Path: .claude/skills/captain-spec-audit/SKILL.md. Contains:

Audit constraints (read-only, prod>replay, docs2 = single source, doc 32 governs).
Authoritative corpus inventory.
The six SC findings above pre-filled.
Full coverage matrix with every PG mapped to its implementation file and stores.
Standard finding template (verbatim from the 2026-04-22 audit).
Output document structure (6 sections matching the prior audit).
11-subagent fan-out plan for Phase 2 (one per block-group; SA-9 owns AIM modifiers; SA-10/11 are cross-cutting for orchestrator+Redis+schema diff).
Phase 2 fan-out plan (preview)
Subagent	Owns	Files
SA-1
Block 1 lifecycle/DMA/HDWM/Drift/Version
b1_aim_lifecycle.py, b1_dma_update.py, b1_hdwm_diversity.py, b1_drift_detection.py, version_snapshot.py
SA-2
Block 1 — AIM-16 HMM training (PG-01C)
b1_aim16_hmm.py
SA-3
Block 2 — Decay (BOCPD/CUSUM/L2-L3)
b2_bocpd.py, b2_cusum.py, b2_level_escalation.py
SA-4
Block 3 + 4 — Pseudotrader + Injection + Transition
b3_pseudotrader.py, b4_injection.py
SA-5
Block 5 + 6 — Sensitivity + Auto-Expansion
b5_sensitivity.py, b6_auto_expansion.py
SA-6
Block 7 — TSM Simulation
b7_tsm_simulation.py
SA-7
Block 8 — Kelly L1 + β_b
b8_kelly_update.py, b8_cb_params.py
SA-8
Block 9 — System Health (8 dimensions)
b9_diagnostic.py
SA-9
AIM-01..15 individual modifier formulas
shared/aim_compute.py
SA-10
Cross-cutting wiring (orchestrator, Redis, structural divergence CV-01/02)
orchestrator.py, shared/redis_client.py, shared/aim_compute.py
SA-11
QuestDB schema diff (P2-D06/D07 absence; field-by-field coverage)
shared/canonical_schemas.py, scripts/init_questdb.py
All subagents will run with readonly: true and return findings in the standard template. Main thread will dedupe (e.g. SA-3 and SA-7 both touch P3-D04), severity-rank, and assemble the audit doc.

Ready to proceed?
Two things to confirm before I launch Phase 2:

Audit doc filename — docs2/audits/2026-04-22_offline_spec_vs_code_audit.md (today's date, scope-suffixed). OK?
SC-03 / CV-01 stance — for Phase 2, do you want subagents to (a) flag the structural divergence between shared/aim_compute.py and the spec's "one file per AIM" as a LOW finding (architectural), or (b) treat it as settled-by-implementation and skip the finding? My default is (a) — flag it once, severity LOW, with a note that consolidation is reasonable.
Once you greenlight those two, I'll launch all 11 subagents in parallel.