# Audit cache — pre-flight bundle

**Git commit:** `ef24edf632eba2462527505d28c5a75b133fb612`  
**Branch:** `main`  
**Audit ISO timestamp:** `2026-05-12T14:08:20Z`

## Cached artefacts

| File | Contents |
|------|----------|
| `mem-search.md` | Claude-mem `search` MCP output — recent Captain-defining observations (indexed). |
| `smart-explore.md` | Intended AST structural map; MCP `smart_search` returned **zero symbols** for targeted queries — **manual fallback** (directory map + entrypoints). |
| `spec-audit.md` | Offline spec-vs-code audit digest — aggregates **`docs2/audits/2026-04-22_offline_spec_vs_code_audit.md`** + **`shared/canonical_schemas.py`** known-flag zones only **verified at HEAD**. |
| `trade-audit.md` | Signal → Redis → Command → TopstepX path audited against **`captain-trade-audit`** enum checklist **only at HEAD**. |

## Conflicting / ambiguous versions (from `/mem-search` + codebase verification)

1. **Repository root naming:** Memory results alternate paths such as `captain-command/...` vs `captain-system/captain-command/...`. **Canonical checkout:** `/home/nomaan/captain-system`; cite paths relative to this repo root.
2. **GUI block registry vs filesystem:** `captain-gui/src/constants/blockRegistry.js` lists `offline-b1-hmm` as `captain_offline/blocks/b1_hmm_training.py` and decay modules as `b2_*_decay.py`; implementation filenames at HEAD use **`b1_aim16_hmm.py`**, **`b2_bocpd.py`**, **`b2_cusum.py`**. Treat registry as UX catalog — **`captain_offline/blocks/*.py` is authoritative**.
3. **Skill mentions `/captain:signals:{user}`** vs **`STREAM_SIGNALS = stream:signals`**. Code publishes Redis Stream **`stream:signals`** (`shared/redis_client.py`). Confirm legacy naming elsewhere before documenting broker-visible queues only.

## Confirmation requested from repo owner

- Should **`captain-gui` block registry `sourceFile` paths** be updated to match actual `.py` filenames, or left as conceptual aliases?
- Is **`stream:signals`** the sole production signal transport (vs pub/sub `captain:signals:{user}`)? Current writers/consumers observed use **`stream:signals`**.
