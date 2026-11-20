"""Run versioned V1 scenarios against native Codex profiles."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
from uuid import uuid4

from testing.graders import grade, release_gate
from testing.native import run_case

ROOT = Path(__file__).resolve().parents[1]
AGENT_FILES = (
    "AGENTS.md",
    ".codex/config.toml",
    ".codex/hooks.json",
    ".codex/hooks/audit.py",
    ".codex/agents/analytik.toml",
    ".codex/agents/overovatel.toml",
    "templates/task.md",
    "templates/assignment.md",
    "templates/result.md",
)
CASE_ID = re.compile(r"[a-z][a-z0-9_-]*")
SCHEMA_VERSION = 2


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout


def load_cases():
    cases = {}
    for path in sorted((ROOT / "testing/scenarios").glob("*.json")):
        batch = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(batch, list):
            raise ValueError(f"{path.name} musí obsahovat seznam scénářů.")
        for case in batch:
            identity = case["id"]
            if not CASE_ID.fullmatch(identity) or identity in cases:
                raise ValueError(f"Neplatné nebo duplicitní ID scénáře {identity!r}.")
            if type(case["repeats"]) is not int or not 1 <= case["repeats"] <= 5:
                raise ValueError(f"Neplatný počet pokusů u {identity}.")
            if not isinstance(case["prompt"], str) or not case["prompt"].strip():
                raise ValueError(f"Prázdné zadání scénáře {identity}.")
            if case["category"] not in {"coordinator", "analyst", "verifier", "workflow", "security"}:
                raise ValueError(f"Neznámá kategorie scénáře {identity}.")
            cases[identity] = case
    if not cases:
        raise ValueError("Chybějí scénáře V1.0.")
    return cases


def reviewed_snapshot():
    if git("status", "--porcelain", "--untracked-files=normal").strip():
        raise ValueError("Nejdřív ulož testovanou změnu v Gitu. Report má odpovídat přesně jednomu commitu.")
    commit = git("rev-parse", "HEAD").decode().strip()
    agents = {}
    for name in AGENT_FILES:
        tree_entry = git("ls-tree", commit, "--", name).split()
        if not tree_entry or tree_entry[0] not in {b"100644", b"100755"}:
            raise ValueError(f"Ve výchozím commitu chybí běžný soubor {name}.")
        agents[name] = git("show", f"{commit}:{name}")
    return commit, agents


def make_workspace(path, source):
    subprocess.run(
        ["git", "init", "--quiet", "--initial-branch=main", str(path)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for name, contents in source.items():
        destination = path / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(contents)


def trial(case, run_number, source, model, timeout):
    try:
        with TemporaryDirectory(prefix="codex-v1-") as folder:
            workspace = Path(folder) / "fixture"
            make_workspace(workspace, source)
            observed = run_case(workspace, case, model, timeout)
            result = grade(case, observed)
    except Exception as exc:
        # Keep the run in the report without copying provider/tool output into artifacts.
        return {
            "attempt": run_number, "status": "REVIEW",
            "checks": [{"name": "runner", "status": "REVIEW", "detail": type(exc).__name__}],
        }
    return {
        **result,
        "attempt": run_number,
        "session_id": observed.get("session_id"),
        "elapsed_seconds": observed.get("elapsed_seconds"),
        "usage": observed.get("usage", {}),
        "audit": observed.get("audit", []),
        "native_analyst_ids": [item["agent_id"] for item in observed.get("analysts", [])],
        "error": observed.get("error"),
    }


def measurements(attempts):
    elapsed = [row["elapsed_seconds"] for row in attempts if row.get("elapsed_seconds") is not None]
    usage = {}
    for row in attempts:
        for key, tokens in row.get("usage", {}).items():
            total = usage.setdefault(key, {"attempts": 0, "tokens": 0})
            total["attempts"] += 1
            total["tokens"] += tokens
    return {
        "attempts": len(attempts),
        "latency": {"attempts": len(elapsed), "total_seconds": round(sum(elapsed), 3),
                    "max_seconds": max(elapsed, default=None)},
        "usage": usage,
    }


def write_document(path, value):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def run_suite(args):
    cases = load_cases()
    unknown = set(args.case) - cases.keys()
    if unknown:
        raise ValueError(f"Neznámé scénáře {', '.join(sorted(unknown))}.")
    selected = {key: case for key, case in cases.items() if not args.case or key in args.case}
    complete = selected.keys() == cases.keys()
    if args.candidate and not complete:
        raise ValueError("Kandidát baseline vyžaduje úplnou sadu scénářů.")
    commit, source = reviewed_snapshot()
    cli_version = subprocess.run(
        ["codex", "--version"], cwd=ROOT, capture_output=True, text=True, check=True, timeout=10,
    ).stdout.strip()
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    report_dir = ROOT / "testing/reports" / run_id
    report_dir.mkdir(parents=True)
    project_configuration = {name: digest(contents) for name, contents in source.items()}
    runtime_policy = {
        "entrypoint": "native codex exec",
        "project_config": project_configuration[".codex/config.toml"],
        "hook_config": project_configuration[".codex/hooks.json"],
        "audit_hook": project_configuration[".codex/hooks/audit.py"],
        "native_adapter": digest((ROOT / "testing/native.py").read_bytes()),
        "timeout_seconds": args.timeout,
        "approval_policy": "never",
        "sandbox": "read-only",
        "shell": False,
        "external_connectors": False,
    }
    records = [
        {
            "id": identity, "category": case["category"], "required": case.get("required", True),
            "critical": case.get("critical", False), "repeats": case["repeats"], "attempts": [],
            "scenario_sha256": digest(json_bytes(case)),
        }
        for identity, case in selected.items()
    ]
    by_id = {record["id"]: record for record in records}
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        pending = {
            pool.submit(trial, case, n, source, args.model, args.timeout): (identity, n)
            for identity, case in selected.items()
            for n in range(1, case["repeats"] + 1)
        }
        for future in as_completed(pending):
            identity, number = pending[future]
            result = future.result()
            by_id[identity]["attempts"].append(result)
            print(identity, f"{number}/{selected[identity]['repeats']}", result["status"], flush=True)
    for record in records:
        record["attempts"].sort(key=lambda item: item["attempt"])
    summary = {status: 0 for status in ("PASS", "FAIL", "REVIEW")}
    for record in records:
        for attempt in record["attempts"]:
            summary[attempt["status"]] += 1
    for record in records:
        record["measurements"] = measurements(record["attempts"])
    report = {
        "schema_version": SCHEMA_VERSION,
        "meta": {
            "run_id": run_id, "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "version": version, "commit": commit, "cli_version": cli_version, "model": args.model,
            "suite_sha256": digest(json_bytes(cases)), "runtime_sha256": digest(json_bytes(runtime_policy)),
            "runtime_policy": runtime_policy, "configuration": project_configuration,
            "complete": complete, "scenario_ids": list(cases),
            "required_ids": [name for name, case in cases.items() if case.get("required", True)],
        },
        "scenarios": records,
        "summary": summary,
        "measurements": measurements([attempt for record in records for attempt in record["attempts"]]),
    }
    report_path = report_dir / "report.json"
    write_document(report_path, report)
    if args.candidate:
        candidate = report_dir / "baseline.candidate.json"
        write_document(candidate, {"status": "candidate", "report": report})
        print("Kandidát baseline", candidate)
    print("Report", report_path)
    print("Souhrn", json.dumps(summary))
    return 1 if summary["FAIL"] else 2 if summary["REVIEW"] else 0


def evaluate_gate(args):
    report = json.loads(args.report.read_text(encoding="utf-8"))
    baseline = None
    if args.baseline and args.baseline.exists():
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    result = release_gate(report, baseline)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return {"PASS": 0, "BLOCK": 1, "REVIEW": 2}[result["status"]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    modes.add_parser("list", help="Vypsat verzované scénáře")
    execute = modes.add_parser("run", help="Spustit izolované scénáře v Codexu")
    execute.add_argument("--model", required=True)
    execute.add_argument("--case", action="append", default=[])
    execute.add_argument("--jobs", type=int, choices=range(1, 9), default=2)
    execute.add_argument("--timeout", type=int, default=160)
    execute.add_argument("--candidate", action="store_true")
    gate = modes.add_parser("gate", help="Vyhodnotit report proti schválené baseline")
    gate.add_argument("--report", required=True, type=Path)
    gate.add_argument("--baseline", type=Path)
    args = parser.parse_args()
    try:
        if args.mode == "list":
            for identity, case in load_cases().items():
                print(identity, case["category"], case["repeats"])
            return 0
        if args.mode == "run":
            if args.timeout < 10:
                raise ValueError("Časový limit je alespoň 10 sekund.")
            return run_suite(args)
        return evaluate_gate(args)
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
