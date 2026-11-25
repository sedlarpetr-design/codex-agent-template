# Claude runtime adapter

This repository uses the platform-neutral contracts and behavior in
[templates/CORE_RULES.md](templates/CORE_RULES.md). This file only maps those
rules to Claude / Claude Code.

- Use the available file, command, and subagent tools only within the runtime's
  granted permissions.
- Keep each delegated task within its assigned scope and return the shared
  `ResultEnvelope` fields, evidence refs, task/step IDs, and attempt number.
- Use the deterministic `core/` package for queue state, verification,
  accounting, and synthesis checks. Never infer a successful verdict from a
  tool call or a model's confidence.
- Return one of `SPLNĚNO`, `NESPLNĚNO`, or `NEOVĚŘENO` with criterion-level
  evidence. Mark an interrupted or invalidly closed audit `audit_neuplny`.
- Obtain explicit runtime permission for writes or external side effects; a
  quality verdict does not grant authorization.
