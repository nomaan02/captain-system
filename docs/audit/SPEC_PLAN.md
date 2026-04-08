# Phase 2 Spec Plan — Obsidian Consolidation + Master Gap Analysis

Created: 2026-04-08
Status: READY FOR EXECUTION

---

## Discovery Findings

### Critical Path Correction

CLAUDE.md references `docs/CAPTAIN-FUNCTION-DOCS-NEW-AMENDMENTS/` — **this directory does NOT exist**.
V3 authoritative specs live at `docs/AIM-Specs/new-aim-specs/` (9 files, ~9,895 lines).
Per CLAUDE.md rule: "V3 amendments SUPERSEDE original specs where conflicts exist."

### Source Priority (all executors follow this)

1. **PRIMARY** — V3 repo specs (`docs/AIM-Specs/new-aim-specs/`) — longer, authoritative, supersede originals
2. **SUPPLEMENTARY** — Obsidian vault (`/mnt/c/Users/nomaa/Documents/Quant_Project/Direct Information/`) — original Isaac specs, read via WSL2 filesystem (no Obsidian MCP needed)
3. **REFERENCE** — Phase 1 audit files (`docs/audit/`) — code-level findings from codebase audit

---

## Vault Inventory

### Source 1: Obsidian Vault (25 docs, 5,660 lines)

Path: `/mnt/c/Users/nomaa/Documents/Quant_Project/`

| Doc # | File | Lines | Area |
|-------|------|-------|------|
| 00 | 00_GAP_ANALYSIS.md | 457 | Index / gap catalog |
| 01 | 01_DIAGRAM_CONVENTIONS.md | 85 | Conventions |
| 12 | 12_Input_Variables.md | 158 | P1 features (V-001–V-075) |
| 13 | 13_Transformations.md | 87 | P1 transformations (T-001–T-039) |
| 14 | 14_Binary_Events.md | 81 | P1 binary events (BE-001–BE-051) |
| 15 | 15_Model_Definitions.md | 188 | Model specs (M-001–M-070) |
| 16 | 16_Strategy_Type_Registry.md | 42 | Strategy types ST-01–ST-06 |
| 17 | 17_Sample_Periods_Per_Asset.md | 176 | Per-asset sample periods |
| 18 | 18_GUI_Dashboard.md | 149 | GUI panel spec |
| 19 | 19_User_Management.md | 158 | RBAC / user management |
| 20 | 20_Signal_Distribution.md | 108 | Signal distribution / anti-copy |
| 21 | 21_Implementation_Guides.md | 205 | DMA/MoE, BOCPD, Kelly guides |
| 22 | 22_HMM_Opportunity_Regime.md | 151 | AIM-16 HMM spec |
| 23 | 23_XGBoost_Classifier.md | 156 | XGBoost regime classifier |
| 24 | 24_P3_Dataset_Schemas.md | 265 | QuestDB schema spec |
| 25 | 25_Fee_Payout_System.md | 143 | Fee resolution system |
| 26 | 26_Notification_System.md | 159 | 26 event types, priority routing |
| 27 | 27_Contract_Rollover.md | 79 | Futures contract rollover |
| 28 | 28_Pseudotrader_System.md | 121 | Account-aware pseudotrader |
| 29 | 29_Operational_Policies.md | 199 | Governance, change mgmt |
| 30 | 30_P1_Consolidated_Config.md | 89 | P1 consolidated config |
| 31 | 31_AIM_Individual_Specifications.md | 767 | Per-AIM specs (16 AIMs) |
| 32 | 32_P3_Offline_Full_Pseudocode.md | 782 | Offline pseudocode |
| 33 | 33_P3_Online_Full_Pseudocode.md | 475 | Online pseudocode |
| 34 | 34_P3_Command_Full_Pseudocode.md | 380 | Command pseudocode |

**Note:** Docs 02–11 do not exist in the vault (Part 1 docs, live in most-production repo).

#### Canvas Files (7)

| Directory | File |
|-----------|------|
| Functional/ | Programs 1-2-3.canvas |
| Functional/ | AIM System.canvas |
| Functional/ | DMA MoE Meta-Learning Pipeline.canvas |
| Backend/ | VALIDATE Programs 1-2-3.canvas |
| Pseudocode/ | Programs 1-2-3 1.canvas (variant) |
| Pseudocode/ | AIM System.canvas (variant) |
| Pseudocode/ | DMA MoE Meta-Learning Pipeline 1.canvas (variant) |

### Source 2: V3 Repo Specs (9 files, ~9,895 lines)

Path: `docs/AIM-Specs/new-aim-specs/`

| File | Lines | Maps To Obsidian | Notes |
|------|-------|-----------------|-------|
| Program3_Online.md | 1,756 | doc 33 (475L) | 3.7x longer — full V3 Online spec |
| Program3_Offline.md | 1,729 | doc 32 (782L) | 2.2x longer — full V3 Offline spec |
| AIM_Extractions.md | 3,723 | doc 31 (767L) | 4.9x longer — detailed AIM paper extractions |
| HMM_Opportunity_Regime_Spec.md | 578 | doc 22 (151L) | 3.8x longer — full HMM spec |
| DMA_MoE_Implementation_Guide.md | 339 | doc 21 (205L) | 1.7x longer — DMA/MoE guide |
| P3_Dataset_Schemas.md | 565 | doc 24 (265L) | 2.1x longer — field-level schemas |
| Cross_Reference_PreDeploy_vs_V3.md | 367 | — | V3 delta mapping |
| CaptainNotes.md | 563 | — | Dev notes |
| Nomaan_Edits_P3.md | 275 | — | Command amendments |

### Source 3: Phase 1 Audit Reports (complete)

Path: `docs/audit/`

| File | Lines | Coverage |
|------|-------|----------|
| captain_online.md | 1,457 | Sessions 1–3: Online core, ingestion, Kelly-to-signal |
| captain_offline.md | 804 | Sessions 4a–4b: Orchestrator, AIM lifecycle, BOCPD |
| captain_command.md | 930 | Session 5b: Command interface (36 files, 6 critical) |
| cross_cutting.md | 682 | Session 6: Shared library, config, Docker |

---

## Session Plan

| Session | Prompt ID | Writes | Primary Docs (V3 repo) | Supplementary (Obsidian) | Est. Read |
|---------|-----------|--------|------------------------|--------------------------|-----------|
| CC2 | SPEC-EXEC-01 | §1–2 | Program3_Online.md (1756L) | doc 33 (475L), doc 30 (89L) | ~2,320L |
| CC3 | SPEC-EXEC-02 | §3 | AIM_Extractions.md (3723L), HMM_Opportunity_Regime_Spec.md (578L) | doc 31 (767L), doc 22 (151L) | ~5,219L |
| CC4 | SPEC-EXEC-03 | §4–6 | Program3_Offline.md (1729L), DMA_MoE_Implementation_Guide.md (339L) | doc 32 (782L), doc 21 (205L) | ~3,055L |
| CC5 | SPEC-EXEC-04 | §7–8 | Nomaan_Edits_P3.md (275L) | doc 34 (380L), doc 18 (149L), doc 26 (159L) | ~963L |
| CC6 | SPEC-EXEC-05 | §9–10 | P3_Dataset_Schemas.md (565L) | doc 24 (265L), doc 25 (143L), doc 20 (108L), doc 27 (79L), doc 28 (121L) | ~1,281L |
| CC7 | SPEC-EXEC-06 | §11–13 | Cross_Reference_PreDeploy_vs_V3.md (367L) | canvas files, doc 15 (188L), doc 16 (42L), doc 29 (199L) | ~796L+ |
| — | CHECKPOINT | — | Review full spec_reference.md | Patch if needed | — |
| CC8 | SPEC-EXEC-07 | GAP | spec_reference.md + 4 audit files + codebase | — | ~4,000L+ |

**Total estimated reading:** ~13,634 lines of spec docs + canvas JSON + codebase grep for EXEC-07.

---

## Output Structure

All sessions write to: **`docs/audit/spec_reference.md`**

| Section | Title | Writer | Content |
|---------|-------|--------|---------|
| §1 | Session Definitions | EXEC-01 | NY/LON/APAC, session_match(), open times, asset mapping |
| §2 | Online Blocks 1–9 | EXEC-01 | Per block: PG ID, I/O, QuestDB R/W, Redis, logic |
| §3 | AIM System (AIMs 1–16) | EXEC-02 | Per AIM: tier, sources, thresholds, warm-up, lifecycle, HDWM |
| §4 | Offline Blocks 1–9 | EXEC-03 | Per block: PG ID, I/O, QuestDB R/W, Redis, logic |
| §5 | Kelly 7-Layer Pipeline | EXEC-03 | Layer-by-layer: inputs, formula, dataset refs |
| §6 | Circuit Breaker 5 Layers | EXEC-03 | Per layer: condition, action, dataset refs |
| §7 | Command Blocks 1–10 | EXEC-04 | Per block: PG ID, I/O, endpoints, QuestDB |
| §8 | GUI Panels + Security | EXEC-04 | Panels, autonomy tiers, 6 outbound fields |
| §9 | QuestDB Dataset Master List | EXEC-05 | Every D00–D27: purpose, key fields, writer, reader, when |
| §10 | Supporting Systems | EXEC-05 | Fee resolution, signal distribution, rollover, pseudotrader |
| §11 | Feedback Loops (6) | EXEC-06 | Per loop: trigger, data flow, datasets |
| §12 | Daily Lifecycle | EXEC-06 | 19:00 SOD reset -> pre-session -> OR -> trading -> EOD -> recon |
| §13 | Strategy Types + Exit Grid | EXEC-06 | ST-01–ST-06, exit grid, variant counts |

Final output: **`docs/audit/master_gap_analysis.md`** (EXEC-07 only)

---

## Execution Order

```
SPEC-EXEC-01  (must run first — establishes session definitions)
     |
     v
SPEC-EXEC-02 through 06  (any order, sequential writes to spec_reference.md)
     |
     v
CHECKPOINT  (orchestrator reviews all 13 sections, patches if needed)
     |
     v
SPEC-EXEC-07  (LAST — reads completed spec_reference.md + audit files + codebase)
```

---

## Between-Session Protocol

When pasting the next executor prompt, prepend the passover block from the previous session:

```
## Previous Session Summary
[Paste passover block from bottom of spec_reference.md]

## Your Assignment
[Paste next prompt from spec_executor_prompts.md]
```

---

## Tracking Checklist

- [ ] SPEC-EXEC-01 complete -> §1–2 written
- [ ] SPEC-EXEC-02 complete -> §3 written
- [ ] SPEC-EXEC-03 complete -> §4–6 written
- [ ] SPEC-EXEC-04 complete -> §7–8 written
- [ ] SPEC-EXEC-05 complete -> §9–10 written
- [ ] SPEC-EXEC-06 complete -> §11–13 written
- [ ] CHECKPOINT: all 13 sections populated, no gaps
- [ ] SPEC-EXEC-07 complete -> master_gap_analysis.md written
- [ ] Orchestrator final review of master_gap_analysis.md

---

## Patch Protocol

After each executor session, the orchestrator:
1. Reads updated spec_reference.md
2. Checks: all assigned sections present? Extraction complete?
3. If gaps found -> produce SPEC-EXEC-XX-PATCH prompt targeting specific missing content
4. Before EXEC-07: confirm all 13 sections are populated and internally consistent
5. After EXEC-07: review master_gap_analysis.md for completeness (every gap has both spec citation AND code citation)
