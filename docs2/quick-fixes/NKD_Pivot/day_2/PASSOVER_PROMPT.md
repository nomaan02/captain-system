# Passover prompt — execute NKD Pivot day-2 commits C14/C15/C16

Copy everything between the BEGIN/END markers below into a fresh Cursor agent session in this workspace.

--- BEGIN PROMPT ---

You are landing three atomic commits (C14, C15, C16) for the Captain System NKD pivot. All the specifics — locked spec values, before/after code snippets, file:line citations, test rewrites, commit message templates, doc patches, deploy gates, risk register — live in:

- **Authoritative plan:** [`docs2/quick-fixes/NKD_Pivot/day_2/PLAN.md`](docs2/quick-fixes/NKD_Pivot/day_2/PLAN.md). Read it in full before writing code. Execute §2.C14, §2.C15, §2.C16 verbatim and apply the doc patches in §3.
- **Status audit (what's already done, do NOT redo):** [`docs2/quick-fixes/NKD_Pivot/day_2/COMPLETION_CHECKLIST.md`](docs2/quick-fixes/NKD_Pivot/day_2/COMPLETION_CHECKLIST.md).
- **Workspace rules (non-negotiable):** [`.cursor/rules/captain-deploy-and-tower-discipline.mdc`](.cursor/rules/captain-deploy-and-tower-discipline.mdc) §1 dual-remote push + SHA-parity check, §2 fish-shell discipline. [`CLAUDE.md`](CLAUDE.md) Frozen Files section.

## Workflow

Three atomic commits, in order, each pushed to BOTH remotes (`origin` + `multi-user`) before starting the next:

1. **C14** — per `day_2/PLAN.md §2.C14`. Run its validation gate. Commit with the template in that section. Push to both remotes. Verify SHA parity.
2. **C15** — per `day_2/PLAN.md §2.C15`. Same loop.
3. **C16** — per `day_2/PLAN.md §2.C16`. Same loop. Highest risk — re-read §2.C16 and §5 (risk register) before touching code.
4. **Doc patches** — apply `day_2/PLAN.md §3` (runbook update). Single follow-up commit or fold into C16's commit; either is fine.

## Hard rules

1. Do NOT deploy with an open NKD position. Check `redis-cli HGETALL captain:open_positions` for any `is_nkd_trail=true` entry before pushing C14. If one exists, STOP and ask the user.
2. Do NOT use `--force` on either remote.
3. Do NOT bundle commits — three commits, three messages, three pushes.
4. Do NOT edit the day-2 PLAN.md or COMPLETION_CHECKLIST.md. If you find a genuine plan error during implementation, STOP and ask the user.
5. Do NOT run [`scripts/nkd_pivot_d26_override.py`](scripts/nkd_pivot_d26_override.py) — that is a separate operator-gated action, out of scope here.
6. Do NOT deploy to any tower yourself. That step is operator-only per workspace rule §3.
7. Confirm SHA parity (`git rev-parse HEAD` == `origin/main` == `multi-user/main`) after each push before moving on.

## When you finish

Run the full NKD validation suite:

```bash
PYTHONPATH=./:./captain-online:./captain-offline:./captain-command \
  python3 -m pytest tests/test_b7b_nkd_trail.py tests/test_b7b_isaac_jitter_stress.py \
    tests/test_b6_signal.py tests/test_bootstrap_nkd_trail_fields.py \
    tests/test_nkd_jitter_lifecycle.py tests/test_tick_snap_outward.py \
    tests/test_b12_compliance_modify_check.py tests/test_userstream_bracket_capture.py \
    tests/test_marketstream_nkd_persistence.py tests/test_b7_time_exit_nkd_exemption.py \
    tests/test_nkd_replay_22h.py -v
```

Report back with: (a) the three SHAs + remote-parity confirmation, (b) the pytest pass/fail line per file, (c) any deviation from the plan and why, (d) the next operator action (it is the tower-side pull / config-sync / `dco build` / `cmd-run bootstrap_production.py` sequence from `day_2/PLAN.md §4`).

--- END PROMPT ---
