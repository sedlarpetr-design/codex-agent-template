"""Typed, versioned data contracts shared by all runtime adapters."""

from dataclasses import asdict, dataclass, field, fields
from typing import Any


SCHEMA_VERSION = "1.0"
VERDICTS = frozenset({"SPLNĚNO", "NESPLNĚNO", "NEOVĚŘENO"})
RETRY_CLASSES = frozenset(
    {"substantive", "needs_evidence", "technical", "waiting_input", "none"}
)
RESULT_STATUSES = frozenset({"ok", "failed", "needs_input"})
EVIDENCE_TYPES = frozenset({"quote", "file", "screenshot", "log", "calc", "url"})


def _require_text(name: str, value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _check_version(value: str) -> None:
    if value != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version: {value!r}")


def _validate_mapping(value: Any, model: type, required: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{model.__name__} must be an object")
    names = {item.name for item in fields(model)}
    missing = required - value.keys()
    extra = value.keys() - names
    if missing or extra:
        raise ValueError(
            f"invalid {model.__name__} fields; missing={sorted(missing)}, unknown={sorted(extra)}"
        )
    return value


@dataclass(frozen=True)
class Evidence:
    ref: str
    type: str
    id: str
    uri: str | None
    excerpt: str
    attempt: int
    sha256: str | None = None

    def __post_init__(self) -> None:
        _require_text("ref", self.ref)
        if "#" not in self.ref:
            raise ValueError("evidence ref must use <step_id>#<index>")
        step_id, index = self.ref.rsplit("#", 1)
        if not step_id or not index.isdecimal():
            raise ValueError("evidence ref must use <step_id>#<index>")
        if self.type not in EVIDENCE_TYPES:
            raise ValueError(f"unsupported evidence type: {self.type!r}")
        _require_text("id", self.id)
        if self.type in {"file", "screenshot", "log"} and not self.uri:
            raise ValueError(f"{self.type} evidence requires uri")
        if not isinstance(self.excerpt, str):
            raise ValueError("excerpt must be a string")
        if type(self.attempt) is not int or self.attempt < 1:
            raise ValueError("attempt must be a positive integer")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Evidence":
        if not isinstance(value, dict):
            raise ValueError("evidence must be an object")
        required = {"ref", "type", "id", "excerpt", "attempt"}
        missing = required - value.keys()
        if missing:
            raise ValueError(f"evidence missing fields: {sorted(missing)}")
        allowed = {"ref", "type", "id", "uri", "excerpt", "attempt", "sha256"}
        extra = value.keys() - allowed
        if extra:
            raise ValueError(f"unknown evidence fields: {sorted(extra)}")
        data = dict(value)
        data.setdefault("uri", None)
        return cls(**data)


@dataclass(frozen=True)
class TaskEnvelope:
    task_id: str
    step_id: str
    kind: str
    goal: str
    input: dict[str, Any]
    constraints: dict[str, Any] = field(default_factory=dict)
    attempt: int = 1
    feedback: list[dict[str, Any]] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _check_version(self.schema_version)
        for name in ("task_id", "step_id", "kind", "goal"):
            _require_text(name, getattr(self, name))
        if type(self.attempt) is not int or self.attempt < 1:
            raise ValueError("attempt must be a positive integer")
        if not isinstance(self.input, dict) or not isinstance(self.constraints, dict):
            raise ValueError("input and constraints must be objects")
        if not isinstance(self.feedback, list):
            raise ValueError("feedback must be a list")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "TaskEnvelope":
        required = {"schema_version", "task_id", "step_id", "kind", "goal", "input"}
        return cls(**_validate_mapping(value, cls, required))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ResultEnvelope:
    task_id: str
    attempt: int
    step_id: str
    kind: str
    status: str
    result: dict[str, Any]
    evidence: list[Evidence]
    confidence: float = 0.0
    notes: str = ""
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _check_version(self.schema_version)
        for name in ("task_id", "step_id", "kind"):
            _require_text(name, getattr(self, name))
        if type(self.attempt) is not int or self.attempt < 1:
            raise ValueError("attempt must be a positive integer")
        if self.status not in RESULT_STATUSES:
            raise ValueError(f"unsupported result status: {self.status!r}")
        if not isinstance(self.result, dict) or not isinstance(self.evidence, list):
            raise ValueError("result must be an object and evidence must be a list")
        if any(not isinstance(item, Evidence) for item in self.evidence):
            raise ValueError("evidence entries must be Evidence objects")
        if type(self.confidence) not in {int, float} or not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if not isinstance(self.notes, str):
            raise ValueError("notes must be a string")
        if any(item.attempt != self.attempt for item in self.evidence):
            raise ValueError("evidence attempt must match result attempt")
        if len({item.ref for item in self.evidence}) != len(self.evidence):
            raise ValueError("evidence refs must be unique within a result")
        if any(not item.ref.startswith(self.step_id + "#") for item in self.evidence):
            raise ValueError("evidence refs must belong to result step_id")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ResultEnvelope":
        required = {
            "schema_version", "task_id", "attempt", "step_id", "kind",
            "status", "result", "evidence",
        }
        data = dict(_validate_mapping(value, cls, required))
        data["evidence"] = [Evidence.from_dict(item) for item in data.get("evidence", [])]
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data


@dataclass(frozen=True)
class CriterionResult:
    criterion: str
    status: str
    evidence: list[str] = field(default_factory=list)
    reason: str = ""
    required: bool = True
    retry: str = "technical"

    def __post_init__(self) -> None:
        _require_text("criterion", self.criterion)
        if self.status not in {"met", "violated", "unverified"}:
            raise ValueError(f"unsupported criterion status: {self.status!r}")
        if not isinstance(self.evidence, list) or not all(isinstance(item, str) for item in self.evidence):
            raise ValueError("criterion evidence must be a list of strings")
        if self.retry not in RETRY_CLASSES:
            raise ValueError(f"unsupported retry class: {self.retry!r}")


@dataclass(frozen=True)
class Verdict:
    task_id: str
    step_id: str
    attempt: int
    verdict: str
    retry_class: str
    criteria: list[CriterionResult]
    notes: list[dict[str, str]] = field(default_factory=list)
    fix_hint: str = ""
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _check_version(self.schema_version)
        for name in ("task_id", "step_id"):
            _require_text(name, getattr(self, name))
        if type(self.attempt) is not int or self.attempt < 1:
            raise ValueError("attempt must be a positive integer")
        if self.verdict not in VERDICTS:
            raise ValueError(f"unsupported verdict: {self.verdict!r}")
        if self.retry_class not in RETRY_CLASSES:
            raise ValueError(f"unsupported retry class: {self.retry_class!r}")
        if any(not isinstance(item, CriterionResult) for item in self.criteria):
            raise ValueError("criteria entries must be CriterionResult objects")
        if len({item.criterion for item in self.criteria}) != len(self.criteria):
            raise ValueError("criterion IDs must be unique")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Verdict":
        required = {
            "schema_version", "task_id", "step_id", "attempt", "verdict",
            "retry_class", "criteria",
        }
        data = dict(_validate_mapping(value, cls, required))
        data["criteria"] = [CriterionResult(**item) for item in data.get("criteria", [])]
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Deliverable:
    status: str
    deliverable: dict[str, str]
    claims: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _check_version(self.schema_version)
        if self.status not in {"ok", "needs_input", "failed"}:
            raise ValueError(f"unsupported deliverable status: {self.status!r}")
        if not isinstance(self.deliverable, dict) or not {"format", "content"} <= self.deliverable.keys():
            raise ValueError("deliverable must contain format and content")
        if not isinstance(self.deliverable["format"], str) or not isinstance(self.deliverable["content"], str):
            raise ValueError("deliverable format and content must be strings")
        if not isinstance(self.claims, list) or not isinstance(self.conflicts, list) or not isinstance(self.gaps, list):
            raise ValueError("claims, conflicts, and gaps must be lists")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Deliverable":
        required = {"schema_version", "status", "deliverable"}
        return cls(**_validate_mapping(value, cls, required))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
