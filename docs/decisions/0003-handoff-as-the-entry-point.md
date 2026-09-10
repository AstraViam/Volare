# 3. HANDOFF.md is the entry point

Date: 2026-09-10 · Status: accepted

## Context

Work on this project moves between sessions, between people, and between AI
assistants with no shared memory. Each restart otherwise spends its first hour
rediscovering what is broken, what is missing and what was already tried.

## Decision

`HANDOFF.md` is the single entry point. It carries current state, every known
blocker with what it blocks, what changed last session, and what to do next.
`README.md` and `CLAUDE.md` both point at it in their first lines.

`CLAUDE.md` makes updating it a requirement of any session that changes the
repository, and `HANDOFF.md` section 9 says exactly which parts to update.

## Consequences

The handoff is only useful while it is true. An out-of-date handoff is worse
than none, because the next reader trusts it. That is why the update rule names
specific sections rather than saying "keep it current", and why the session log
is append-only: a wrong entry can be corrected by a later one, but deleting
history hides that the correction happened.
