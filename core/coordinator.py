"""Deterministic SQLite queue and workflow state machine."""

from collections import Counter
from contextlib import contextmanager
import json
import sqlite3
import time
from typing import Any, Iterable
from uuid import uuid4

from .envelopes import ResultEnvelope, VERDICTS


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS config (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    value TEXT NOT NULL
);
INSERT OR IGNORE INTO config VALUES
    (1, '{"parallelism":1,"paused":false,"roles":{},"resources":{},"reserve_verify_cpu":false,"retries":{"substantive":2,"technical":2,"needs_evidence":1}}');
CREATE TABLE IF NOT EXISTS job (
    id TEXT PRIMARY KEY,
    task TEXT NOT NULL,
    role TEXT NOT NULL,
    resource TEXT NOT NULL,
    phase TEXT NOT NULL CHECK (phase IN ('specialist','verify_cpu','verify_content','finalize')),
    parent_id TEXT REFERENCES job(id),
    children_closed INTEGER NOT NULL DEFAULT 1 CHECK (children_closed IN (0,1)),
    priority INTEGER NOT NULL DEFAULT 50,
    payload TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','running','done','blocked')),
    attempt INTEGER NOT NULL DEFAULT 0,
    same_attempt INTEGER NOT NULL DEFAULT 0 CHECK (same_attempt IN (0,1)),
    max_attempts INTEGER NOT NULL CHECK (max_attempts >= 1),
    token TEXT,
    lease_until REAL,
    worker TEXT,
    ready_at REAL NOT NULL DEFAULT 0,
    artifact TEXT,
    verdict TEXT,
    feedback TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS active_task_role
    ON job(task, role) WHERE state = 'running';
CREATE TABLE IF NOT EXISTS dependency (
    job_id TEXT NOT NULL REFERENCES job(id),
    predecessor TEXT NOT NULL REFERENCES job(id),
    needs_pass INTEGER NOT NULL CHECK (needs_pass IN (0,1)),
    PRIMARY KEY (job_id, predecessor),
    CHECK (job_id <> predecessor)
);
CREATE TABLE IF NOT EXISTS history (
    seq INTEGER PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES job(id),
    attempt INTEGER NOT NULL,
    event TEXT NOT NULL,
    at REAL NOT NULL,
    details TEXT
);
CREATE TABLE IF NOT EXISTS evidence (
    task_id TEXT NOT NULL,
    ref TEXT NOT NULL,
    step_id TEXT NOT NULL REFERENCES job(id),
    attempt INTEGER NOT NULL,
    evidence_id TEXT NOT NULL,
    type TEXT NOT NULL,
    uri TEXT,
    excerpt TEXT,
    sha256 TEXT,
    PRIMARY KEY (task_id, ref)
);
CREATE VIEW IF NOT EXISTS v_evidence_overview AS
SELECT e.task_id, e.step_id, e.attempt, e.ref, e.type, e.evidence_id,
       j.verdict AS step_verdict, e.uri, substr(e.excerpt, 1, 80) AS excerpt_preview
FROM evidence e
LEFT JOIN job j ON j.task = e.task_id AND j.id = e.step_id AND j.attempt = e.attempt;
"""

PHASES = {"specialist", "verify_cpu", "verify_content", "finalize"}
READINESS = {"not_needed", "skipped_due_to_failure", "waiting_for_evidence", "ready"}
TERMINAL_AUDIT_STATES = {"hotovo", "vraceno", "blokovano", "ceka_na_vstup"}
AUDIT_VERDICTS = {"proslo", "neproslo", "nelze_overit", "neprovedeno"}
DEFAULT_RETRIES = {"substantive": 2, "technical": 2, "needs_evidence": 1}


def audit_neuplny(records: Iterable[dict[str, Any]]) -> bool:
    """Return whether the audit lacks a valid terminal record for its run."""
    rows = list(records)
    if not rows:
        return True
    final = rows[-1]
    return not (
        final.get("udalost") == "uzavreni_ukolu"
        and final.get("stav") in TERMINAL_AUDIT_STATES
        and final.get("overeni") in AUDIT_VERDICTS
        and type(final.get("opravy")) is int
        and 0 <= final["opravy"] <= 2
    )


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


class Coordinator:
    """SQLite-backed dispatcher. Handler work must happen outside transactions."""

    def __init__(self, path: str = ":memory:") -> None:
        self.db = sqlite3.connect(path, isolation_level=None, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "Coordinator":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    @contextmanager
    def _transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def configure(
        self,
        parallelism: int = 1,
        *,
        paused: bool = False,
        roles: dict[str, int] | None = None,
        resources: dict[str, int] | None = None,
        reserve_verify_cpu: bool = False,
        retries: dict[str, int] | None = None,
    ) -> None:
        roles = roles or {}
        resources = resources or {}
        retry_limits = dict(DEFAULT_RETRIES)
        retry_limits.update(retries or {})
        limits = [parallelism, *roles.values(), *resources.values()]
        if any(type(value) is not int or value < 1 for value in limits):
            raise ValueError("queue limits must be positive integers")
        if type(paused) is not bool or type(reserve_verify_cpu) is not bool:
            raise ValueError("paused and reserve_verify_cpu must be booleans")
        if reserve_verify_cpu and parallelism < 2:
            raise ValueError("verify_cpu reservation requires at least two queue slots")
        if (set(retry_limits) - set(DEFAULT_RETRIES)
                or any(type(value) is not int or value < 0 for value in retry_limits.values())
                or retry_limits["substantive"] > 2):
            raise ValueError("retry budgets must be non-negative; substantive is capped at two")
        value = {
            "parallelism": parallelism,
            "paused": paused,
            "roles": roles,
            "resources": resources,
            "reserve_verify_cpu": reserve_verify_cpu,
            "retries": retry_limits,
        }
        with self._transaction():
            self.db.execute("UPDATE config SET value=? WHERE id=1", (_json(value),))

    def _event(self, row: sqlite3.Row | dict[str, Any], event: str, details: Any = None) -> None:
        self.db.execute(
            "INSERT INTO history(job_id,attempt,event,at,details) VALUES (?,?,?,?,?)",
            (row["id"], row["attempt"], event, time.time(), None if details is None else _json(details)),
        )

    def _retry_class(self, verdict: str, feedback: Any = None, artifact: Any = None) -> str:
        for value in (feedback, artifact):
            if isinstance(value, dict) and value.get("retry_class") in {
                "substantive", "technical", "needs_evidence", "waiting_input", "none",
            }:
                return value["retry_class"]
        return "substantive" if verdict == "NESPLNĚNO" else "technical"

    def _retry_allowed(self, row: sqlite3.Row, retry_class: str) -> bool:
        if retry_class not in DEFAULT_RETRIES or row["attempt"] >= row["max_attempts"]:
            return False
        cfg = json.loads(self.db.execute("SELECT value FROM config WHERE id=1").fetchone()[0])
        limit = cfg.get("retries", DEFAULT_RETRIES).get(retry_class, 0)
        used = 0
        for item in self.db.execute(
            "SELECT details FROM history WHERE job_id=? AND event='retry_scheduled'",
            (row["id"],),
        ):
            try:
                details = json.loads(item["details"] or "{}")
            except ValueError:
                continue
            used += details.get("retry_class") == retry_class
        return used < limit

    def _insert_job(
        self,
        *,
        id: str,
        task: str,
        role: str,
        resource: str,
        phase: str,
        payload: dict[str, Any],
        depends_on: Iterable[tuple[str, bool]] = (),
        parent_id: str | None = None,
        children_closed: bool = True,
        priority: int = 50,
        max_attempts: int = 3,
    ) -> None:
        if phase not in PHASES:
            raise ValueError(f"unsupported phase: {phase!r}")
        if not all(isinstance(value, str) and value for value in (id, task, role, resource)):
            raise ValueError("id, task, role, and resource must be non-empty strings")
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
        if type(max_attempts) is not int or max_attempts < 1:
            raise ValueError("max_attempts must be a positive integer")
        if type(priority) is not int or type(children_closed) is not bool:
            raise ValueError("priority must be an integer and children_closed a boolean")
        if parent_id is not None:
            parent = self.db.execute("SELECT * FROM job WHERE id=?", (parent_id,)).fetchone()
            if parent is None or parent["children_closed"] or parent["state"] != "pending":
                raise ValueError("parent is not accepting child jobs")
        self.db.execute(
            """INSERT INTO job(id,task,role,resource,phase,parent_id,children_closed,
                               priority,payload,max_attempts)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (id, task, role, resource, phase, parent_id, int(children_closed),
             priority, _json(payload), max_attempts),
        )
        for predecessor, needs_pass in depends_on:
            if type(needs_pass) is not bool:
                raise ValueError("dependency needs_pass must be boolean")
            self.db.execute(
                "INSERT INTO dependency(job_id,predecessor,needs_pass) VALUES (?,?,?)",
                (id, predecessor, int(needs_pass)),
            )
        row = self.db.execute("SELECT * FROM job WHERE id=?", (id,)).fetchone()
        self._event(row, "queued")

    def enqueue(
        self,
        *,
        id: str,
        task: str,
        role: str,
        resource: str,
        phase: str,
        payload: dict[str, Any],
        depends_on: Iterable[tuple[str, bool]] = (),
        parent_id: str | None = None,
        children_closed: bool = True,
        priority: int = 50,
        max_attempts: int = 3,
    ) -> None:
        with self._transaction():
            self._insert_job(
                id=id, task=task, role=role, resource=resource, phase=phase, payload=payload,
                depends_on=depends_on, parent_id=parent_id, children_closed=children_closed,
                priority=priority, max_attempts=max_attempts,
            )

    def enqueue_url_check_batch(
        self, parent_task_id: str, urls: list[str], batch_size: int = 5
    ) -> list[str]:
        if type(batch_size) is not int or batch_size < 1:
            raise ValueError("batch_size must be a positive integer")
        if not isinstance(urls, list) or any(not isinstance(url, str) or not url for url in urls):
            raise ValueError("urls must be a list of non-empty strings")
        parent = self.db.execute("SELECT * FROM job WHERE id=?", (parent_task_id,)).fetchone()
        if parent is None:
            raise ValueError("parent task does not exist")
        if parent["state"] != "pending" or parent["children_closed"]:
            raise ValueError("parent task must be pending and open to children")
        ids = []
        with self._transaction():
            for offset in range(0, len(urls), batch_size):
                index = offset // batch_size
                child_id = f"{parent_task_id}-batch-{index}"
                self._insert_job(
                    id=child_id, task=parent["task"], role="tester_webu", resource="browser",
                    phase="specialist", payload={"urls": urls[offset:offset + batch_size]},
                    parent_id=parent_task_id,
                )
                ids.append(child_id)
        return ids

    def close_children(self, job_id: str) -> bool:
        with self._transaction():
            row = self.db.execute("SELECT * FROM job WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            if row["state"] != "pending":
                return False
            changed = self.db.execute(
                "UPDATE job SET children_closed=1 WHERE id=? AND children_closed=0",
                (job_id,),
            ).rowcount
            if changed:
                self._event(row, "children_closed")
            return changed == 1

    def claim(self, worker: str, lease: float = 300) -> dict[str, Any] | None:
        if not isinstance(worker, str) or not worker:
            raise ValueError("worker must be a non-empty string")
        if isinstance(lease, bool) or not isinstance(lease, (int, float)) or lease <= 0:
            raise ValueError("lease must be positive")
        with self._transaction():
            cfg = json.loads(self.db.execute("SELECT value FROM config WHERE id=1").fetchone()[0])
            active = self.db.execute("SELECT * FROM job WHERE state='running'").fetchall()
            if cfg.get("paused") or len(active) >= cfg["parallelism"]:
                return None
            roles = Counter(row["role"] for row in active)
            used = Counter(row["resource"] for row in active)
            owners = {(row["task"], row["role"]) for row in active}
            now = time.time()
            candidates = self.db.execute(
                """SELECT j.* FROM job j
                   WHERE j.state='pending' AND j.children_closed=1 AND j.ready_at<=?
                     AND NOT EXISTS (
                       SELECT 1 FROM job c WHERE c.parent_id=j.id
                         AND c.state NOT IN ('done','blocked'))
                     AND NOT EXISTS (
                       SELECT 1 FROM dependency d JOIN job p ON p.id=d.predecessor
                       WHERE d.job_id=j.id
                         AND (p.state NOT IN ('done','blocked')
                              OR (d.needs_pass=1 AND p.verdict IS NOT 'SPLNĚNO')))
                   ORDER BY j.priority,j.rowid""",
                (now,),
            ).fetchall()
            for row in candidates:
                role, resource = row["role"], row["resource"]
                if (row["task"], role) in owners:
                    continue
                if roles[role] >= cfg.get("roles", {}).get(role, float("inf")):
                    continue
                if used[resource] >= cfg.get("resources", {}).get(resource, float("inf")):
                    continue
                if (cfg.get("reserve_verify_cpu") and resource != "verify_cpu"
                        and not used["verify_cpu"] and len(active) == cfg["parallelism"] - 1):
                    continue
                token = uuid4().hex
                lease_until = now + lease
                attempt = row["attempt"] if row["same_attempt"] else row["attempt"] + 1
                self.db.execute(
                    """UPDATE job SET state='running',worker=?,token=?,lease_until=?,attempt=?,
                       same_attempt=0
                       WHERE id=?""",
                    (worker, token, lease_until, attempt, row["id"]),
                )
                claimed = dict(row)
                claimed.update(
                    state="running", worker=worker, token=token,
                    lease_until=lease_until, attempt=attempt, same_attempt=0,
                )
                self._event(claimed, "claimed", worker)
                return claimed
        return None

    def renew(self, job_id: str, token: str, lease: float = 300) -> bool:
        if isinstance(lease, bool) or not isinstance(lease, (int, float)) or lease <= 0:
            raise ValueError("lease must be positive")
        now = time.time()
        with self._transaction():
            changed = self.db.execute(
                """UPDATE job SET lease_until=? WHERE id=? AND state='running'
                   AND token=? AND lease_until>?""",
                (now + lease, job_id, token, now),
            ).rowcount
            if changed:
                row = self.db.execute("SELECT * FROM job WHERE id=?", (job_id,)).fetchone()
                self._event(row, "renewed")
            return changed == 1

    def register_evidence(
        self, task_id: str, step_id: str, attempt: int, evidence: Iterable[dict[str, Any]]
    ) -> None:
        for item in evidence:
            ref = item.get("ref")
            if not isinstance(ref, str) or not ref.startswith(step_id + "#"):
                raise ValueError("evidence ref must be canonical and belong to step_id")
            suffix = ref.rsplit("#", 1)[-1]
            if not suffix.isdecimal():
                raise ValueError("evidence ref must use <step_id>#<index>")
            if item.get("attempt") != attempt:
                raise ValueError("evidence attempt does not match job attempt")
            self.db.execute(
                """INSERT INTO evidence(task_id,ref,step_id,attempt,evidence_id,type,uri,excerpt,sha256)
                   VALUES (?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(task_id,ref) DO UPDATE SET
                     step_id=excluded.step_id,attempt=excluded.attempt,
                     evidence_id=excluded.evidence_id,type=excluded.type,uri=excluded.uri,
                     excerpt=excluded.excerpt,sha256=excluded.sha256""",
                (task_id, ref, step_id, attempt, item["id"], item["type"], item.get("uri"),
                 item.get("excerpt", ""), item.get("sha256")),
            )

    def submit_specialist_result(self, job_id: str, token: str, result: ResultEnvelope) -> bool:
        with self._transaction():
            row = self.db.execute(
                "SELECT * FROM job WHERE id=? AND state='running' AND token=? AND lease_until>?",
                (job_id, token, time.time()),
            ).fetchone()
            if row is None:
                return False
            if row["phase"] != "specialist":
                raise ValueError("job is not in specialist phase")
            if result.task_id != row["task"] or result.step_id != job_id or result.attempt != row["attempt"]:
                raise ValueError("result envelope identity does not match claimed job")
            self.register_evidence(result.task_id, result.step_id, result.attempt,
                                   [item.__dict__ for item in result.evidence])
            payload = json.loads(row["payload"])
            payload["specialist_result"] = result.to_dict()
            self.db.execute(
                """UPDATE job SET role='overovatel',resource='verify_cpu',phase='verify_cpu',
                   state='pending',same_attempt=1,token=NULL,lease_until=NULL,
                   worker=NULL,payload=?,artifact=NULL
                   WHERE id=?""",
                (_json(payload), job_id),
            )
            self._event(row, "specialist_result_submitted")
            return True

    def advance_after_verify_cpu(
        self, job_id: str, token: str, readiness: str, artifact: Any
    ) -> bool:
        if readiness not in READINESS:
            raise ValueError(f"unsupported readiness state: {readiness!r}")
        with self._transaction():
            row = self.db.execute(
                "SELECT * FROM job WHERE id=? AND state='running' AND token=? AND lease_until>?",
                (job_id, token, time.time()),
            ).fetchone()
            if row is None:
                return False
            if row["phase"] != "verify_cpu":
                raise ValueError("job is not in verify_cpu phase")
            payload = json.loads(row["payload"])
            payload["verify_cpu"] = artifact
            if readiness == "ready":
                self.db.execute(
                    """UPDATE job SET phase='verify_content',resource='llm',state='pending',
                       same_attempt=1,
                       token=NULL,lease_until=NULL,worker=NULL,payload=? WHERE id=?""",
                    (_json(payload), job_id),
                )
                self._event(row, "verify_content_ready")
                return True
            if readiness == "skipped_due_to_failure":
                verdict = "NESPLNĚNO"
                retry_class = "substantive"
            elif readiness == "waiting_for_evidence":
                verdict = "NEOVĚŘENO"
                retry_class = "needs_evidence"
            else:
                verdict = artifact.get("verdict") if isinstance(artifact, dict) else None
                if verdict not in VERDICTS:
                    verdict = "NEOVĚŘENO"
                retry_class = None
            self._complete_verification(row, token, payload, artifact, verdict, retry_class)
            return True

    def _complete_verification(
        self, row: sqlite3.Row, token: str, payload: Any, artifact: Any, verdict: str,
        retry_class: str | None = None,
    ) -> None:
        retry_class = retry_class or self._retry_class(verdict, artifact=artifact)
        if verdict == "SPLNĚNO":
            state = "done"
            ready_at = 0
        elif self._retry_allowed(row, retry_class):
            state = "pending"
            ready_at = time.time() + min(60, 2 ** min(row["attempt"], 6))
            payload = dict(payload) if isinstance(payload, dict) else {"previous": payload}
            payload["last_verification"] = artifact
        else:
            state = "blocked"
            ready_at = 0
        next_phase = row["phase"] if state == "pending" else row["phase"]
        if state == "pending":
            payload["retry_phase"] = next_phase
        self.db.execute(
            """UPDATE job SET state=?,artifact=?,verdict=?,feedback=?,payload=?,ready_at=?,
               same_attempt=0,
               token=NULL,lease_until=NULL,worker=NULL WHERE id=? AND token=?""",
            (state, _json(artifact), verdict if state != "pending" else None,
             _json({"retry_class": retry_class}) if state == "pending" else None,
             _json(payload), ready_at, row["id"], token),
        )
        self._event(row, "verification_finished", {"verdict": verdict, "state": state})
        if state == "pending":
            self._event(row, "retry_scheduled", {"retry_class": retry_class})
        if state == "blocked":
            self._propagate_blocked(row["id"])

    def finish_verification(
        self, job_id: str, token: str, artifact: Any, verdict: str, feedback: Any = None
    ) -> bool:
        if artifact is None or verdict not in VERDICTS:
            raise ValueError("artifact and a supported verdict are required")
        with self._transaction():
            row = self.db.execute(
                "SELECT * FROM job WHERE id=? AND state='running' AND token=? AND lease_until>?",
                (job_id, token, time.time()),
            ).fetchone()
            if row is None:
                return False
            if row["phase"] not in {"verify_cpu", "verify_content"}:
                raise ValueError("job is not in a verification phase")
            retry_class = self._retry_class(verdict, feedback=feedback, artifact=artifact)
            if verdict == "SPLNĚNO":
                state, ready_at = "done", 0
            elif self._retry_allowed(row, retry_class):
                state = "pending"
                ready_at = time.time() + min(60, 2 ** min(row["attempt"], 6))
            else:
                state, ready_at = "blocked", 0
            self.db.execute(
                """UPDATE job SET state=?,artifact=?,verdict=?,feedback=?,ready_at=?,same_attempt=0,
                   token=NULL,lease_until=NULL,worker=NULL WHERE id=?""",
                (state, _json(artifact), verdict if state != "pending" else None,
                 _json(feedback) if feedback is not None else None, ready_at, job_id),
            )
            self._event(row, "verification_finished", {"verdict": verdict, "state": state})
            if state == "pending":
                self._event(row, "retry_scheduled", {"retry_class": retry_class})
            if state == "blocked":
                self._propagate_blocked(job_id)
            return True

    def finish(
        self, job_id: str, token: str, artifact: Any, verdict: str | None = None,
        feedback: Any = None,
    ) -> bool:
        if artifact is None or verdict not in (None, *VERDICTS):
            raise ValueError("artifact is required and verdict must be valid")
        with self._transaction():
            row = self.db.execute(
                "SELECT * FROM job WHERE id=? AND state='running' AND token=? AND lease_until>?",
                (job_id, token, time.time()),
            ).fetchone()
            if row is None:
                return False
            if verdict == "SPLNĚNO" or row["phase"] == "finalize":
                state, ready_at, stored_verdict = "done", 0, verdict
            else:
                retry_class = self._retry_class(verdict or "NEOVĚŘENO",
                                                feedback=feedback, artifact=artifact)
            if (verdict not in (None, "SPLNĚNO") and row["phase"] != "finalize"
                    and self._retry_allowed(row, retry_class)):
                state = "pending"
                ready_at = time.time() + min(60, 2 ** min(row["attempt"], 6))
                stored_verdict = None
            elif verdict != "SPLNĚNO" and row["phase"] != "finalize":
                state, ready_at, stored_verdict = "blocked", 0, verdict or "NEOVĚŘENO"
            self.db.execute(
                """UPDATE job SET state=?,artifact=?,verdict=?,feedback=?,ready_at=?,same_attempt=0,
                   token=NULL,lease_until=NULL,worker=NULL WHERE id=?""",
                (state, _json(artifact), stored_verdict,
                 _json(feedback) if feedback is not None else None, ready_at, job_id),
            )
            self._event(row, "finished", {"verdict": stored_verdict, "state": state})
            if state == "pending":
                self._event(row, "retry_scheduled", {"retry_class": retry_class})
            if state == "blocked":
                self._propagate_blocked(job_id)
            return True

    def _propagate_blocked(self, predecessor: str) -> None:
        dependents = self.db.execute(
            "SELECT job_id FROM dependency WHERE predecessor=? AND needs_pass=1",
            (predecessor,),
        ).fetchall()
        for item in dependents:
            row = self.db.execute("SELECT * FROM job WHERE id=?", (item["job_id"],)).fetchone()
            if row and row["state"] == "pending":
                self.db.execute(
                    """UPDATE job SET state='blocked',verdict='NEOVĚŘENO',
                       feedback=? WHERE id=?""",
                    (_json({"reason": "blocked_by_predecessor", "predecessor": predecessor}),
                     item["job_id"]),
                )
                self._event(row, "blocked_by_predecessor", predecessor)
                self._propagate_blocked(item["job_id"])

    def recover(
        self, job_id: str, token: str, *, stopped: bool, safe_to_retry: bool
    ) -> bool:
        if type(stopped) is not bool or type(safe_to_retry) is not bool:
            raise ValueError("stopped and safe_to_retry must be booleans")
        if not stopped:
            return False
        with self._transaction():
            now = time.time()
            row = self.db.execute(
                """SELECT * FROM job WHERE id=? AND state='running' AND token=?
                   AND lease_until<=?""",
                (job_id, token, now),
            ).fetchone()
            if row is None:
                return False
            retry = safe_to_retry and self._retry_allowed(row, "technical")
            state = "pending" if retry else "blocked"
            self.db.execute(
                """UPDATE job SET state=?,verdict=?,ready_at=?,same_attempt=0,
                   token=NULL,lease_until=NULL,
                   worker=NULL,feedback=? WHERE id=?""",
                (state, None if retry else "NEOVĚŘENO",
                 now + min(60, 2 ** min(row["attempt"], 6)) if retry else 0,
                 None if retry else _json({"reason": "recovery_blocked"}), job_id),
            )
            self._event(row, "requeued" if retry else "recovery_blocked")
            if retry:
                self._event(row, "retry_scheduled", {"retry_class": "technical"})
            if not retry:
                self._propagate_blocked(job_id)
            return True

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM job WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else None

    def history(self, job_id: str) -> list[dict[str, Any]]:
        return [dict(row) for row in self.db.execute(
            "SELECT * FROM history WHERE job_id=? ORDER BY seq", (job_id,)
        )]

    def evidence(self, task_id: str) -> list[dict[str, Any]]:
        return [dict(row) for row in self.db.execute(
            "SELECT * FROM v_evidence_overview WHERE task_id=? ORDER BY step_id,ref", (task_id,)
        )]

    def collect_children_results(self, parent_id: str) -> list[dict[str, Any]] | None:
        parent = self.db.execute("SELECT * FROM job WHERE id=?", (parent_id,)).fetchone()
        if parent is None:
            raise KeyError(parent_id)
        if not parent["children_closed"]:
            return None
        children = self.db.execute(
            "SELECT * FROM job WHERE parent_id=? ORDER BY rowid", (parent_id,)
        ).fetchall()
        if any(child["state"] not in {"done", "blocked"} for child in children):
            return None
        return [
            {
                "id": child["id"],
                "state": child["state"],
                "verdict": child["verdict"],
                "attempt": child["attempt"],
                "artifact": json.loads(child["artifact"]) if child["artifact"] else None,
            }
            for child in children
        ]
