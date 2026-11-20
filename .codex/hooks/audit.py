"""Store metadata from trusted Codex hooks without copying task content."""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,128}")
NAME = re.compile(r"[A-Za-z0-9_./:-]{1,160}")
ACTIONS = {
    "cteni", "analyza", "delegovani", "overeni", "oprava",
    "priprava_zmeny", "zmena_souboru", "odeslani", "nasazeni",
}
FOOTER = re.compile(
    r"AUDIT stav=(hotovo|vraceno|blokovano|ceka_na_vstup)"
    r" overeni=(proslo|neproslo|nelze_overit|neprovedeno)"
    r" opravy=([0-2]) akce=([a-z_,]{1,140})"
)
VERDICT = re.compile(r"OVERENI vysledek=(proslo|neproslo|nelze_overit)")
STATES = {
    "UserPromptSubmit": ("zadano", "prijeti_ukolu"),
    "SubagentStart": ("bezi", "spusteni_podagenta"),
    "SubagentStop": ("bezi", "ukonceni_podagenta"),
    "PostToolUse": ("bezi", "pouziti_nastroje"),
    "Interrupt": ("preruseno", "preruseni_ukolu"),
    "Stop": ("audit_neuplny", "uzavreni_ukolu"),
}


def footer_match(pattern, message):
    lines = message.rstrip().splitlines() if isinstance(message, str) else []
    return pattern.fullmatch(lines[-1]) if lines else None


def final_fields(message):
    match = footer_match(FOOTER, message)
    if match is None:
        return {}
    state, verification, repairs, action_list = match.groups()
    actions = action_list.split(",") if action_list != "zadna" else []
    if not set(actions).issubset(ACTIONS):
        return {}
    if state == "hotovo" and (
        verification in {"neproslo", "nelze_overit"}
        or ({"delegovani", "overeni"} & set(actions) and verification != "proslo")
    ):
        return {}
    return {
        "stav": state,
        "overeni": verification,
        "opravy": int(repairs),
        "provedene_akce": list(dict.fromkeys(actions)),
    }


def task_id_for(path, event, turn_id, agent_id):
    if event in {"UserPromptSubmit", "Interrupt", "Stop"} or not path.exists():
        return turn_id
    # A child has its own turn id. Associate repeat events with its recorded launch.
    current_task = turn_id
    agent_task = None
    with path.open(encoding="utf-8") as source:
        for line in source:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if entry.get("udalost") == "prijeti_ukolu":
                current_task = entry["task_id"]
            if agent_id and entry.get("agent_id") == agent_id:
                if entry.get("udalost") == "spusteni_podagenta":
                    agent_task = entry["task_id"]
    return agent_task or current_task


def record(payload, project=PROJECT):
    event = payload.get("hook_event_name")
    if event not in STATES:
        raise ValueError("Unsupported audit event")
    session_id = payload.get("session_id")
    turn_id = payload.get("turn_id")
    if not all(isinstance(value, str) and IDENTIFIER.fullmatch(value)
               for value in (session_id, turn_id)):
        raise ValueError("Missing or invalid Codex session or turn ID")

    path = project / ".runs" / session_id / "audit.jsonl"
    if path.resolve() != path:
        raise ValueError("Audit path must not contain symbolic links")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    state, action = STATES[event]
    entry = {
        "cas_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "session_id": session_id,
        "task_id": task_id_for(path, event, turn_id, payload.get("agent_id")),
        "turn_id": turn_id,
        "udalost": action,
        "stav": state,
        "overeni": "nezaznamenano" if event == "Stop" else None,
    }
    for key in ("agent_id", "agent_type", "tool_name", "tool_use_id"):
        value = payload.get(key)
        if isinstance(value, str) and NAME.fullmatch(value):
            entry[key] = value
    if event == "Stop":
        entry.update(final_fields(payload.get("last_assistant_message")))
    if event == "SubagentStop" and entry.get("agent_type") == "overovatel":
        verdict = footer_match(VERDICT, payload.get("last_assistant_message"))
        entry["overeni"] = verdict.group(1) if verdict else "nezaznamenano"

    data = (json.dumps(entry, ensure_ascii=False) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        if os.write(fd, data) != len(data):
            raise OSError("Incomplete audit write")
    finally:
        os.close(fd)
    if entry["stav"] == "audit_neuplny":
        return {"systemMessage": "Minimální audit má neúplný závěr. Ověř stav úkolu."}
    return {}


def main():
    try:
        print(json.dumps(record(json.load(sys.stdin)), ensure_ascii=False))
    except (OSError, ValueError, AttributeError) as exc:
        print(f"Codex audit: {type(exc).__name__}; záznam se nepodařilo uložit.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
