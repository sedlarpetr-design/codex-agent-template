# Antigravity runtime adapter

Follow the platform-neutral [core rules](../../templates/CORE_RULES.md). Use
Antigravity workspace tools, artifacts, and subagents only within the
permissions of the active workspace.

- Return the shared task, result, verdict, and deliverable fields, including
  stable IDs, attempts, and canonical evidence references.
- Persist queue state and checkpoints outside model context. Use the Python
  `core/` implementation for deterministic state changes and checks.
- Delegate measurable work to code or approved workspace tools. Distinguish
  verified facts from unsupported assumptions, and use NEOVĚŘENO when required
  evidence is unavailable.
- A tool invocation alone does not establish that an external action succeeded.
  Audit incomplete runs as `audit_neuplny`; permission is never implied by a
  verifier's quality decision.
