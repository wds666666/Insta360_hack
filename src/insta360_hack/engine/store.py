import json
from pathlib import Path

from insta360_hack.engine.workflows import NODE_SPECS, WORKFLOW_ID


def new_record(run_id: str, *, prompt: str, style: str | None, image_url: str | None) -> dict:
    return {
        "run_id": run_id,
        "workflow_id": WORKFLOW_ID,
        "status": "pending",
        "current_node": None,
        "nodes": [{"name": name, "label": label, "status": "pending"} for name, label in NODE_SPECS],
        "inputs": {"prompt": prompt, "style": style, "image_url": image_url},
        "artifacts": {},
        "outputs": {
            "reference_image": None,
            "optimized_image": None,
            "model_glb": None,
            "model_stl": None,
        },
        "error": None,
    }


class RunStore:
    def __init__(self, root: Path, *, recover: bool = True):
        self.root = root
        self.recover = recover
        self.runs: dict[str, dict] = {}
        self.load()

    def load(self) -> None:
        if not self.root.exists():
            return
        for path in self.root.glob("*/run.json"):
            record = json.loads(path.read_text())
            if self.recover and record.get("status") in {"pending", "running"}:
                record["status"] = "failed"
                record["error"] = {"code": "INTERRUPTED", "message": "服务重启，任务中断"}
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
        return self.runs.get(run_id)
