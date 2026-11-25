from pathlib import Path
from tempfile import TemporaryDirectory
import time
from unittest import TestCase

from core.coordinator import Coordinator, audit_neuplny
from core.envelopes import Evidence, ResultEnvelope


def enqueue(coordinator, identity, task="task", role="analyst", *, depends_on=(),
            phase="specialist", resource="cpu", max_attempts=1, parent_id=None,
            children_closed=True):
    coordinator.enqueue(
        id=identity, task=task, role=role, resource=resource, phase=phase,
        payload={}, depends_on=depends_on, max_attempts=max_attempts,
        parent_id=parent_id, children_closed=children_closed,
    )


class CoordinatorTests(TestCase):
    def test_sqlite_wal_queue_survives_reopen(self):
        with TemporaryDirectory() as directory:
            path = str(Path(directory) / "queue.sqlite")
            queue = Coordinator(path)
            enqueue(queue, "persistent")
            self.assertEqual(queue.db.execute("PRAGMA journal_mode").fetchone()[0], "wal")
            queue.close()
            with Coordinator(path) as restored:
                self.assertEqual(restored.get_job("persistent")["state"], "pending")

    def test_task_role_lock_excludes_duplicate_role_but_not_other_task(self):
        with Coordinator() as queue:
            queue.configure(2, roles={"analyst": 2}, resources={"cpu": 2})
            enqueue(queue, "first", task="same-task")
            enqueue(queue, "same-role", task="same-task")
            enqueue(queue, "other-task", task="other-task")
            first = queue.claim("worker-1")
            second = queue.claim("worker-2")
            self.assertEqual((first["id"], second["id"]), ("first", "other-task"))
            self.assertEqual(queue.get_job("same-role")["state"], "pending")

    def test_recover_requires_stopped_worker_and_rejects_stale_token(self):
        with Coordinator() as queue:
            enqueue(queue, "recover-me", max_attempts=2)
            claimed = queue.claim("worker", lease=0.01)
            time.sleep(0.02)
            self.assertFalse(queue.recover("recover-me", claimed["token"],
                                           stopped=False, safe_to_retry=True))
            self.assertTrue(queue.recover("recover-me", claimed["token"],
                                          stopped=True, safe_to_retry=True))
            self.assertEqual(queue.get_job("recover-me")["state"], "pending")
            self.assertFalse(queue.finish("recover-me", claimed["token"], {"late": True}))
            queue.db.execute("UPDATE job SET ready_at=0 WHERE id='recover-me'")
            retried = queue.claim("worker")
            self.assertEqual(retried["attempt"], 2)

    def test_failed_needs_pass_dependency_cascades_to_pending_descendants(self):
        with Coordinator() as queue:
            enqueue(queue, "source")
            enqueue(queue, "middle", depends_on=[("source", True)])
            enqueue(queue, "leaf", depends_on=[("middle", True)])
            claimed = queue.claim("worker")
            self.assertTrue(queue.finish(
                "source", claimed["token"], {"failed": True}, verdict="NESPLNĚNO"
            ))
            self.assertEqual(queue.get_job("source")["state"], "blocked")
            self.assertEqual(queue.get_job("middle")["state"], "blocked")
            self.assertEqual(queue.get_job("leaf")["state"], "blocked")
            self.assertIn("blocked_by_predecessor",
                          [item["event"] for item in queue.history("leaf")])

    def test_substantive_repairs_are_capped_at_two(self):
        with Coordinator() as queue:
            enqueue(queue, "repair-limit", max_attempts=10)
            for attempt in range(1, 4):
                claimed = queue.claim(f"worker-{attempt}")
                self.assertEqual(claimed["attempt"], attempt)
                queue.finish("repair-limit", claimed["token"], {"bad": True},
                             verdict="NESPLNĚNO")
                if attempt < 3:
                    self.assertEqual(queue.get_job("repair-limit")["state"], "pending")
                    queue.db.execute("UPDATE job SET ready_at=0 WHERE id='repair-limit'")
            job = queue.get_job("repair-limit")
            self.assertEqual((job["state"], job["verdict"]), ("blocked", "NESPLNĚNO"))
            retries = [item for item in queue.history("repair-limit")
                       if item["event"] == "retry_scheduled"]
            self.assertEqual(len(retries), 2)

    def test_url_batches_require_explicit_close_and_wait_for_children(self):
        with Coordinator() as queue:
            queue.configure(2, resources={"browser": 1, "cpu": 1})
            enqueue(queue, "batch-parent", role="summary", resource="cpu",
                    children_closed=False)
            self.assertEqual(
                queue.enqueue_url_check_batch("batch-parent", ["u1", "u2", "u3"], 2),
                ["batch-parent-batch-0", "batch-parent-batch-1"],
            )
            self.assertTrue(queue.close_children("batch-parent"))
            self.assertIsNone(queue.collect_children_results("batch-parent"))
            first = queue.claim("worker-1")
            self.assertEqual(first["id"], "batch-parent-batch-0")
            self.assertTrue(queue.finish(first["id"], first["token"], {"ok": True},
                                         verdict="SPLNĚNO"))
            second = queue.claim("worker-2")
            self.assertEqual(second["id"], "batch-parent-batch-1")
            self.assertTrue(queue.finish(second["id"], second["token"], {"ok": True},
                                         verdict="SPLNĚNO"))
            self.assertEqual(len(queue.collect_children_results("batch-parent")), 2)

    def test_specialist_result_registers_canonical_evidence_and_routes_to_cpu(self):
        with Coordinator() as queue:
            enqueue(queue, "step-1")
            job = queue.claim("specialist")
            result = ResultEnvelope(
                task_id="task", attempt=1, step_id="step-1", kind="files",
                status="ok", result={"files": []},
                evidence=[Evidence("step-1#0", "calc", "c1", None, "count=1", 1)],
            )
            self.assertTrue(queue.submit_specialist_result("step-1", job["token"], result))
            pending = queue.get_job("step-1")
            self.assertEqual((pending["phase"], pending["resource"], pending["attempt"]),
                             ("verify_cpu", "verify_cpu", 1))
            self.assertEqual(queue.evidence("task")[0]["ref"], "step-1#0")
            verifier = queue.claim("verifier")
            self.assertEqual(verifier["attempt"], 1)

    def test_verify_cpu_readiness_transitions_only_ready_to_content(self):
        with Coordinator() as queue:
            enqueue(queue, "verify", role="overovatel", phase="verify_cpu", resource="verify_cpu")
            claimed = queue.claim("cpu")
            self.assertTrue(queue.advance_after_verify_cpu(
                "verify", claimed["token"], "ready", {"checks": "pass"}
            ))
            self.assertEqual(queue.get_job("verify")["phase"], "verify_content")
            content = queue.claim("content")
            self.assertEqual((content["resource"], content["attempt"]), ("llm", 1))

    def test_not_needed_cpu_phase_does_not_assume_success(self):
        with Coordinator() as queue:
            enqueue(queue, "cpu-only", role="overovatel", phase="verify_cpu",
                    resource="verify_cpu")
            claimed = queue.claim("cpu")
            self.assertTrue(queue.advance_after_verify_cpu(
                "cpu-only", claimed["token"], "not_needed", {"verdict": "NEOVĚŘENO"}
            ))
            job = queue.get_job("cpu-only")
            self.assertEqual((job["state"], job["verdict"]), ("blocked", "NEOVĚŘENO"))

    def test_waiting_for_evidence_uses_its_separate_retry_budget(self):
        with Coordinator() as queue:
            enqueue(queue, "evidence-retry", role="overovatel", phase="verify_cpu",
                    resource="verify_cpu", max_attempts=5)
            for attempt in (1, 2):
                claimed = queue.claim(f"cpu-{attempt}")
                queue.advance_after_verify_cpu(
                    "evidence-retry", claimed["token"], "waiting_for_evidence", {}
                )
                if attempt == 1:
                    queue.db.execute("UPDATE job SET ready_at=0 WHERE id='evidence-retry'")
            job = queue.get_job("evidence-retry")
            self.assertEqual((job["state"], job["verdict"]), ("blocked", "NEOVĚŘENO"))
            retries = [item for item in queue.history("evidence-retry")
                       if item["event"] == "retry_scheduled"]
            self.assertEqual(len(retries), 1)

    def test_audit_missing_or_invalid_close_is_marked_incomplete(self):
        self.assertTrue(audit_neuplny([]))
        self.assertTrue(audit_neuplny([{"udalost": "uzavreni_ukolu", "stav": "hotovo"}]))
        self.assertFalse(audit_neuplny([{
            "udalost": "uzavreni_ukolu", "stav": "hotovo", "overeni": "proslo", "opravy": 0,
        }]))
