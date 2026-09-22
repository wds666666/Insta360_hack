import json
from datetime import datetime, timezone
from pathlib import Path

from insta360_hack.engine.workflows import NODE_SPECS, WORKFLOW_ID


def new_record(
    run_id: str,
    *,
    prompt: str,
    style: str | None,
    image_url: str | None,
    mode: str = "auto",
) -> dict:
    return {
        "run_id": run_id,
        "workflow_id": WORKFLOW_ID,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "current_node": None,
        "nodes": [{"name": name, "label": label, "status": "pending"} for name, label in NODE_SPECS],
        "inputs": {"prompt": prompt, "style": style, "image_url": image_url, "mode": mode},
        "artifacts": {},
        "outputs": {
            "reference_image": None,
            "reference_images": None,
            "optimized_image": None,
            "model_glb": None,
            "model_stl": None,
        },
        "error": None,
    }


def resume_at(record: dict) -> str | None:
    artifacts = record.get("artifacts") or {}
    outputs = record.get("outputs") or {}
    if outputs.get("model_glb") and outputs.get("model_stl"):
        return None
    status = record.get("status")
    error_code = (record.get("error") or {}).get("code")
    recoverable = status in {"pending", "running"} or (status == "failed" and error_code == "INTERRUPTED")
    if not recoverable:
        return None
    nodes = {node.get("name"): node.get("status") for node in record.get("nodes") or []}
    if artifacts.get("export_task_id") and nodes.get("poll_stl") != "succeeded":
        return "poll_stl"
    if artifacts.get("lux3d_task_id") and nodes.get("poll_mesh") != "succeeded":
        return "poll_mesh"
    if nodes.get("poll_mesh") == "succeeded" and (artifacts.get("mesh_output_urls") or artifacts.get("mesh_glb_url")):
        if nodes.get("export_stl") != "succeeded":
            return "export_stl"
        if nodes.get("download_model") != "succeeded":
            return "download_model"
    return None


def prepare_resume(record: dict, start_at: str) -> None:
    record["status"] = "running"
    record["error"] = None
    record["current_node"] = start_at
    seen = False
    for node in record.get("nodes") or []:
        if node.get("name") == start_at:
            seen = True
        if seen:
            node["status"] = "pending"


def mark_interrupted(record: dict) -> None:
    nodes = record.get("nodes") or []
    index = next((i for i, node in enumerate(nodes) if node.get("status") != "succeeded"), 0)
    if nodes:
        nodes[index]["status"] = "failed"
        for later in nodes[index + 1 :]:
            if later.get("status") != "succeeded":
                later["status"] = "skipped"
        record["current_node"] = nodes[index].get("name")
    record["status"] = "failed"
    record["error"] = {"code": "INTERRUPTED", "message": "服务重启，任务中断"}


class RunStore:
    def __init__(self, root: Path, *, recover: bool = True):
        self.root = root
        self.recover = recover
        self.runs: dict[str, dict] = {}
        self.pending_resumes: list[tuple[dict, str]] = []
        self.load()

    def load(self) -> None:
        if not self.root.exists():
            return
        for path in self.root.glob("*/run.json"):
            record = json.loads(path.read_text())
            if self.recover:
                start_at = resume_at(record)
                if start_at:
                    prepare_resume(record, start_at)
                    path.write_text(json.dumps(record, ensure_ascii=False, indent=2))
                    self.pending_resumes.append((record, start_at))
                elif record.get("status") in {"pending", "running"}:
                    mark_interrupted(record)
                    path.write_text(json.dumps(record, ensure_ascii=False, indent=2))
            self.runs[record["run_id"]] = record

    def create(self, record: dict) -> dict:
        self.runs[record["run_id"]] = record
        self.save(record)
        return record

    def save(self, record: dict) -> None:
        directory = self.root / record["run_id"]
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "run.json").write_text(json.dumps(record, ensure_ascii=False, indent=2))

    def get(self, run_id: str) -> dict | None:
        current = self.runs.get(run_id)
        if current is not None:
            return current
        path = self.root / run_id / "run.json"
        if not path.is_file():
            return None
        record = json.loads(path.read_text())
        self.runs[record["run_id"]] = record
        return record

    def summaries(self) -> list[dict]:
        items = []
        if self.root.exists():
            for path in self.root.glob("*/run.json"):
                try:
                    record = json.loads(path.read_text())
                except (OSError, json.JSONDecodeError):
                    continue
                record.setdefault("run_id", path.parent.name)
                items.append(self._summary(record))
        items.sort(key=lambda item: item["created_at"] or "", reverse=True)
        return items

    def _summary(self, record: dict) -> dict:
        nodes = record.get("nodes") or []
        current = record.get("current_node")
        label = next((node.get("label") for node in nodes if node.get("name") == current), None)
        inputs = record.get("inputs") or {}
        return {
            "run_id": record["run_id"],
            "status": record.get("status"),
            "created_at": self._created_at(record),
            "prompt": inputs.get("prompt") or "",
            "current_label": label,
            "reference_image": self._reference_image(record),
        }

    def _reference_image(self, record: dict) -> str | None:
        outputs = record.get("outputs") or {}
        if outputs.get("reference_image"):
            return outputs["reference_image"]
        run_id = record["run_id"]
        for name in ("reference.jpg", "reference.png", "reference.webp"):
            if (self.root / run_id / name).is_file():
                return f"/api/v1/runs/{run_id}/files/{name}"
        return None

    def _created_at(self, record: dict) -> str | None:
        created = record.get("created_at")
        if isinstance(created, str) and created:
            return created
        path = self.root / record["run_id"] / "run.json"
        if not path.is_file():
            return None
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
