"""Deterministic decimal-based accounting calculations."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from core.envelopes import Evidence, ResultEnvelope, TaskEnvelope


class AccountingSpecialist:
    def work(self, task: TaskEnvelope) -> ResultEnvelope:
        rows = task.input.get("rows")
        if not isinstance(rows, list) or not rows:
            return ResultEnvelope(
                task.task_id, task.attempt, task.step_id, task.kind, "needs_input",
                {}, [], notes="input.rows musí obsahovat alespoň jednu položku",
            )
        rounding = task.input.get("rules", {}).get("rounding", "2dp")
        if rounding != "2dp":
            raise ValueError(f"unsupported rounding rule: {rounding!r}")
        quantum = Decimal("0.01")
        items = []
        try:
            for row in rows:
                net = Decimal(str(row["net"])).quantize(quantum, rounding=ROUND_HALF_UP)
                rate = Decimal(str(row["vat_rate"]))
                if not net.is_finite() or not rate.is_finite() or not Decimal("0") <= rate <= Decimal("1"):
                    raise ValueError("net must be finite and vat_rate must be between 0 and 1")
                vat = (net * rate).quantize(quantum, rounding=ROUND_HALF_UP)
                items.append({
                    "desc": row["desc"],
                    "net": str(net),
                    "vat": str(vat),
                    "amount": str((net + vat).quantize(quantum, rounding=ROUND_HALF_UP)),
                })
        except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
            return ResultEnvelope(
                task.task_id, task.attempt, task.step_id, task.kind, "failed",
                {}, [], notes=f"neplatná účetní položka: {exc}",
            )
        total_net = sum((Decimal(item["net"]) for item in items), Decimal("0"))
        total_vat = sum((Decimal(item["vat"]) for item in items), Decimal("0"))
        total = total_net + total_vat
        result: dict[str, Any] = {
            "items": items,
            "total_net": str(total_net.quantize(quantum, rounding=ROUND_HALF_UP)),
            "total_vat": str(total_vat.quantize(quantum, rounding=ROUND_HALF_UP)),
            "total": str(total.quantize(quantum, rounding=ROUND_HALF_UP)),
            "currency": task.input.get("currency", "CZK"),
        }
        excerpt = f"net={result['total_net']}; vat={result['total_vat']}; total={result['total']}"
        evidence = Evidence(
            ref=f"{task.step_id}#0", type="calc", id="accounting-totals",
            uri=None, excerpt=excerpt, attempt=task.attempt,
        )
        return ResultEnvelope(
            task_id=task.task_id, attempt=task.attempt, step_id=task.step_id, kind=task.kind,
            status="ok", result=result, evidence=[evidence],
        )
