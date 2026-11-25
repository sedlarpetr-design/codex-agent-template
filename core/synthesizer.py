"""Evidence-bounded synthesis and safe structured fallback."""

from typing import Any, Callable

from .envelopes import Deliverable
from .verifier import verify


def _require_approved(approved: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(approved, list):
        raise ValueError("approved outputs must be a list")
    for item in approved:
        if not isinstance(item, dict):
            raise ValueError("approved output entries must be objects")
        status = item.get("verdict", item.get("approval"))
        if status is not None and status != "SPLNĚNO":
            raise ValueError("synthesis accepts approved outputs only")
    return approved


def known_refs(approved: list[dict[str, Any]]) -> set[str]:
    result: set[str] = set()
    for item in _require_approved(approved):
        for evidence in item.get("evidence", []):
            ref = evidence.get("ref")
            if isinstance(ref, str):
                result.add(ref)
    return result


def verify_synthesis(
    output: dict[str, Any],
    approved: list[dict[str, Any]],
    gaps: list[str],
) -> dict[str, Any]:
    _require_approved(approved)
    verdict = verify(
        "synthesis",
        output,
        {"known_refs": known_refs(approved), "unverified_count": len(gaps)},
        common=False,
    )
    return verdict.to_dict()


def synthesize_or_fallback(
    generate: Callable[[list[dict[str, Any]], list[str], str | None], dict[str, Any]],
    validate: Callable[[dict[str, Any]], dict[str, Any]],
    approved: list[dict[str, Any]],
    gaps: list[str],
    max_repairs: int = 1,
) -> dict[str, Any]:
    _require_approved(approved)
    if not isinstance(gaps, list) or not all(isinstance(item, str) for item in gaps):
        raise ValueError("gaps must be a list of strings")
    if type(max_repairs) is not int or not 0 <= max_repairs <= 2:
        raise ValueError("max_repairs must be an integer from 0 to 2")
    feedback = None
    for attempt in range(max_repairs + 1):
        output = generate(approved, gaps, feedback)
        if not isinstance(output, dict):
            raise ValueError("synthesizer must return an object")
        decision = validate(output)
        verdict = decision.get("verdict")
        if verdict == "SPLNĚNO":
            return {"verdict": "SPLNĚNO", "mode": "synthesis", "output": output}
        if verdict != "NESPLNĚNO" or attempt == max_repairs:
            break
        feedback = decision.get("fix_hint", "")
    return {
        "verdict": "NEOVĚŘENO",
        "mode": "structured_fallback",
        "approved": approved,
        "gaps": gaps,
        "reason": "Souhrnný text neprošel ověřením.",
    }


def deliverable_or_fallback(
    generate: Callable[[list[dict[str, Any]], list[str], str | None], dict[str, Any]],
    approved: list[dict[str, Any]],
    gaps: list[str],
    *,
    format: str = "report",
    max_repairs: int = 1,
) -> dict[str, Any]:
    """Run synthesis with the built-in reference and gap checks."""
    outcome = synthesize_or_fallback(
        generate,
        lambda value: verify_synthesis(value, approved, gaps),
        approved,
        gaps,
        max_repairs,
    )
    if outcome["mode"] == "synthesis":
        return Deliverable(
            status="ok",
            deliverable={"format": format, "content": outcome["output"]["deliverable"]["content"]},
            claims=outcome["output"].get("claims", []),
            conflicts=outcome["output"].get("conflicts", []),
            gaps=outcome["output"].get("gaps", []),
        ).to_dict()
    return {
        "schema_version": "1.0",
        "status": "needs_input",
        "verdict": "NEOVĚŘENO",
        "mode": "structured_fallback",
        "approved": approved,
        "gaps": gaps,
        "reason": outcome["reason"],
    }
