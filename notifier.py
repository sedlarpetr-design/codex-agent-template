"""Jednosměrný MVP notifier (Fáze 1) pro hlášení stavu běhu přes Telegram / webhook."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


def _is_enabled() -> bool:
    val = os.getenv("NOTIFY_ENABLED", "").strip().lower()
    return val in {"1", "true", "yes", "on"}


def _get_timeout_sec(default: float = 5.0) -> float:
    raw = os.getenv("NOTIFY_TIMEOUT_SEC", "").strip()
    if not raw:
        return default
    try:
        parsed = float(raw)
        return parsed if parsed > 0 else default
    except ValueError:
        return default


def _format_message(
    task_id: str,
    status: str,
    summary: dict[str, Any] | str | None = None,
    artifact_path: str | None = None,
) -> str:
    lines = [f"[{status.upper()}] Úloha: {task_id}"]
    if isinstance(summary, dict):
        parts = [f"{k}={v}" for k, v in summary.items() if v is not None]
        if parts:
            lines.append("Souhrn: " + ", ".join(parts))
    elif summary:
        lines.append(f"Souhrn: {summary}")
    if artifact_path:
        lines.append(f"Výstup: {artifact_path}")
    return "\n".join(lines)


def _post_json(url: str, payload: dict[str, Any], timeout_sec: float) -> tuple[bool, str]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            code = getattr(resp, "status", 200)
            if 200 <= code < 300:
                return True, f"http_{code}"
            return False, f"http_{code}"
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        return False, f"error:{type(exc).__name__}:{exc}"


def send_run_notification(
    task_id: str,
    status: str,
    summary: dict[str, Any] | str | None = None,
    artifact_path: str | None = None,
) -> dict[str, Any]:
    """Odešle notifikaci o stavu běhu (DONE / ERROR / INCOMPLETE) do aktivních kanálů."""
    if not _is_enabled():
        return {"sent": False, "reason": "disabled", "channels": {}}

    timeout_sec = _get_timeout_sec()
    text = _format_message(task_id=task_id, status=status, summary=summary, artifact_path=artifact_path)

    tg_token = os.getenv("NOTIFY_TELEGRAM_BOT_TOKEN", "").strip()
    tg_chat_id = os.getenv("NOTIFY_TELEGRAM_CHAT_ID", "").strip()
    webhook_url = os.getenv("NOTIFY_WEBHOOK_URL", "").strip()

    channels: dict[str, Any] = {}

    if tg_token and tg_chat_id:
        tg_url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
        ok, detail = _post_json(
            tg_url,
            {"chat_id": tg_chat_id, "text": text},
            timeout_sec=timeout_sec,
        )
        channels["telegram"] = {"ok": ok, "detail": detail}
    elif tg_token or tg_chat_id:
        channels["telegram"] = {"ok": False, "detail": "incomplete_telegram_config"}

    if webhook_url:
        ok, detail = _post_json(
            webhook_url,
            {
                "task_id": task_id,
                "status": status.upper(),
                "summary": summary,
                "artifact_path": artifact_path,
                "text": text,
            },
            timeout_sec=timeout_sec,
        )
        channels["webhook"] = {"ok": ok, "detail": detail}

    if not channels:
        return {"sent": False, "reason": "no_channel_configured", "channels": {}}

    any_sent = any(ch.get("ok") for ch in channels.values())
    return {
        "sent": any_sent,
        "reason": "ok" if any_sent else "all_channels_failed",
        "channels": channels,
    }
