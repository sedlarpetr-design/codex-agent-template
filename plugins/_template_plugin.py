PLUGIN_META = {
    "name": "_template_plugin",
    "version": "1.0.0",
    "description": "Vzorovy plugin se sjednocenou logikou skip_already_active a reset_to_base",
    "capabilities": ["deterministic_check", "state_flags"],
}


def run_plugin(item_ctx: dict, verifier_cfg: dict) -> dict:
    already_active = bool(item_ctx.get("already_active", False))
    skip_active = bool(verifier_cfg.get("skip_already_active", False))
    reset_to_base = bool(verifier_cfg.get("reset_to_base", True))

    if already_active and skip_active:
        return {
            "anomaly": False,
            "anomaly_reasons": "",
            "llm_status": "LLM_SKIPPED",
            "llm_verdict": f"skipped_already_active;reset_to_base={reset_to_base}",
        }

    return {
        "anomaly": False,
        "anomaly_reasons": "",
        "llm_status": "LLM_SKIPPED",
        "llm_verdict": f"reset_to_base={reset_to_base}",
    }
