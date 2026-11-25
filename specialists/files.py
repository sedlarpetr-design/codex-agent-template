"""Local, code-driven file inspection specialist."""

import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile
from typing import Any

from core.envelopes import Evidence, ResultEnvelope, TaskEnvelope


class FilesSpecialist:
    def work(self, task: TaskEnvelope) -> ResultEnvelope:
        paths = task.input.get("paths")
        if (not isinstance(paths, list) or not paths
                or any(not isinstance(path, str) or not path for path in paths)):
            return ResultEnvelope(
                task.task_id, task.attempt, task.step_id, task.kind, "needs_input",
                {}, [], notes="input.paths musí obsahovat alespoň jeden soubor",
            )
        files = []
        evidence = []
        rules = task.input.get("rules", {})
        max_bytes = int(float(rules.get("max_size_mb", 50)) * 1024 * 1024)
        csv_rules = rules.get("csv", {})
        for index, raw_path in enumerate(paths):
            path = Path(raw_path)
            item: dict[str, Any] = {
                "path": str(path), "type": path.suffix.lower().lstrip("."),
                "size": None, "sha256": None, "parsed_ok": False,
                "errors": [], "extracted": {},
            }
            try:
                data = path.read_bytes()
                item["size"] = len(data)
                item["sha256"] = hashlib.sha256(data).hexdigest()
                if len(data) > max_bytes:
                    item["errors"].append(f"file exceeds max_size_mb ({rules.get('max_size_mb', 50)})")
                else:
                    try:
                        self._inspect(path, data, item, csv_rules)
                    except (UnicodeError, ValueError, csv.Error, zipfile.BadZipFile) as exc:
                        item["errors"].append(f"invalid {item['type']} data: {exc}")
            except OSError as exc:
                item["errors"].append(f"cannot read file: {exc.strerror or exc.__class__.__name__}")
            files.append(item)
            excerpt = (
                f"type={item['type']}; size={item['size']}; "
                f"parsed_ok={str(item['parsed_ok']).lower()}; errors={'; '.join(item['errors'])}"
            )
            evidence.append(Evidence(
                ref=f"{task.step_id}#{index}", type="file", id=f"file-{index}",
                uri=str(path), excerpt=excerpt[:500], attempt=task.attempt,
                sha256=item["sha256"],
            ))
        return ResultEnvelope(
            task_id=task.task_id, attempt=task.attempt, step_id=task.step_id, kind=task.kind,
            status="ok", result={"files": files}, evidence=evidence,
        )

    @staticmethod
    def _inspect(path: Path, data: bytes, item: dict[str, Any], csv_rules: dict[str, Any]) -> None:
        suffix = path.suffix.lower()
        if suffix == ".json":
            value = json.loads(data.decode("utf-8"))
            item["extracted"] = {"top_level_type": type(value).__name__}
        elif suffix == ".csv":
            text = data.decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            missing = set(csv_rules.get("required_columns", [])) - set(reader.fieldnames or [])
            rows = list(reader)
            if missing:
                item["errors"].append(f"missing CSV columns: {', '.join(sorted(missing))}")
            item["extracted"] = {"rows": len(rows), "columns": reader.fieldnames or []}
        elif suffix == ".zip":
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                bad_member = archive.testzip()
                if bad_member:
                    item["errors"].append(f"corrupt archive member: {bad_member}")
                item["extracted"] = {"members": len(archive.infolist())}
        elif suffix == ".pdf":
            try:
                from pypdf import PdfReader
                from pypdf.errors import PdfReadError
            except ImportError:
                item["errors"].append("PDF reader dependency pypdf is not installed")
            else:
                try:
                    reader = PdfReader(io.BytesIO(data))
                    item["extracted"] = {"pages": len(reader.pages)}
                except (PdfReadError, ValueError, OSError) as exc:
                    item["errors"].append(f"invalid PDF data: {exc}")
        item["parsed_ok"] = not item["errors"]
