import csv
import importlib.util
import json
import sys
import time
from pathlib import Path


def load_yaml_simple(path: Path) -> dict:
    try:
        import yaml
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except ImportError:
        data = {}
        stack = [(0, data)]
        for raw in path.read_text(encoding="utf-8").splitlines():
            s = raw.strip()
            if not s or s.startswith("#") or ":" not in s:
                continue
            indent = len(raw) - len(raw.lstrip(" "))
            while len(stack) > 1 and indent <= stack[-1][0]:
                stack.pop()
            k, v = [p.strip() for p in s.split(":", 1)]
            if v == "":
                child = {}
                stack[-1][1][k] = child
                stack.append((indent, child))
            else:
                low = v.lower()
                if low == "true":
                    val = True
                elif low == "false":
                    val = False
                elif v.isdigit():
                    val = int(v)
                else:
                    val = v.strip('"').strip("'")
                stack[-1][1][k] = val
        return data


def select_items(items: list, limit: int, mode: str) -> list:
    if not limit or limit <= 0 or limit >= len(items):
        return items
    if mode == "head":
        return items[:limit]
    if mode == "all":
        return items
    step = len(items) / limit
    return [items[int(i * step)] for i in range(limit)]


def discover_plugins(plugins_dir: Path, cache: dict) -> dict:
    found = {}
    if not plugins_dir.exists():
        return found
    for py in sorted(plugins_dir.glob("*.py")):
        if py.name.startswith("__"):
            continue
        mtime = py.stat().st_mtime
        prev = cache.get(py.stem)
        if prev and prev["mtime"] == mtime:
            found[py.stem] = prev["mod"]
            continue
        spec = importlib.util.spec_from_file_location(f"tpl_plugin_{py.stem}", str(py))
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            cache[py.stem] = {"mtime": mtime, "mod": mod}
            found[py.stem] = mod
    return found


def _load_dotenv_if_present(env_path) -> None:
    try:
        from pathlib import Path
        import os
        p = Path(env_path)
        if not p.is_file():
            return
        for raw_line in p.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
    except Exception:
        pass

def main() -> int:
    if len(sys.argv) < 2:
        print("Pouziti: python runner_template.py <profil.yaml>")
        return 2
    root = Path(__file__).resolve().parent
    _load_dotenv_if_present(root / ".env")
    cfg_path = Path(sys.argv[1])
    if not cfg_path.is_absolute():
        cfg_path = root / cfg_path
    cfg = load_yaml_simple(cfg_path)
    src = cfg.get("source") or {}
    ver = cfg.get("verifier") or {}
    out = cfg.get("output") or {}

    in_file = root / str(src.get("urls_file", ""))
    raw_items = (
        [ln.strip() for ln in in_file.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.strip().startswith("#")]
        if in_file.exists()
        else []
    )
    limit = int(src.get("limit", 0) or 0)
    mode = str(src.get("sample_mode", "strided"))
    selected = select_items(raw_items, limit, mode)

    out_dir = root / str(out.get("dir", "runs/template-run-01"))
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / str(out.get("csv", "results.csv"))
    log_path = out_dir / str(out.get("log", "diag.txt"))

    cache = {}
    plugin_name = str(ver.get("plugin", "_template_plugin"))
    plugin = discover_plugins(root / "plugins", cache).get(plugin_name)
    meta = getattr(plugin, "PLUGIN_META", {})

    status = "audit_neuplny"
    with csv_path.open("w", encoding="utf-8", newline="") as f_csv, log_path.open("w", encoding="utf-8") as f_log:
        writer = csv.DictWriter(f_csv, fieldnames=["item", "anomaly", "anomaly_reasons", "llm_status", "llm_verdict"])
        writer.writeheader()
        f_csv.flush()
        f_log.write(f"nacteno={len(raw_items)} limit={limit} sample_mode={mode} vybrano={len(selected)} plugin={plugin_name} meta={meta}\n")
        f_log.flush()
        try:
            for item in selected:
                plugin = discover_plugins(root / "plugins", cache).get(plugin_name) or plugin
                res = (
                    plugin.run_plugin({"item": item}, ver)
                    if plugin and hasattr(plugin, "run_plugin")
                    else {"anomaly": False, "anomaly_reasons": "", "llm_status": "LLM_SKIPPED", "llm_verdict": ""}
                )
                writer.writerow({"item": item, **res})
                f_csv.flush()
                f_log.write(json.dumps({"item": item, **res}, ensure_ascii=False) + "\n")
                f_log.flush()
                time.sleep(0.01)
            status = "run_closed"
        except KeyboardInterrupt:
            status = "audit_neuplny"
        finally:
            f_log.write(f"status={status}\n")
            f_log.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

