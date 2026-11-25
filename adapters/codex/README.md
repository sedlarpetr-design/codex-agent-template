# Codex runtime adapter

Use the repository-level [AGENTS.md](../../AGENTS.md) as the authoritative
Codex adapter. Native profiles and hooks are configured in [`.codex/`](../../.codex/).
The shared contracts and workflow semantics remain in
[templates/CORE_RULES.md](../../templates/CORE_RULES.md); do not duplicate or
override them here.

Codex-specific settings, profiles, and tool permissions belong to the host
configuration. The repository defaults to read-only access and keeps
coordination, verification, and synthesis in the shared Python `core/`.
