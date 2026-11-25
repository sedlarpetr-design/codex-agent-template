"""Code-first verification with evidence-backed three-state verdicts."""

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import re
from pathlib import Path
from typing import Any, Callable

from .envelopes import CriterionResult, Verdict


@dataclass
class R:
    criterion: str
    status: str
    evidence: list[str] = field(default_factory=list)
    reason: str = ""
    required: bool = True
    retry: str = "technical"


REGISTRY: dict[str, list[Callable[..., R | None]]] = {}
REQUIRED: dict[str, set[str]] = {}


def met(criterion: str, evidence: list[str]) -> R:
    return R(criterion, "met", evidence)


def violated(criterion: str, reason: str, evidence: list[str]) -> R:
    return R(criterion, "violated", evidence, reason)


def unverified(criterion: str, reason: str, retry: str = "technical") -> R:
    return R(criterion, "unverified", [], reason, retry=retry)


def note(criterion: str, reason: str) -> R:
    return R(criterion, "violated", [], reason, required=False)


def check(kind: str, criterion: str, required: bool = True):
    def decorate(function: Callable[..., R | None]):
        if any(getattr(existing, "criterion", None) == criterion
               for existing in REGISTRY.get(kind, [])):
            raise ValueError(f"duplicate criterion: {criterion}")
        function.criterion = criterion
        function.required = required
        REGISTRY.setdefault(kind, []).append(function)
        if required:
            REQUIRED.setdefault(kind, set()).add(criterion)
        return function
    return decorate


def normalized_quote(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("quote must be a string")
    translation = str.maketrans({"„": '"', "“": '"', "”": '"', "«": '"', "»": '"',
                                 "’": "'", "‘": "'"})
    return " ".join(value.translate(translation).split())


def build_verdict(
    kind: str,
    out: dict[str, Any],
    results: list[R],
    not_applicable: set[str] | None = None,
    common: bool = True,
) -> Verdict:
    not_applicable = not_applicable or set()
    required = (
        (REQUIRED.get("*", set()) if common else set()) | REQUIRED.get(kind, set())
    ) - not_applicable
    by_criterion = {result.criterion: result for result in results}
    violations = [
        result for result in results
        if result.required and result.status == "violated" and result.evidence
    ]
    unproven = [
        criterion for criterion in required
        if criterion not in by_criterion
        or not by_criterion[criterion].evidence
        or by_criterion[criterion].status == "unverified"
    ]
    if violations:
        verdict = "NESPLNĚNO"
        retry_class = "substantive"
        fix_hint = "; ".join(item.reason for item in violations)
    elif unproven or not required:
        retries = {by_criterion[item].retry for item in unproven if item in by_criterion}
        if out.get("status") == "needs_input":
            retry_class = "waiting_input"
        elif "needs_evidence" in retries:
            retry_class = "needs_evidence"
        else:
            retry_class = "technical"
        verdict = "NEOVĚŘENO"
        fix_hint = (
            "chybí důkaz pro: " + ", ".join(sorted(unproven))
            if unproven else "není doložené povinné kritérium"
        )
    else:
        verdict, retry_class, fix_hint = "SPLNĚNO", "none", ""

    criteria = [
        CriterionResult(
            criterion=item.criterion,
            status=item.status,
            evidence=item.evidence,
            reason=item.reason,
            required=item.required,
            retry=item.retry,
        )
        for item in results if item.required
    ]
    notes = [
        {"criterion": item.criterion, "reason": item.reason}
        for item in results if not item.required
    ]
    return Verdict(
        task_id=str(out.get("task_id", "synthesis")),
        step_id=str(out.get("step_id", "synthesis")),
        attempt=out.get("attempt", 1) if type(out.get("attempt", 1)) is int else 1,
        verdict=verdict,
        retry_class=retry_class,
        criteria=criteria,
        notes=notes,
        fix_hint=fix_hint[:500],
    )


def verify(
    kind: str, out: dict[str, Any], ctx: dict[str, Any], common: bool = True
) -> Verdict:
    if not isinstance(out, dict) or not isinstance(ctx, dict):
        raise ValueError("out and ctx must be objects")
    functions = (REGISTRY.get("*", []) if common else []) + REGISTRY.get(kind, [])
    results: list[R] = []
    not_applicable: set[str] = set()
    for function in functions:
        criterion = function.criterion
        if ctx.get("inapplicable", {}).get(criterion):
            not_applicable.add(criterion)
            continue
        try:
            result = function(out, ctx)
        except Exception:
            result = unverified(criterion, "kontrola selhala")
        if result is None:
            if not function.required:
                not_applicable.add(criterion)
                continue
            result = unverified(criterion, "chybí důkaz nebo rozhodnutí o použitelnosti")
        if result.criterion != criterion:
            result = unverified(criterion, "kontrola vrátila jiné ID kritéria")
        result.required = function.required
        results.append(result)
    return build_verdict(kind, out, results, not_applicable, common)


def readiness_after_cpu(
    verdict: Verdict | dict[str, Any],
    *,
    content_criteria: list[str],
    evidence_records: list[dict[str, Any]],
    task_id: str | None = None,
    attempt: int | None = None,
    required_evidence: dict[str, list[str]] | None = None,
) -> str:
    """Resolve the verify_cpu -> verify_content transition."""
    data = verdict.to_dict() if isinstance(verdict, Verdict) else verdict
    if not content_criteria:
        return "not_needed"
    if data.get("verdict") == "NESPLNĚNO":
        return "skipped_due_to_failure"
    if data.get("verdict") != "SPLNĚNO":
        return "waiting_for_evidence"
    eligible = []
    for record in evidence_records:
        if task_id is not None and record.get("task_id") != task_id:
            continue
        if attempt is not None and record.get("attempt") != attempt:
            continue
        if not record.get("ref") or not record.get("readable", True):
            continue
        eligible.append(record)
    available = {record["ref"] for record in eligible}
    requirements = required_evidence or {}
    for criterion in content_criteria:
        refs = set(requirements.get(criterion, []))
        if not refs:
            refs = {
                record["ref"] for record in eligible
                if record.get("criterion") == criterion
            }
        if not refs or not refs <= available:
            return "waiting_for_evidence"
    return "ready"


def extract_normalized_numbers(text: str, locale: str) -> tuple[set[tuple[Decimal, str]], list[str]]:
    """Parse unambiguous cs/en numeric values and their optional units."""
    formats = {
        "cs": re.compile(r"(?:\d{1,3}(?:[ \u00a0\u202f]\d{3})+|\d+)(?:,\d+)?\Z"),
        "en": re.compile(r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\Z"),
    }
    if locale not in formats:
        raise ValueError("číselný formát musí být cs nebo en")
    pattern = re.compile(
        r"(?<!\w)(?P<sign>[+\-−]?)(?P<number>\d+(?:[.,]\d+|[ \u00a0\u202f]\d{3})*)"
        r"(?:[ \t\u00a0\u202f]*(?P<unit>%|Kč|CZK|EUR|USD|€|\$|kg|km|mm|ms|h|m|s)(?!\w))?",
        re.IGNORECASE,
    )
    unit_aliases = {"kč": "CZK", "czk": "CZK", "€": "EUR", "eur": "EUR",
                    "usd": "USD", "$": "$"}
    values: set[tuple[Decimal, str]] = set()
    ambiguous: list[str] = []
    for match in pattern.finditer(text):
        raw = match.group("number")
        unit = (match.group("unit") or "").lower()
        if not formats[locale].fullmatch(raw) or unit == "$":
            ambiguous.append(match.group(0))
            continue
        normalized = re.sub(r"[ \u00a0\u202f]", "", raw)
        normalized = normalized.replace(",", ".") if locale == "cs" else normalized.replace(",", "")
        sign = "-" if match.group("sign") == "−" else match.group("sign")
        try:
            value = Decimal(sign + normalized)
        except InvalidOperation:
            ambiguous.append(match.group(0))
            continue
        values.add((value, unit_aliases.get(unit, unit)))
    return values, ambiguous


def compare_numbers(
    out_text: str, source_texts: list[str], ctx: dict[str, Any]
) -> tuple[set[Any], bool]:
    allowed_facts = ctx.get("numeric_facts")
    used_claims = ctx.get("numeric_claims")
    if allowed_facts is not None and used_claims is not None:
        return set(used_claims) - set(allowed_facts), False
    if "source_number_locale" not in ctx or "output_number_locale" not in ctx:
        return set(), True
    used, output_uncertain = extract_normalized_numbers(out_text, ctx["output_number_locale"])
    if not used and not output_uncertain:
        return set(), False
    allowed: set[tuple[Decimal, str]] = set()
    uncertain = bool(output_uncertain) or not source_texts
    for source in source_texts:
        values, ambiguous = extract_normalized_numbers(source, ctx["source_number_locale"])
        allowed.update(values)
        uncertain = uncertain or bool(ambiguous)
    return used - allowed, uncertain


@check("*", "envelope_ok")
def _envelope_ok(out: dict[str, Any], ctx: dict[str, Any]) -> R:
    required = {"schema_version", "task_id", "step_id", "kind", "status", "result", "evidence", "attempt"}
    missing = required - out.keys()
    if missing:
        return violated("envelope_ok", "chybí pole: " + str(sorted(missing)), ["envelope"])
    if out.get("schema_version") != "1.0":
        return violated("envelope_ok", "nepodporovaná schema_version", ["envelope.schema_version"])
    if not isinstance(out.get("evidence"), list) or not isinstance(out.get("result"), dict):
        return violated("envelope_ok", "result nebo evidence nemá správný typ", ["envelope"])
    return met("envelope_ok", ["envelope"])


@check("*", "status_ok")
def _status_ok(out: dict[str, Any], ctx: dict[str, Any]) -> R:
    if out.get("status") == "ok":
        return met("status_ok", ["envelope.status"])
    return unverified("status_ok", f"status={out.get('status')}: {out.get('notes', '')}")


@check("*", "evidence_present")
def _evidence_present(out: dict[str, Any], ctx: dict[str, Any]) -> R:
    evidence = out.get("evidence") or []
    if not evidence:
        return unverified("evidence_present", "specialista nedodal důkaz", "needs_evidence")
    refs = [item.get("ref") for item in evidence if isinstance(item, dict)]
    if len(refs) != len(evidence) or any(
        ref not in ctx.get("available_refs", ()) for ref in refs
    ):
        return unverified("evidence_present", "odkaz na důkaz nelze načíst", "needs_evidence")
    return met("evidence_present", refs)


@check("*", "quotes_in_source")
def _quotes_in_source(out: dict[str, Any], ctx: dict[str, Any]) -> R:
    source = ctx.get("source_text")
    quotes = [item for item in out.get("evidence", [])
              if isinstance(item, dict) and item.get("type") == "quote"]
    if not source or not quotes:
        return unverified("quotes_in_source", "chybí původní zdroj nebo citát", "needs_evidence")
    normalized_source = normalized_quote(source)
    bad = [item for item in quotes
           if not normalized_quote(item.get("excerpt", ""))
           or normalized_quote(item.get("excerpt", "")) not in normalized_source]
    if bad:
        return violated("quotes_in_source", f"{len(bad)} citátů není ve zdroji",
                        [item["ref"] for item in bad])
    return met("quotes_in_source", [item["ref"] for item in quotes])


@check("web_test", "steps_passed")
def _steps_passed(out: dict[str, Any], ctx: dict[str, Any]) -> R:
    steps = out.get("result", {}).get("steps", [])
    available = ctx.get("available_refs", ())
    if not steps or any(not step.get("evidence_ref") or step["evidence_ref"] not in available
                        for step in steps):
        return unverified("steps_passed", "chybí důkaz kroku", "needs_evidence")
    failed = [step for step in steps
              if step.get("status") == "failed" and step.get("target_observed") is True]
    broken = [step for step in steps if step.get("status") != "passed" and step not in failed]
    if failed:
        reason = "; ".join(f"{step.get('name', step.get('step_id'))}: {step.get('actual')}"
                           for step in failed)
        return violated("steps_passed", reason, [step["evidence_ref"] for step in failed])
    if broken:
        return unverified("steps_passed", "nespuštěno nebo chyba: "
                          + str([step.get("name", step.get("step_id")) for step in broken]))
    return met("steps_passed", [step["evidence_ref"] for step in steps])


@check("web_test", "scenario_covered")
def _scenario_covered(out: dict[str, Any], ctx: dict[str, Any]) -> R:
    desired = [step["step_id"] for step in ctx["task_input"]["scenario"]]
    steps = out.get("result", {}).get("steps", [])
    actual = [step["step_id"] for step in steps]
    if not desired or len(set(desired)) != len(desired) or sorted(desired) != sorted(actual):
        return unverified("scenario_covered", "neúplná nebo duplicitní ID kroků")
    return met("scenario_covered", [step["evidence_ref"] for step in steps])


@check("web_test", "failed_have_screenshot", required=False)
def _failed_have_screenshot(out: dict[str, Any], ctx: dict[str, Any]) -> R | None:
    failed = out.get("result", {}).get("summary", {}).get("failed", 0)
    if failed and not any(item.get("type") == "screenshot" for item in out.get("evidence", [])):
        return note("failed_have_screenshot", "chybí screenshot")
    return None


@check("files", "files_readable")
def _files_readable(out: dict[str, Any], ctx: dict[str, Any]) -> R:
    bad, good = [], []
    for item in out.get("result", {}).get("files", []):
        path = item.get("path", "")
        if not Path(path).exists():
            bad.append((path, "neexistuje"))
        elif not item.get("parsed_ok"):
            bad.append((path, "nejde přečíst: " + str(item.get("errors", []))))
        else:
            good.append(path)
    if bad:
        return violated("files_readable", "; ".join(f"{path}: {reason}" for path, reason in bad),
                        [path or "result.files" for path, _ in bad])
    if not good:
        return unverified("files_readable", "chybí zpracované soubory", "needs_evidence")
    return met("files_readable", good)


@check("files", "all_inputs_covered")
def _all_inputs_covered(out: dict[str, Any], ctx: dict[str, Any]) -> R:
    desired = set(ctx.get("task_input", {}).get("paths", []))
    actual = {item.get("path") for item in out.get("result", {}).get("files", [])}
    if not desired:
        return unverified("all_inputs_covered", "chybí seznam vstupních souborů")
    missing = desired - actual
    if missing:
        return unverified("all_inputs_covered", "nezpracováno: " + str(sorted(missing)))
    return met("all_inputs_covered", sorted(actual))


@check("accounting", "totals_match")
def _totals_match(out: dict[str, Any], ctx: dict[str, Any]) -> R:
    result = out.get("result", {})
    items = result.get("items", [])
    try:
        net = sum((Decimal(str(item["net"])) for item in items), Decimal("0"))
        vat = sum((Decimal(str(item["vat"])) for item in items), Decimal("0"))
        total = sum((Decimal(str(item["amount"])) for item in items), Decimal("0"))
        stated_net = Decimal(str(result["total_net"]))
        stated_vat = Decimal(str(result["total_vat"]))
        stated_total = Decimal(str(result["total"]))
    except (KeyError, InvalidOperation, TypeError):
        return unverified("totals_match", "chybí platné částky", "needs_evidence")
    errors = []
    if net != stated_net:
        errors.append(f"net {net} != {stated_net}")
    if vat != stated_vat:
        errors.append(f"vat {vat} != {stated_vat}")
    if total != stated_total or net + vat != stated_total:
        errors.append(f"total {net + vat} != {stated_total}")
    for index, item in enumerate(items):
        if Decimal(str(item["net"])) + Decimal(str(item["vat"])) != Decimal(str(item["amount"])):
            errors.append(f"items[{index}] amount does not equal net + vat")
    if errors:
        return violated("totals_match", "; ".join(errors),
                        [f"items[{index}]" for index in range(len(items))] or ["result"])
    if not items:
        return unverified("totals_match", "chybí účetní položky")
    return met("totals_match", ["calc:sum(items)"])


@check("accounting", "rows_match_input")
def _rows_match_input(out: dict[str, Any], ctx: dict[str, Any]) -> R:
    wanted = len(ctx.get("task_input", {}).get("rows", []))
    actual = len(out.get("result", {}).get("items", []))
    if wanted != actual:
        return violated("rows_match_input", f"{actual} položek, ve vstupu {wanted}",
                        ["result.items", "input.rows"])
    return met("rows_match_input", ["result.items", "input.rows"])


@check("synthesis", "refs_exist")
def _refs_exist(out: dict[str, Any], ctx: dict[str, Any]) -> R:
    claims = out.get("claims", [])
    refs = [ref for claim in claims for ref in claim.get("evidence_refs", [])]
    if any(not claim.get("evidence_refs") for claim in claims) or any(
        ref not in ctx.get("known_refs", ()) for ref in refs
    ):
        return violated("refs_exist", "chybějící nebo neznámé reference", ["claims"])
    content = out.get("deliverable", {}).get("content", "")
    if not claims and content.strip():
        return unverified("refs_exist", "text nemá doložený seznam tvrzení", "needs_evidence")
    return met("refs_exist", refs or ["claims"])


@check("synthesis", "deliverable_ok")
def _deliverable_ok(out: dict[str, Any], ctx: dict[str, Any]) -> R:
    deliverable = out.get("deliverable")
    if (out.get("schema_version") != "1.0" or out.get("status") != "ok"
            or not isinstance(deliverable, dict)
            or not isinstance(deliverable.get("format"), str)
            or not isinstance(deliverable.get("content"), str)
            or not isinstance(out.get("claims"), list)
            or not isinstance(out.get("conflicts"), list)
            or not isinstance(out.get("gaps"), list)):
        return violated("deliverable_ok", "deliverable nemá platný tvar/schema_version",
                        ["deliverable"])
    return met("deliverable_ok", ["deliverable"])


@check("synthesis", "gaps_reported")
def _gaps_reported(out: dict[str, Any], ctx: dict[str, Any]) -> R:
    if ctx.get("unverified_count", 0) and not out.get("gaps"):
        return violated("gaps_reported", "neověřené kroky nejsou v gaps",
                        ["unverified:" + str(ctx["unverified_count"])])
    return met("gaps_reported", ["gaps"])
