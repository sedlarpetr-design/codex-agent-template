import argparse
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from testing import runner


class RunnerTests(TestCase):
    def test_isolated_workspace_uses_only_provided_files(self):
        with TemporaryDirectory() as temporary:
            workspace = Path(temporary) / "fixture"
            runner.make_workspace(workspace, {".codex/config.toml": b"example", "AGENTS.md": b"instructions"})
            self.assertTrue((workspace / ".git").is_dir())
            self.assertEqual((workspace / "AGENTS.md").read_bytes(), b"instructions")
            self.assertEqual((workspace / ".codex/config.toml").read_bytes(), b"example")
            self.assertEqual({item.name for item in workspace.iterdir()}, {".git", ".codex", "AGENTS.md"})

    def test_trial_removes_temporary_workspace(self):
        workspaces = []

        def native(workspace, case, model, timeout):
            workspaces.append(workspace)
            self.assertEqual((workspace / "AGENTS.md").read_bytes(), b"instructions")
            self.assertEqual(case["id"], "small")
            return {"session_id": "native", "audit": [{"stav": "hotovo"}]}

        with patch.object(runner, "run_case", side_effect=native), patch.object(
            runner, "grade", return_value={"status": "PASS", "checks": []}
        ):
            result = runner.trial({"id": "small"}, 1, {"AGENTS.md": b"instructions"}, "model", 30)
        self.assertEqual(result["session_id"], "native")
        self.assertEqual(result["audit"], [{"stav": "hotovo"}])
        self.assertFalse(workspaces[0].exists())

    def test_partial_report_cannot_create_candidate(self):
        args = argparse.Namespace(case=["a"], candidate=True)
        with patch.object(runner, "load_cases", return_value={"a": {}, "b": {}}):
            with self.assertRaisesRegex(ValueError, "úplnou sadu"):
                runner.run_suite(args)

    def test_candidate_keeps_failed_attempt_and_stays_separate(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "VERSION").write_text("1.0.0-dev.1\n", encoding="utf-8")
            (root / "testing").mkdir()
            (root / "testing/native.py").write_text("test fixture", encoding="utf-8")
            args = argparse.Namespace(case=[], candidate=True, model="model", timeout=30, jobs=1)
            scenario = {"a": {"category": "security", "repeats": 1, "critical": True, "prompt": "fixture", "expected": {}}}
            source = {name: name.encode() for name in runner.AGENT_FILES}
            with (
                patch.object(runner, "ROOT", root),
                patch.object(runner, "load_cases", return_value=scenario),
                patch.object(runner, "reviewed_snapshot", return_value=("fixture-commit", source)),
                patch.object(runner, "trial", return_value={"attempt": 1, "status": "FAIL", "checks": []}),
                patch.object(runner.subprocess, "run", return_value=CompletedProcess([], 0, "fixture CLI", "")),
                redirect_stdout(StringIO()),
            ):
                self.assertEqual(runner.run_suite(args), 1)
            (report,) = (root / "testing/reports").glob("*/report.json")
            candidate = json.loads(report.with_name("baseline.candidate.json").read_text())
            self.assertEqual(candidate["status"], "candidate")
            self.assertEqual(candidate["report"]["summary"]["FAIL"], 1)
            self.assertFalse((root / "testing/baseline.json").exists())
