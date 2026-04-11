# Obsidian Vault Enrichment Plan

> Generated: 2026-04-11 | Status: APPROVED — awaiting execution prompt
> Vault: `/mnt/c/Users/nomaa/Documents/Quant_Project/`
> MCP server: `obsidian` (obsidian-mcp-pro)
> Scope: 27 existing notes + 10 stubs (excluding `_claude/` directory and all `.canvas` files)

---

## Decisions (all confirmed)

| # | Question | Decision |
|---|----------|----------|
| 1 | Doc 01 tags | All 5 System 1 tags (P1, P2, P3-offline, P3-online, P3-command) |
| 2 | Shorthand D-store refs (D01 without P3- prefix) | Normalize text to `P3-D01` format, then link |
| 3 | Part 1 doc N refs (docs 02-11 not in vault) | Create stub notes so all links resolve |
| 4 | System 2 D-store refs | Skip linking, but add cross-system tags to System 2 docs |
| 5 | Bold-number-only refs in metadata tables | Link them (stubs make all targets valid) |
| 6 | Fix ~/obsidian-spec symlink | Yes |

---

## Phase 0: Discovery (COMPLETE)

All 34 notes read. Key findings:

- **Zero YAML frontmatter** on any content note (docs 12-34 use inline metadata tables, not YAML)
- **Zero wikilinks** anywhere — all cross-references are plain text
- **No inline-edit MCP tool** — must use filesystem `Edit` at `/mnt/c/Users/nomaa/Documents/Quant_Project/...`
- **Symlink broken** — `~/obsidian-spec` is a 0-byte regular file, not a symlink
- **Both kanbans empty** — safe to delete
- **`_claude/CLAUDE.md`** is 45 lines, needs audit/update

### Complete doc inventory (after stubs)

```
System 1/Direct Information/
├── 00_GAP_ANALYSIS.md
├── 01_DIAGRAM_CONVENTIONS.md
├── 02_P2_Regime_Selection.md              ← STUB
├── 03_Captain_Architecture.md             ← STUB
├── 04_Captain_Offline.md                  ← STUB
├── 05_Captain_Online.md                   ← STUB
├── 06_Captain_Command.md                  ← STUB
├── 07_AIM_System.md                       ← STUB
├── 08_Kelly_Sizing_Pipeline.md            ← STUB
├── 09_Risk_Management.md                  ← STUB
├── 10_Dataset_Catalogue.md                ← STUB
├── 11_Reserved.md                         ← STUB
├── 12_Input_Variables.md
├── 13_Transformations.md
├── 14_Binary_Events.md
├── 15_Model_Definitions.md
├── 16_Strategy_Type_Registry.md
├── 17_Sample_Periods_Per_Asset.md
├── 18_GUI_Dashboard.md
├── 19_User_Management.md
├── 20_Signal_Distribution.md
├── 21_Implementation_Guides.md
├── 22_HMM_Opportunity_Regime.md
├── 23_XGBoost_Classifier.md
├── 24_P3_Dataset_Schemas.md
├── 25_Fee_Payout_System.md
├── 26_Notification_System.md
├── 27_Contract_Rollover.md
├── 28_Pseudotrader_System.md
├── 29_Operational_Policies.md
├── 30_P1_Consolidated_Config.md
├── 31_AIM_Individual_Specifications.md
├── 32_P3_Offline_Full_Pseudocode.md
├── 33_P3_Online_Full_Pseudocode.md
└── 34_P3_Command_Full_Pseudocode.md
```

---

## Phase 1: Fix Symlink + Kanban Cleanup + Create Stubs

**Estimated effort:** 3 minutes

### 1a. Fix the broken symlink

```bash
rm /home/nomaan/obsidian-spec
ln -s "/mnt/c/Users/nomaa/Documents/Quant_Project" /home/nomaan/obsidian-spec
```

### 1b. Delete empty kanban boards

Use `mcp__obsidian__delete_note` on:
- `Untitled Kanban.md` (empty — frontmatter only)
- `Untitled Kanban 1.md` (one checked-off "AIMs" card, no useful content)

### 1c. Create stub notes for Part 1 docs 02-11

Use `mcp__obsidian__create_note` for each. All stubs go in `System 1/Direct Information/`.

| File | Title | Tags |
|------|-------|------|
| `02_P2_Regime_Selection.md` | P2 — Regime Selection | P2 |
| `03_Captain_Architecture.md` | Captain Architecture | P3-offline, P3-online, P3-command |
| `04_Captain_Offline.md` | Captain Offline | P3-offline |
| `05_Captain_Online.md` | Captain Online | P3-online |
| `06_Captain_Command.md` | Captain Command | P3-command |
| `07_AIM_System.md` | AIM System | P3-offline, P3-online |
| `08_Kelly_Sizing_Pipeline.md` | Kelly Sizing Pipeline | P3-offline, P3-online |
| `09_Risk_Management.md` | Risk Management | P3-offline, P3-online, P3-command |
| `10_Dataset_Catalogue.md` | Dataset Catalogue | P1, P2 |
| `11_Reserved.md` | Reserved | P1 |

Each stub has this format:
```markdown
---
tags: [relevant tags]
status: stub
---
# NN — Title
> Part 1 original document. Not yet transferred to this vault.
```

### Verification

- `ls -la ~/obsidian-spec` shows symlink → `/mnt/c/Users/nomaa/Documents/Quant_Project`
- `mcp__obsidian__list_notes` returns 42 notes (34 original - 2 kanbans + 10 stubs)
- `mcp__obsidian__search_by_frontmatter` with property `status`, value `stub` returns 10 notes

---

## Phase 2: Apply Tags via Frontmatter

**Estimated effort:** 5 minutes (37 `update_frontmatter` calls — 27 existing + 10 stubs done in Phase 1)

Use `mcp__obsidian__update_frontmatter` with `{"tags": ["P1", "P3-online", ...]}` for each note.

### Tag Assignment Table — Direct Information (25 existing notes)

| Doc | File | Tags |
|-----|------|------|
| 00 | `System 1/Direct Information/00_GAP_ANALYSIS.md` | P1, P2, P3-offline, P3-online, P3-command |
| 01 | `System 1/Direct Information/01_DIAGRAM_CONVENTIONS.md` | P1, P2, P3-offline, P3-online, P3-command |
| 12 | `System 1/Direct Information/12_Input_Variables.md` | P1 |
| 13 | `System 1/Direct Information/13_Transformations.md` | P1 |
| 14 | `System 1/Direct Information/14_Binary_Events.md` | P1 |
| 15 | `System 1/Direct Information/15_Model_Definitions.md` | P1, P2 |
| 16 | `System 1/Direct Information/16_Strategy_Type_Registry.md` | P1 |
| 17 | `System 1/Direct Information/17_Sample_Periods_Per_Asset.md` | P1 |
| 18 | `System 1/Direct Information/18_GUI_Dashboard.md` | P3-command |
| 19 | `System 1/Direct Information/19_User_Management.md` | P3-command, P3-online |
| 20 | `System 1/Direct Information/20_Signal_Distribution.md` | P3-online, P3-command |
| 21 | `System 1/Direct Information/21_Implementation_Guides.md` | P3-offline, P3-online |
| 22 | `System 1/Direct Information/22_HMM_Opportunity_Regime.md` | P3-offline, P3-online |
| 23 | `System 1/Direct Information/23_XGBoost_Classifier.md` | P2, P3-online |
| 24 | `System 1/Direct Information/24_P3_Dataset_Schemas.md` | P3-offline, P3-online, P3-command |
| 25 | `System 1/Direct Information/25_Fee_Payout_System.md` | P3-command |
| 26 | `System 1/Direct Information/26_Notification_System.md` | P3-command |
| 27 | `System 1/Direct Information/27_Contract_Rollover.md` | P1, P3-online |
| 28 | `System 1/Direct Information/28_Pseudotrader_System.md` | P3-offline |
| 29 | `System 1/Direct Information/29_Operational_Policies.md` | P3-offline, P3-online, P3-command |
| 30 | `System 1/Direct Information/30_P1_Consolidated_Config.md` | P1 |
| 31 | `System 1/Direct Information/31_AIM_Individual_Specifications.md` | P3-offline, P3-online |
| 32 | `System 1/Direct Information/32_P3_Offline_Full_Pseudocode.md` | P3-offline |
| 33 | `System 1/Direct Information/33_P3_Online_Full_Pseudocode.md` | P3-online |
| 34 | `System 1/Direct Information/34_P3_Command_Full_Pseudocode.md` | P3-command |

### Tag Assignment Table — System 2 (with cross-system tags)

| File | Tags |
|------|------|
| `System 2/Discussions/Discussion 1.md` | system2, P3-offline, P3-online |
| `System 2/Discussions/Discussion 2.md` | system2, P3-offline, P3-online |
| `System 2/Discussions/GPTDR.md` | system2 |
| `System 2/Overviews/System 2 Overview.md` | system2, P1, P2, P3-offline, P3-online, P3-command |

### Anti-pattern guards

- Do NOT use `#` prefix in the tags array — Obsidian adds it automatically
- Do NOT overwrite existing frontmatter — `update_frontmatter` merges, so this is safe
- Stub notes already have tags from Phase 1 creation — no update needed for those

### Verification

- `mcp__obsidian__get_tags` returns all 6 tag names with correct counts
- `mcp__obsidian__search_by_tag` for each tag returns expected notes
- Spot-check: `mcp__obsidian__get_note` on 3 random docs confirms YAML frontmatter block present

---

## Phase 3: Apply Wikilinks

**Estimated effort:** 15-20 minutes (bulk of the work)

Use filesystem `Edit` tool on files at `/mnt/c/Users/nomaa/Documents/Quant_Project/System 1/Direct Information/...`

### Reference Lookup Tables

#### A. Doc ID → Wikilink Target

ALL doc IDs are now valid targets (stubs fill the 02-11 gap).

| Pattern (case-insensitive) | Wikilink |
|---------------------------|----------|
| doc 00 | `[[00_GAP_ANALYSIS\|doc 00]]` |
| doc 01 | `[[01_DIAGRAM_CONVENTIONS\|doc 01]]` |
| doc 02 | `[[02_P2_Regime_Selection\|doc 02]]` |
| doc 03 | `[[03_Captain_Architecture\|doc 03]]` |
| doc 04 | `[[04_Captain_Offline\|doc 04]]` |
| doc 05 | `[[05_Captain_Online\|doc 05]]` |
| doc 06 | `[[06_Captain_Command\|doc 06]]` |
| doc 07 | `[[07_AIM_System\|doc 07]]` |
| doc 08 | `[[08_Kelly_Sizing_Pipeline\|doc 08]]` |
| doc 09 | `[[09_Risk_Management\|doc 09]]` |
| doc 10 | `[[10_Dataset_Catalogue\|doc 10]]` |
| doc 11 | `[[11_Reserved\|doc 11]]` |
| doc 12 | `[[12_Input_Variables\|doc 12]]` |
| doc 13 | `[[13_Transformations\|doc 13]]` |
| doc 14 | `[[14_Binary_Events\|doc 14]]` |
| doc 15 | `[[15_Model_Definitions\|doc 15]]` |
| doc 16 | `[[16_Strategy_Type_Registry\|doc 16]]` |
| doc 17 | `[[17_Sample_Periods_Per_Asset\|doc 17]]` |
| doc 18 | `[[18_GUI_Dashboard\|doc 18]]` |
| doc 19 | `[[19_User_Management\|doc 19]]` |
| doc 20 | `[[20_Signal_Distribution\|doc 20]]` |
| doc 21 | `[[21_Implementation_Guides\|doc 21]]` |
| doc 22 | `[[22_HMM_Opportunity_Regime\|doc 22]]` |
| doc 23 | `[[23_XGBoost_Classifier\|doc 23]]` |
| doc 24 | `[[24_P3_Dataset_Schemas\|doc 24]]` |
| doc 25 | `[[25_Fee_Payout_System\|doc 25]]` |
| doc 26 | `[[26_Notification_System\|doc 26]]` |
| doc 27 | `[[27_Contract_Rollover\|doc 27]]` |
| doc 28 | `[[28_Pseudotrader_System\|doc 28]]` |
| doc 29 | `[[29_Operational_Policies\|doc 29]]` |
| doc 30 | `[[30_P1_Consolidated_Config\|doc 30]]` |
| doc 31 | `[[31_AIM_Individual_Specifications\|doc 31]]` |
| doc 32 | `[[32_P3_Offline_Full_Pseudocode\|doc 32]]` |
| doc 33 | `[[33_P3_Online_Full_Pseudocode\|doc 33]]` |
| doc 34 | `[[34_P3_Command_Full_Pseudocode\|doc 34]]` |

**Variant patterns to match:**
- `doc N` / `Doc N` / `document N` (case-insensitive)
- `**doc N**` (bold) → `**[[NN_Filename\|doc N]]**`
- `Part 1 doc N` → `[[NN_Filename\|Part 1 doc N]]` (preserving full display text)
- `Part 2 doc N` → `[[NN_Filename\|Part 2 doc N]]` (preserving full display text)
- `**N**` in metadata cross-ref tables → `**[[NN_Filename\|N]]**` (bold-number-only refs)

**Self-references:** Do NOT link a doc to itself (e.g., doc 32 referencing "doc 32" within `32_P3_Offline_Full_Pseudocode.md`).

#### B. Data Store → Wikilink Target

All P3 data stores are defined in doc 24.

| Pattern | Wikilink |
|---------|----------|
| `P3-D00` through `P3-D27` | `[[24_P3_Dataset_Schemas\|P3-Dxx]]` |

**Normalization rule (Decision #2):** In docs 29 and 34, shorthand refs like `D01`, `D02` (no `P3-` prefix) in RPT tables must be normalized to `P3-D01` format BEFORE linking. The edit changes both the text AND wraps it: `D01` → `[[24_P3_Dataset_Schemas\|P3-D01]]`.

**DO NOT link:**
- P1 data stores (`D-00` through `D-24` without P3 prefix, OUTSIDE RPT tables) — ambiguous
- P2 data stores (`P2-D01` through `P2-D09`) — no dedicated schema doc in vault
- Data store refs inside doc 24 itself (it's the defining doc — self-references are noise)
- Data store refs that appear inside code blocks
- Data store refs in System 2 docs (Decision #4 — cross-system, skip linking)

#### C. PG Reference → Wikilink Target

| PG Range | Defining Doc | Wikilink |
|----------|-------------|----------|
| PG-01 through PG-17 (incl. PG-01C, PG-09B, PG-09C, PG-16B, PG-16C) | doc 32 | `[[32_P3_Offline_Full_Pseudocode\|PG-xx]]` |
| PG-21 through PG-29 (incl. PG-25B, PG-27B) | doc 33 | `[[33_P3_Online_Full_Pseudocode\|PG-xx]]` |
| PG-25D | doc 20 | `[[20_Signal_Distribution\|PG-25D]]` |
| PG-30 through PG-41 | doc 34 | `[[34_P3_Command_Full_Pseudocode\|PG-xx]]` |

**DO NOT link:**
- PG refs inside their own defining doc (e.g., PG-01 inside doc 32)
- PG refs inside code blocks
- Wildcard patterns like `PG-*` (doc 01)

### Execution Strategy

Process files one at a time. For each file:
1. Read via filesystem `Read` tool at `/mnt/c/Users/nomaa/Documents/Quant_Project/System 1/Direct Information/...`
2. Identify all linkable references (skip code blocks, skip self-references)
3. Apply `Edit` replacements — use `replace_all: false` for unique strings, batch carefully for repeated patterns
4. For doc 29 and 34: normalize shorthand D-store refs first, then link
5. Verify with `mcp__obsidian__get_outlinks` after editing

### Per-File Reference Summary (updated with stubs)

| Doc | Doc Refs | D-Store Refs | PG Refs | Est. Edits |
|-----|----------|-------------|---------|------------|
| 00 | 01,02-11,12-30 (ALL linkable now) | P3-D16, P3-D27 | PG-25D,26,09,09B,09C,36 | ~30 |
| 01 | (none) | wildcards only (skip) | wildcards only (skip) | 0 |
| 12 | 13,14,15 | (none linkable) | (none) | ~3 |
| 13 | 12,14,15 | (none linkable) | (none) | ~3 |
| 14 | 12,13,15 | (none) | (none) | ~3 |
| 15 | 12,13,14,16 | (none linkable) | (none) | ~4 |
| 16 | 12,14,15 | (none) | (none) | ~3 |
| 17 | 12,15 | (none linkable) | (none) | ~2 |
| 18 | 06,07,31 | P3-D03 | PG-17 | ~5 |
| 19 | 03,06 | P3-D08, P3-D16 | PG-21 to PG-29 | ~14 |
| 20 | 05 | P3-D27 | PG-30 | ~3 |
| 21 | 04,05,07,08,31,18 | P3-D01 to D12 (6 stores) | PG-02,03,04,17,23 | ~18 |
| 22 | 05,07 | P3-D26 | PG-01C, PG-25B | ~7 |
| 23 | 02 | (none linkable) | (none) | ~1 |
| 24 | 10 | ALL P3-D (self, skip) | (none) | ~1 |
| 25 | 09 | (none) | (none) | ~1 |
| 26 | 06,10 | P3-D10 | (none) | ~3 |
| 27 | 01 | (none) | (none) | ~1 |
| 28 | 04,09 | P3-D08 | PG-09,09B,09C | ~6 |
| 29 | 03 | P3-D01 to D19 (normalize+link) | (none) | ~20 |
| 30 | 01 | (none linkable) | (none) | ~1 |
| 31 | 07,21,22 | P3-D03,D04,D07,D13,D23,D26 | (none) | ~12 |
| 32 | 04,07,08,22,31 | 16 P3-D stores | 21 PGs (self, skip) | ~10 |
| 33 | 05,18,21,23,25,31,32 | 14 P3-D stores | 12 PGs (self, skip) | ~25 |
| 34 | 06,18,19,26,29 | 15+ P3-D stores (normalize+link) | 13 PGs (self, skip) | ~25 |
| Disc 1 | (none) | (skip — cross-system) | (none) | 0 |
| Disc 2 | (none) | (none) | (none) | 0 |
| GPTDR | (none) | (none) | (none) | 0 |
| Sys2 Ov | (none) | (skip — cross-system) | (none) | 0 |

**Estimated total edits: ~200** (increased from ~145 due to stubs making docs 02-11 linkable)

### Anti-pattern guards

- NEVER create a wikilink inside a markdown code block (``` or indented 4 spaces)
- NEVER link a doc to itself
- NEVER double-link (if text is already `[[...]]`, skip it)
- Preserve surrounding formatting (bold, italic, table cells)
- When normalizing D-store shorthand: only normalize in RPT/reporting tables in docs 29 and 34, not elsewhere

---

## Phase 4: Verification

**Estimated effort:** 3 minutes

### Checks

1. **Broken links:** `mcp__obsidian__find_broken_links` — must return 0
2. **Orphan check:** `mcp__obsidian__find_orphans` — should show dramatic improvement from original 34/34
3. **Tag coverage:** `mcp__obsidian__get_tags` — all 6 tags present with correct counts
4. **Outlink spot-check:** `mcp__obsidian__get_outlinks` on docs 32, 33, 34 — should show multiple outlinks
5. **Backlink spot-check:** `mcp__obsidian__get_backlinks` on doc 24 — should show many inbound links
6. **Backlink spot-check:** `mcp__obsidian__get_backlinks` on stubs (e.g., doc 05) — should show inbound links from docs that reference it
7. **Grep for missed refs:** Search vault files for unlinked `doc [0-9]` and `PG-[0-9]` patterns outside code blocks and existing wikilinks

---

## Phase 5: Claude Integration

**Estimated effort:** 5 minutes

### 5a. Create `_claude/OBSIDIAN_ACCESS.md`

Create via `mcp__obsidian__create_note` at path `_claude/OBSIDIAN_ACCESS.md`.

Contents:
- Vault path: symlink `~/obsidian-spec` → real path `/mnt/c/Users/nomaa/Documents/Quant_Project/`
- How to read notes: `mcp__obsidian__get_note` (MCP) or `Read` tool at filesystem path
- How to search: `mcp__obsidian__search_notes` (full-text), `mcp__obsidian__search_by_tag` (filtered)
- How to list: `mcp__obsidian__list_notes` (all or by folder)
- How to edit: `mcp__obsidian__update_frontmatter` (tags/metadata), filesystem `Edit` (inline body changes), `mcp__obsidian__append_to_note` / `prepend_to_note` (add content)
- Tag taxonomy with meanings:
  - `P1` — Program 1 (Strategy Validation pipeline)
  - `P2` — Program 2 (Regime-Conditioned Selection)
  - `P3-offline` — Captain Offline (strategic brain)
  - `P3-online` — Captain Online (signal engine)
  - `P3-command` — Captain Command (linking layer)
  - `system2` — System 2 (next-gen research platform, design phase)
- Stub notes: files with `status: stub` frontmatter are placeholders for Part 1 originals not yet in vault
- Canvas warning: `.canvas` files are JSON, do not edit via Claude

### 5b. Update `_claude/CLAUDE.md`

Read current file (45 lines), audit, then update:
- Add top section: "Before implementing any Captain or MOST work, check the Obsidian vault via mcp-obsidian for relevant specs. See `_claude/OBSIDIAN_ACCESS.md` for access patterns."
- Remove/update any stale references
- Keep concise — reflect current state, not history

---

## Phase 6: Final

No git commit needed — vault is outside the captain-system repo (it's on the Windows side at `/mnt/c/`). The vault is not version-controlled.

### Final note count

- 42 notes total (25 existing content + 10 stubs + 4 System 2 + 3 _claude)
- 24 canvases (untouched)
- 6 tags in active use
- 0 orphan notes (target)
- 0 broken links (target)
