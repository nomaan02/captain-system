# Proposed amendment to doc 32 — PG-15 cp_prob source

**Context:** Q-07 (Audit Decisions Log §2 Group E) ratifies the Kelly canvas contract: Redis `captain:bocpd:{asset}` is the canonical source for `cp_prob`. Doc 32 PG-15 currently reads `P3-D04.current_changepoint_probability`, which is a divergent secondary source.

**Affected file:** `docs2/spec-docs-02/offline/32_P3_Offline_Full_Pseudocode.md`

**Section:** PG-15 (Block 8 — Kelly Parameter Updates).

**Current text (line 633):**
```
cp_prob = P3-D04[u].current_changepoint_probability
```

**Proposed text:**
```
cp_prob = redis.get("captain:bocpd:{u}")
   -- canonical per Q-07; falls back to P3-D04.current_changepoint_probability on miss.
   -- P3-D04 retains audit/replay role; Redis is the live read path.
```

**Rationale:** brings doc 32 into alignment with the Kelly 7-Layer Pipeline canvas L1 SIDE INPUTS column ("BOCPD cp_prob (Redis: bocpd:{asset} key)") and with the live code in `b2_bocpd.py` and `b8_kelly_update.py` after Phase 5 batches 1–2.

**Decision required from Isaac:** confirm wording (especially the fallback clause and the canvas-vs-code key shape `captain:bocpd:{asset}` rather than the canvas-literal `bocpd:{asset}`).
