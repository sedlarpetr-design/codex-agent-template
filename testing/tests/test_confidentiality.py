import argparse
from contextlib import redirect_stdout
import importlib.util
from io import StringIO
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from testing import native, runner


class ConfidentialityTests(TestCase):
    def test_sensitive_fixture_never_reaches_audit_report_or_candidate(self):
        secret = "synthetic-test-secret-7842"
        hook_path = runner.ROOT / ".codex/hooks/audit.py"
        spec = importlib.util.spec_from_file_location("audit_fixture", hook_path)
        hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook)
        prompt = f"Zadání {secret}\n<podklad>{secret}</podklad>"
        scenario = {"a": {"category": "security", "repeats": 3, "prompt": prompt,
                          "expected": {"analysts": 0, "status": "hotovo", "repairs": 0, "verdicts": []}}}
        source = {name: name.encode() for name in runner.AGENT_FILES}
        args = argparse.Namespace(case=[], candidate=True, model="model", timeout=30, jobs=1)
        real_run = subprocess.run
        attempts = 0

        def execute(command, **kwargs):
            nonlocal attempts
            if command[0] == "git":
                return real_run(command, **kwargs)
            if command == ["codex", "--version"]:
                return subprocess.CompletedProcess(command, 0, "fixture CLI", "")
            attempts += 1
            checkout = kwargs["cwd"]
            self.assertIn(prompt, command[-1])
            common = {"session_id": "session-1", "turn_id": "turn-1"}
            hook.record(dict(common, hook_event_name="UserPromptSubmit", prompt=prompt), checkout)
            hook.record(dict(common, hook_event_name="PostToolUse", tool_name="fixture",
                             tool_response={"content": secret}), checkout)
            hook.record(dict(common, hook_event_name="Stop", last_assistant_message=(
                secret + "\nAUDIT stav=hotovo overeni=neprovedeno opravy=0 akce=zadna")), checkout)
            self.assertNotIn(secret, (checkout / ".runs/session-1/audit.jsonl").read_text())
            if attempts == 3:
                raise ValueError(secret)
            events = [
                {"type": "thread.started", "thread_id": "session-1"},
                {"type": "turn.completed", "usage": {"input_tokens": 12, secret: secret}},
                {"type": "error", "message": f"token expired {secret}"},
                {"type": "item.completed", "item": {"type": "agent_message", "text": secret}},
            ]
            return subprocess.CompletedProcess(command, int(attempts == 2),
                                               "\n".join(map(json.dumps, events)).encode(),
                                               f"bwrap {secret}".encode())

        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "VERSION").write_text("1.0.0\n")
            (root / "testing").mkdir()
            (root / "testing/native.py").write_text("fixture")
            with (
                patch.object(runner, "ROOT", root),
                patch.object(runner, "load_cases", return_value=scenario),
                patch.object(runner, "reviewed_snapshot", return_value=("commit", source)),
                patch.object(native, "discover", return_value="fixture"),
                patch.object(native, "analyst_messages", return_value=[]),
                patch.object(subprocess, "run", side_effect=execute),
                redirect_stdout(StringIO()),
            ):
                self.assertEqual(runner.run_suite(args), 2)
            (report_path,) = root.glob("testing/reports/*/report.json")
            for path in (report_path, report_path.with_name("baseline.candidate.json")):
                self.assertNotIn(secret, path.read_text())
            report = json.loads(report_path.read_text())
            self.assertEqual(report["summary"], {"PASS": 1, "FAIL": 0, "REVIEW": 2})
            self.assertEqual(report["measurements"]["usage"], {"input_tokens": {"attempts": 2, "tokens": 24}})
            self.assertIn("sandbox", report["scenarios"][0]["attempts"][1]["error"])
