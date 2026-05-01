---
name: record
description: >-
  Record the current Captain System debugging context as a new prepended entry
  in `docs2/context/tracking_context.md` (or another file under `docs2/context/`
  if specified). Captures the active issue, what we know, where we are up to,
  and concrete next steps so a fresh agent can resume from where the previous
  one left off. Trigger when the user types `/record` (optionally followed by a
  filename and/or short title).
disable-model-invocation: true
---

# /record — Cross-Agent Context Trail

This skill writes a fresh dated entry into a context-trail markdown file under
`docs2/context/` so the next agent can pick up exactly where the last one stopped.

## When the user invokes `/record`

The user types one of:

- `/record` — append to the **most recently modified** file in `docs2/context/`
  (default: `docs2/context/tracking_context.md`).
- `/record <filename>` — append to that specific file under `docs2/context/`.
  If it does not exist, create it from the template below.
- `/record <filename> "<short title>"` — same as above, but use the supplied
  title as the H3 of the entry instead of an auto-generated one.

## What the skill must produce

A new H3 entry **prepended to the top of `## Records`** (newest-first), with
exactly these five sections — each on its own line, in this order:

```markdown
### YYYY-MM-DD HH:MM <TZ> — <one-line title>

**Status:** <Investigating | Patching | Verifying | Resolved | Blocked>

**What we know — confirmed:**
- <bullet>
- <bullet>

**What we DON'T yet know:**
- <bullet>

**Where we're at:**
- <bullet>

**Next steps:**
1. <numbered step>
2. <numbered step>

**Useful refs:**
- `<path/to/file>:<line>` — <why it matters>
```

## Authoring rules

1. **Prepend, never overwrite.** Find the line `## Records` and insert the new
   entry immediately after the heading. Older entries stay below intact.
2. **Update the `## Active Issue` block at the top** of the file to reflect the
   new headline status (one paragraph, no more). The detailed history lives
   in the records below.
3. **Be concrete.** Reference exact commit SHAs, file paths with line numbers,
   log strings, and SQL table/column names. Avoid vague phrases like "looks like"
   or "should be" — if uncertain, put it under "What we DON'T yet know".
4. **No emoji.** Plain markdown. Files in `docs2/context/` are for cross-agent
   handoff, not user-facing.
5. **Timestamp in the local timezone** the user is operating in (read from the
   shell `date` command if unsure; the tracker has been in BST/UTC+1 historically).
6. **Mention all running todos.** Keep the agent's TodoWrite list in sync with
   the next-steps section so the next agent inherits the task graph.
7. **Keep entries short.** Aim for 15-30 lines per entry. If something is
   longer, link out to a runbook in `docs2/quick-fixes/` or
   `docs2/audits/` instead.
8. **Push.** Per `.cursor/rules/captain-deploy-and-tower-discipline.mdc`, after
   writing the record, run `git add` + `git commit` + push to **both** remotes
   (`origin` and `multi-user`). The skill is a no-op without persistence.

## File template (when creating a new context file)

If `<filename>` does not exist, scaffold it from this skeleton, then prepend
the first entry into `## Records`:

```markdown
# Captain System — <Topic Title>

> **Purpose.** Rolling trail of records for cross-agent context handoff.
> New `/record` entries are prepended at the top of `## Records`. The newest
> entry is always the next agent's starting point.
>
> **How to use.** When you start a new agent chat, paste:
> *"Read `docs2/context/<filename>` and pick up from the most recent record."*

---

## Active Issue

<one paragraph headline status — overwritten on every /record>

---

## Records

<entries newest-first below>
```

## Workflow

1. Resolve target file:
   - If the user supplied a filename, use `docs2/context/<filename>`.
   - Otherwise, use `docs2/context/tracking_context.md` if it exists, else the
     newest `*.md` under `docs2/context/`.
2. Read the file (or scaffold if missing).
3. Compose the entry from the current chat state — be specific about the active
   issue, exact commits/files, and the open questions.
4. Use `StrReplace` to insert the new entry directly under `## Records`. If the
   `## Active Issue` block needs updating, do that in the same call set.
5. Stage, commit (`docs(context): record <one-line summary>`), and push to BOTH
   remotes:
   ```bash
   git add docs2/context/
   git commit -m "docs(context): record <summary>"
   git push origin HEAD
   git push multi-user HEAD
   ```
6. Reply with one line: `Recorded → docs2/context/<filename>` and a 3-line
   condensed summary of what was captured, so the user can verify before
   handing off.

## Anti-patterns

- Replacing the file wholesale.
- Appending below the most recent entry instead of prepending.
- Writing the record but skipping the dual-remote push.
- Including the agent's own internal reasoning instead of the user-facing facts.
- Forgetting to update `## Active Issue`.
- Adding a record without referencing exact commit SHAs / file paths / log strings.
