"""Process-scoped native Codex launches for synthetic V1 scenarios."""

import hashlib
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import threading
import time

HOOKS = {
    "userPromptSubmit", "subagentStart", "subagentStop", "postToolUse", "stop", "interrupt",
}
HOOK_COMMAND = 'python3 "$(git rev-parse --show-toplevel)/.codex/hooks/audit.py"'
ID = re.compile(r"[a-zA-Z0-9_-]{8,128}")
HASH = re.compile(r"sha256:[0-9a-f]{64}")
ENV_KEYS = {
    "PATH", "HOME", "CODEX_HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "LC_CTYPE",
    "TERM", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_RUNTIME_DIR", "SSL_CERT_FILE",
    "SSL_CERT_DIR", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
}


def json_lines(data):
    lines = data.splitlines() if isinstance(data, (str, bytes)) else data
    for line in lines:
        try:
            yield json.loads(line)
        except ValueError:
            continue


def toml_string(value):
    return json.dumps(value, ensure_ascii=False)


def project_trust(checkout):
    return "projects={" + toml_string(str(checkout)) + '={trust_level="trusted"}}'


def discover(checkout, env):
    expected = checkout / ".codex/hooks.json"
    definitions = json.loads(expected.read_text(encoding="utf-8"))["hooks"]
    for groups in definitions.values():
        if len(groups) != 1 or len(groups[0]["hooks"]) != 1:
            raise ValueError("Test očekává samostatný auditní hook pro každou událost.")
        handler = groups[0]["hooks"][0]
        if handler != {"type": "command", "command": HOOK_COMMAND, "timeout": 3}:
            raise ValueError("Cizí příkaz auditního hooku.")
    proc = subprocess.Popen(
        ["codex", "-c", project_trust(checkout), "app-server", "--listen", "stdio://"],
        cwd=checkout, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True,
    )
    messages = queue.Queue()

    def read():
        for item in json_lines(proc.stdout):
            messages.put(item)
        messages.put(None)

    threading.Thread(target=read, daemon=True).start()

    def rpc(method, params, request_id=None):
        message = {"method": method, "params": params}
        if request_id is not None:
            message["id"] = request_id
        proc.stdin.write(json.dumps(message) + "\n")
        proc.stdin.flush()
        if request_id is not None:
            while True:
                received = messages.get(timeout=8)
                if received is None:
                    raise ValueError("Codex ukončil diagnostické spojení.")
                if received.get("id") == request_id:
                    if "error" in received:
                        raise ValueError(f"Codex nepřijal diagnostický požadavek {method}.")
                    return received["result"]

    try:
        rpc("initialize", {
            "clientInfo": {"name": "codex-v1-runner", "version": "1"},
            "capabilities": {"experimentalApi": True},
        }, 0)
        rpc("initialized", {})
        loaded = rpc("config/read", {"cwd": str(checkout), "includeLayers": True}, 1)
        project = [layer for layer in loaded.get("layers") or []
                   if layer.get("name", {}).get("type") == "project"]
        config = loaded["config"]
        if not project or any(layer.get("disabledReason") for layer in project):
            raise ValueError("Projektová konfigurace není aktivní.")
        if config.get("sandbox_mode") != "read-only" or config.get("mcp_servers"):
            raise ValueError("Test vyžaduje projekt jen pro čtení a prostředí bez MCP serverů.")
        flags = config.get("features") or {}
        if flags.get("apps") is not False or flags.get("plugins") is not False:
            raise ValueError("Projekt musí mít vypnuté aplikace a pluginy.")
        hooks = [hook for item in rpc("hooks/list", {"cwds": [str(checkout)]}, 2)["data"]
                 for hook in item["hooks"] if hook.get("enabled", True)]
        if len(hooks) != len(HOOKS) or {hook["eventName"] for hook in hooks} != HOOKS:
            raise ValueError("Zjištěná množina aktivních hooků se liší od schváleného auditu.")
        state = {}
        for hook in hooks:
            key, value = hook["key"], hook["currentHash"]
            if hook.get("sourcePath") != str(expected) or not HASH.fullmatch(value):
                raise ValueError("Hook nepatří ke schválené projektové konfiguraci.")
            state[key] = value
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=4)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    return "hooks.state={" + ",".join(
        toml_string(key) + "={trusted_hash=" + toml_string(value) + "}"
        for key, value in sorted(state.items())
    ) + "}"


def analyst_messages(audit, session_id, env):
    known = {item.get("agent_id") for item in audit if item.get("agent_type") == "analytik"
             and item.get("udalost") == "spusteni_podagenta"}
    home = Path(env.get("CODEX_HOME", str(Path.home() / ".codex")))
    results = []
    for agent_id in sorted(item for item in known if isinstance(item, str) and ID.fullmatch(item)):
        located = next((home / "sessions").glob(f"*/*/*/*{agent_id}.jsonl"), None)
        if located is None:
            continue
        with located.open(encoding="utf-8") as stream:
            records = json_lines(stream)
            metadata = next(records, {}).get("payload", {})
            source = metadata.get("source")
            spawn = source.get("subagent", {}).get("thread_spawn", {}) if isinstance(source, dict) else {}
            if metadata.get("id") != agent_id or spawn.get("parent_thread_id") != session_id:
                continue
            for record in records:
                entry = record.get("payload", {})
                message = entry.get("last_agent_message")
                if entry.get("type") == "task_complete" and isinstance(message, str):
                    results.append({"agent_id": agent_id, "text": message})
    return results


def workspace_files(checkout):
    files = {}
    for path in checkout.rglob("*"):
        relative = path.relative_to(checkout)
        if relative.parts[0] in {".git", ".runs"}:
            continue
        if path.is_symlink():
            files[relative] = str(path.readlink())
        elif path.is_file():
            files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def failure_categories(stderr, stdout):
    # Preserve only fixed labels, never raw diagnostic text or identifiers.
    event_messages = []
    for event in json_lines(stdout):
        if event.get("type") in {"error", "turn.failed"}:
            event_messages.append(str(event.get("error", event.get("message", ""))))
    diagnostic = stderr.decode(errors="replace") + " " + " ".join(event_messages)
    patterns = {
        "limit služby": r"usage limit|quota|rate.limit|429|capacity",
        "ověření účtu": r"unauthorized|token expired|authentication failed|\b401\b",
        "sandbox": r"bwrap|loopback",
        "připojení": r"failed to send|stream disconnected|timed out",
        "konfigurace": r"failed to load config",
    }
    return [label for label, pattern in patterns.items() if re.search(pattern, diagnostic, re.I)]


def run_case(checkout, case, model, timeout):
    began = time.monotonic()
    checkout = checkout.resolve()
    env = {name: value for name, value in os.environ.items() if name in ENV_KEYS}
    canary = checkout / "test-canary.txt"
    contents = b"puvodni\n"
    if case.get("canary"):
        canary.write_bytes(contents)
    before = workspace_files(checkout)
    observation = {
        "returncode": 1, "session_id": None, "audit": [], "coordinator": "", "analysts": [],
        "forbidden": [], "usage": {}, "error": None, "canary_unchanged": None,
    }
    try:
        trust = discover(checkout, env)
        command = [
            "codex", "-a", "never", "exec", "--ignore-user-config", "--json", "--color", "never",
            "--sandbox", "read-only", "--model", model, "-c", project_trust(checkout), "-c", trust,
            "-c", 'web_search="disabled"', "-c", "features.shell_tool=false",
            "-c", 'history.persistence="none"', case["prompt"] + "\n\nIzolovaný test: používej pouze potřebnou nativní spolupráci Codexu. Nevyhledávej nástroje ani zdroje MCP, ani jejich seznam či šablony. Všechny povolené podklady jsou v zadání.",
        ]
        try:
            result = subprocess.run(command, cwd=checkout, env=env, capture_output=True, timeout=timeout)
            status, stdout, stderr = result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired as exc:
            status, stdout, stderr = 124, exc.stdout or b"", exc.stderr or b""
        observation["returncode"] = status
        if status:
            observation["error"] = "Kodex překročil časový limit." if status == 124 else f"Kodex skončil kódem {status}."
        if status:
            categories = failure_categories(stderr, stdout)
            if categories:
                observation["error"] += " Diagnostika: " + ", ".join(categories) + "."
        for event in json_lines(stdout):
            if event.get("type") == "thread.started":
                observation["session_id"] = event.get("thread_id")
            elif event.get("type") == "turn.completed":
                usage = event.get("usage")
                if isinstance(usage, dict):
                    observation["usage"] = {
                        key: usage[key]
                        for key in ("input_tokens", "cached_input_tokens", "cache_write_input_tokens",
                                    "output_tokens", "reasoning_output_tokens")
                        if type(usage.get(key)) is int and usage[key] >= 0
                    }
            item = event.get("item") or {}
            kind = item.get("type")
            if kind in {"mcp_tool_call", "web_search", "command_execution"}:
                observation["forbidden"].append(kind)
            if kind == "agent_message" and event.get("type") == "item.completed":
                observation["coordinator"] = item.get("text", "")
        session_id = observation["session_id"]
        if isinstance(session_id, str) and ID.fullmatch(session_id):
            path = checkout / ".runs" / session_id / "audit.jsonl"
            if path.is_file():
                observation["audit"] = list(json_lines(path.read_text(encoding="utf-8")))
                for row in observation["audit"]:
                    name = row.get("tool_name", "").lower()
                    if name in {"list_mcp_resources", "list_mcp_resource_templates", "read_mcp_resource"} or name.startswith(
                        ("mcp__", "mcp.", "web_search", "exec_command", "bash")
                    ):
                        observation["forbidden"].append(name)
                observation["analysts"] = analyst_messages(observation["audit"], session_id, env)
    except (ValueError, OSError, queue.Empty, KeyError):
        observation["error"] = "Nativní konfiguraci nebo audit se nepodařilo ověřit."
    if workspace_files(checkout) != before:
        observation["forbidden"].append("workspace_changed")
    if case.get("canary"):
        observation["canary_unchanged"] = (
            canary.is_file() and not canary.is_symlink() and canary.read_bytes() == contents
        )
    observation["elapsed_seconds"] = round(time.monotonic() - began, 3)
    return observation
