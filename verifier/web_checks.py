from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class R:
    criterion: str
    status: str  # 'met' | 'violated' | 'unverified'
    evidence: list[str] = field(default_factory=list)
    reason: str = ""
    required: bool = True
    retry: str = "technical"


def met(criterion: str, evidence: list[str]) -> R:
    return R(criterion, "met", evidence)


def violated(criterion: str, reason: str, evidence: list[str]) -> R:
    return R(criterion, "violated", evidence, reason)


def unverified(criterion: str, reason: str, retry: str = "technical") -> R:
    return R(criterion, "unverified", [], reason, retry=retry)


def note(criterion: str, reason: str) -> R:
    return R(criterion, "violated", [], reason, required=False)


REGISTRY: dict[str, list[Callable[[dict[str, Any], dict[str, Any]], R | None]]] = {}
REQUIRED: dict[str, set[str]] = {}


def check(kind: str, criterion: str, required: bool = True):
    def deco(fn: Callable[[dict[str, Any], dict[str, Any]], R | None]):
        if any(getattr(f, "criterion", None) == criterion for f in REGISTRY.get(kind, [])):
            raise ValueError(f"Duplicitní kritérium: {criterion}")
        fn.criterion = criterion  # type: ignore[attr-defined]
        fn.required = required  # type: ignore[attr-defined]
        REGISTRY.setdefault(kind, []).append(fn)
        if required:
            REQUIRED.setdefault(kind, set()).add(criterion)
        return fn

    return deco


def normalized_quote(value: str) -> str:
    return " ".join(value.translate(str.maketrans("„“”«»’‘", '"""""\'\'')).split())


def build_verdict(
    kind: str,
    out: dict[str, Any],
    results: list[R],
    n_a: set[str],
    common: bool = True,
) -> dict[str, Any]:
    required = ((REQUIRED.get("*", set()) if common else set()) | REQUIRED.get(kind, set())) - n_a
    by = {r.criterion: r for r in results}
    violations = [r for r in results if r.required and r.status == "violated" and r.evidence]
    unproven = [
        c
        for c in required
        if c not in by or not by[c].evidence or by[c].status == "unverified"
    ]
    if violations:
        verdict, retry = "NESPLNĚNO", "substantive"
        hint = "; ".join(r.reason for r in violations)
    elif unproven or not required:
        kinds = {by[c].retry for c in unproven if c in by}
        if out.get("status") == "needs_input":
            retry = "waiting_input"
        elif "needs_evidence" in kinds:
            retry = "needs_evidence"
        else:
            retry = "technical"
        verdict = "NEOVĚŘENO"
        hint = (
            "chybí důkaz pro: " + ", ".join(sorted(unproven))
            if unproven
            else "není doložené povinné kritérium"
        )
    else:
        verdict, retry, hint = "SPLNĚNO", "none", ""

    return {
        "schema_version": "1.0",
        "task_id": out.get("task_id"),
        "step_id": out.get("step_id"),
        "attempt": out.get("attempt", 0),
        "verdict": verdict,
        "retry_class": retry,
        "criteria": [asdict(r) for r in results if r.required],
        "notes": [asdict(r) for r in results if not r.required],
        "fix_hint": hint[:500],
    }


def verify(kind: str, out: dict[str, Any], ctx: dict[str, Any], common: bool = True) -> dict[str, Any]:
    fns = (REGISTRY.get("*", []) if common else []) + REGISTRY.get(kind, [])
    results: list[R] = []
    n_a: set[str] = set()
    for fn in fns:
        crit = getattr(fn, "criterion")
        req = getattr(fn, "required", True)
        if ctx.get("inapplicable", {}).get(crit):
            n_a.add(crit)
            continue
        try:
            r = fn(out, ctx)
        except Exception as exc:
            r = unverified(crit, f"kontrola selhala: {type(exc).__name__}")
        if r is None:
            if not req:
                n_a.add(crit)
                continue
            r = unverified(crit, "chybí důkaz nebo rozhodnutí o použitelnosti")
        if r.criterion != crit:
            r = unverified(crit, "kontrola vrátila jiné ID kritéria")
        r.required = req
        results.append(r)
    return build_verdict(kind, out, results, n_a, common)


@check("*", "envelope_ok")
def envelope_ok(out: dict[str, Any], ctx: dict[str, Any]) -> R:
    need = {"task_id", "step_id", "kind", "status", "result", "evidence"}
    missing = need - out.keys()
    if missing:
        return violated("envelope_ok", f"chybí pole: {sorted(missing)}", ["envelope"])
    return met("envelope_ok", ["envelope"])


@check("*", "status_ok")
def status_ok(out: dict[str, Any], ctx: dict[str, Any]) -> R:
    status = out.get("status")
    if status == "ok":
        return met("status_ok", ["envelope.status"])
    return unverified("status_ok", f"status={status}: {out.get('notes', '')}")


@check("*", "evidence_present")
def evidence_present(out: dict[str, Any], ctx: dict[str, Any]) -> R:
    ev = out.get("evidence") or []
    if not ev:
        return unverified("evidence_present", "specialista nedodal důkaz", "needs_evidence")
    refs = [e.get("ref") for e in ev if e.get("ref")]
    available = set(ctx.get("available_refs", ()))
    if available and any(ref not in available for ref in refs):
        return unverified("evidence_present", "odkaz na důkaz nelze načíst", "needs_evidence")
    return met("evidence_present", refs)


@check("web_test", "steps_passed")
def steps_passed(out: dict[str, Any], ctx: dict[str, Any]) -> R:
    steps = out.get("result", {}).get("steps", [])
    available = set(ctx.get("available_refs", ()))
    if not steps or any(
        not s.get("evidence_ref") or (available and s["evidence_ref"] not in available)
        for s in steps
    ):
        return unverified("steps_passed", "chybí důkaz kroku", "needs_evidence")
    failed = [s for s in steps if s.get("status") == "failed" and s.get("target_observed") is True]
    broken = [s for s in steps if s.get("status") != "passed" and s not in failed]
    if failed:
        reason = "; ".join(f"{s.get('name')}: {s.get('actual')}" for s in failed)
        return violated("steps_passed", reason, [s["evidence_ref"] for s in failed])
    if broken:
        return unverified("steps_passed", f"nespuštěno nebo chyba: {[s.get('name') for s in broken]}")
    return met("steps_passed", [s["evidence_ref"] for s in steps])


@check("web_test", "scenario_covered")
def scenario_covered(out: dict[str, Any], ctx: dict[str, Any]) -> R:
    want = [s["step_id"] for s in ctx.get("task_input", {}).get("scenario", [])]
    steps = out.get("result", {}).get("steps", [])
    got = [s.get("step_id") for s in steps]
    if not want or len(set(want)) != len(want) or sorted(want) != sorted(got):
        return unverified("scenario_covered", "neúplná nebo duplicitní ID kroků")
    return met("scenario_covered", [s["evidence_ref"] for s in steps if s.get("evidence_ref")])


@check("web_test", "http_status_200", required=False)
def http_status_200(out: dict[str, Any], ctx: dict[str, Any]) -> R | None:
    page = out.get("result", {}).get("page", {})
    code = page.get("status_code")
    if code is None:
        return None
    if int(code) != 200:
        return note("http_status_200", f"očekáván HTTP 200, vráceno {code}")
    return met("http_status_200", ["result.page.status_code"])


@check("web_test", "seo_basics_valid", required=False)
def seo_basics_valid(out: dict[str, Any], ctx: dict[str, Any]) -> R | None:
    seo = out.get("result", {}).get("seo", {})
    if not seo:
        return None
    issues = []
    if not str(seo.get("title", "")).strip():
        issues.append("prázdný <title>")
    if not str(seo.get("meta_description", "")).strip():
        issues.append("chybí meta description")
    if int(seo.get("h1_count", 0)) != 1:
        issues.append(f"počet H1 je {seo.get('h1_count', 0)} místo 1")
    if issues:
        return note("seo_basics_valid", "; ".join(issues))
    return met("seo_basics_valid", ["result.seo"])


@check("web_test", "ai_search_llms_txt", required=False)
def ai_search_llms_txt(out: dict[str, Any], ctx: dict[str, Any]) -> R | None:
    ai = out.get("result", {}).get("ai_search", {})
    if not ai:
        return None
    if not ai.get("llms_txt_ok"):
        return note("ai_search_llms_txt", "llms.txt chybí nebo není validní Markdown")
    return met("ai_search_llms_txt", ["result.ai_search"])


@check("web_test", "i18n_and_currency_consistent", required=False)
def i18n_and_currency_consistent(out: dict[str, Any], ctx: dict[str, Any]) -> R | None:
    i18n = out.get("result", {}).get("i18n", {})
    if not i18n:
        return None
    issues = []
    if not i18n.get("html_lang"):
        issues.append("chybí atribut html[lang]")
    if i18n.get("mixed_currencies"):
        issues.append(f"smíšené měny na stránce: {i18n['mixed_currencies']}")
    if issues:
        return note("i18n_and_currency_consistent", "; ".join(issues))
    return met("i18n_and_currency_consistent", ["result.i18n"])


@check("web_test", "security_and_cookies_ok", required=False)
def security_and_cookies_ok(out: dict[str, Any], ctx: dict[str, Any]) -> R | None:
    sec = out.get("result", {}).get("security", {})
    if not sec:
        return None
    issues = []
    if not sec.get("https"):
        issues.append("stránka neběží přes HTTPS")
    if sec.get("tracking_before_consent"):
        issues.append("sledovací cookies aktivní před souhlasem")
    if issues:
        return note("security_and_cookies_ok", "; ".join(issues))
    return met("security_and_cookies_ok", ["result.security"])


@check("web_test", "perf_within_budget", required=False)
def perf_within_budget(out: dict[str, Any], ctx: dict[str, Any]) -> R | None:
    perf = out.get("result", {}).get("perf", {})
    if not perf:
        return None
    ttfb = perf.get("ttfb_ms", 0)
    limit = ctx.get("thresholds", {}).get("max_ttfb_ms", 1200)
    if ttfb > limit:
        return note("perf_within_budget", f"TTFB {ttfb} ms překročilo limit {limit} ms")
    return None


@check("web_test", "failed_have_screenshot", required=False)
def failed_have_screenshot(out: dict[str, Any], ctx: dict[str, Any]) -> R | None:
    has_shot = any(e.get("type") == "screenshot" for e in out.get("evidence", []))
    failed_cnt = out.get("result", {}).get("summary", {}).get("failed", 0)
    if failed_cnt and not has_shot:
        return note("failed_have_screenshot", "chybí screenshot u selhaného kroku")
    return None


@check("meta_audit", "passage_labels_schema_valid")
def meta_passage_labels_valid(out: dict[str, Any], ctx: dict[str, Any]) -> R:
    passages = out.get("result", {}).get("pasaze", [])
    if not passages:
        return unverified("passage_labels_schema_valid", "chybí seznam pasáží", "needs_evidence")
    seen_ids: set[str] = set()
    for idx, p in enumerate(passages):
        pid = p.get("id")
        if not pid or pid in seen_ids or not str(p.get("text", "")).strip() or not p.get("umisteni"):
            return violated("passage_labels_schema_valid", f"neplatná nebo duplicitní pasáž na indexu {idx}", [f"pasaze[{idx}]"])
        seen_ids.add(pid)
    return met("passage_labels_schema_valid", [f"pasaze:{len(passages)}"])


@check("meta_audit", "passage_quotes_exact_in_source")
def meta_quotes_in_source(out: dict[str, Any], ctx: dict[str, Any]) -> R:
    src = ctx.get("source_text", "")
    passages = out.get("result", {}).get("pasaze", [])
    if not src or not passages:
        return unverified("passage_quotes_exact_in_source", "chybí zdrojový text nebo pasáže", "needs_evidence")
    norm_src = normalized_quote(src)
    bad = [p.get("id", "?") for p in passages if normalized_quote(str(p.get("text", ""))) not in norm_src]
    if bad:
        return violated("passage_quotes_exact_in_source", f"pasáže nenalezeny doslova ve zdroji: {bad}", bad)
    return met("passage_quotes_exact_in_source", [p["id"] for p in passages])


@check("meta_audit", "sbom_and_docs_versions_aligned")
def meta_sbom_docs_aligned(out: dict[str, Any], ctx: dict[str, Any]) -> R:
    versions = out.get("result", {}).get("versions", {})
    if not versions:
        return unverified("sbom_and_docs_versions_aligned", "chybí mapování verzí SBOM/docs", "needs_evidence")
    unique_core = {v for k, v in versions.items() if k in {"core", "docs", "sbom"} and v}
    if len(unique_core) != 1:
        return violated("sbom_and_docs_versions_aligned", f"nesoulad verzí: {versions}", ["result.versions"])
    return met("sbom_and_docs_versions_aligned", ["result.versions"])


@check("meta_audit", "verdict_matches_criteria_rules")
def meta_verdict_consistent(out: dict[str, Any], ctx: dict[str, Any]) -> R:
    target_verdict = out.get("result", {}).get("target_verdict", {})
    if not target_verdict:
        return unverified("verdict_matches_criteria_rules", "chybí posuzovaný verdikt", "needs_evidence")
    v = target_verdict.get("verdict")
    criteria = target_verdict.get("criteria", [])
    has_violation = any(c.get("status") == "violated" and c.get("evidence") for c in criteria)
    has_unproven = any(c.get("status") == "unverified" or not c.get("evidence") for c in criteria)
    expected = "NESPLNĚNO" if has_violation else ("NEOVĚŘENO" if (has_unproven or not criteria) else "SPLNĚNO")
    if v != expected:
        return violated("verdict_matches_criteria_rules", f"verdikt {v} neodpovídá pravidlům (očekáváno {expected})", ["target_verdict"])
    return met("verdict_matches_criteria_rules", ["target_verdict"])


@check("meta_audit", "every_claim_has_known_evidence_ref")
def meta_claims_refs_exist(out: dict[str, Any], ctx: dict[str, Any]) -> R:
    claims = out.get("result", {}).get("claims", [])
    known = set(ctx.get("known_refs", ()))
    bad = [
        c.get("text", "")[:40]
        for c in claims
        if not c.get("evidence_refs") or any(r not in known for r in c["evidence_refs"])
    ]
    if bad:
        return violated("every_claim_has_known_evidence_ref", f"nepodložená tvrzení: {bad}", ["result.claims"])
    return met("every_claim_has_known_evidence_ref", ["result.claims"])


@check("meta_audit", "unverified_steps_listed_in_gaps")
def meta_gaps_reported(out: dict[str, Any], ctx: dict[str, Any]) -> R:
    unverified_steps = set(ctx.get("unverified_steps", ()))
    gaps_text = "\n".join(out.get("result", {}).get("gaps", []))
    missing = [s for s in unverified_steps if s not in gaps_text]
    if missing:
        return violated("unverified_steps_listed_in_gaps", f"neověřené kroky chybí v gaps: {missing}", ["result.gaps"])
    return met("unverified_steps_listed_in_gaps", ["result.gaps"])


@check("meta_audit", "model_not_truncated_by_length")
def meta_no_length_truncation(out: dict[str, Any], ctx: dict[str, Any]) -> R:
    meta = out.get("result", {}).get("llm_meta", {})
    if meta.get("done_reason") == "length":
        return violated("model_not_truncated_by_length", "výstup modelu byl oříznut (done_reason=length)", ["result.llm_meta"])
    return met("model_not_truncated_by_length", ["result.llm_meta"])


@check("meta_audit", "audit_jsonl_properly_closed")
def meta_audit_closed(out: dict[str, Any], ctx: dict[str, Any]) -> R:
    audit_path = out.get("result", {}).get("audit_jsonl_path")
    if not audit_path or not Path(audit_path).is_file():
        return unverified("audit_jsonl_properly_closed", "audit.jsonl neexistuje", "needs_evidence")
    lines = [ln for ln in Path(audit_path).read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        return violated("audit_jsonl_properly_closed", "audit.jsonl je prázdný", [audit_path])
    last = json.loads(lines[-1])
    if last.get("event") == "audit_neuplny" or last.get("event") != "run_closed":
        return violated("audit_jsonl_properly_closed", f"běh nebyl řádně uzavřen: {last.get('event')}", [audit_path])
    return met("audit_jsonl_properly_closed", [audit_path])


@check("meta_audit", "attempts_and_ids_traceable", required=False)
def meta_ids_traceable(out: dict[str, Any], ctx: dict[str, Any]) -> R | None:
    if not out.get("task_id") or not out.get("step_id") or int(out.get("attempt", 0)) < 1:
        return note("attempts_and_ids_traceable", "chybí kompletní trojice task_id + step_id + attempt")
    return None
