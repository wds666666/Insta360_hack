import json
from pathlib import Path

from fastapi.testclient import TestClient

from insta360_hack.app import create_app
from insta360_hack.config import Settings
from insta360_hack.engine.store import RunStore, new_record
from insta360_hack.lux3d.client import Lux3DError
from insta360_hack.lux3d.models import Lux3DTask, output_slots, parse_g1_outputs


def test_output_slots_keep_positions():
    assert output_slots(
        [None, {"content": "null"}, {"content": "NOT_REQUESTED"}, {"content": "https://cdn.example/a.stl"}]
    ) == [None, None, None, "https://cdn.example/a.stl"]

PNG = b"\x89PNG-test-image"


class FakeLux3D:
    def __init__(self, *, fail_upload: bool = False):
        self.fail_upload = fail_upload
        self.created: list[dict] = []
        self.exports: list[str] = []
        self.downloads: list[str] = []
        self._seen: dict[int, int] = {}

    async def upload_file(self, path: Path) -> str:
        if self.fail_upload:
            raise Lux3DError("UPLOAD_FAILED", "参考图上传失败")
        assert path.read_bytes() == PNG
        return "https://cdn.example/ref.jpg"

    async def create_text_to_3d(self, *, prompt: str, image_url: str, style: str | None) -> int:
        self.created.append(
            {
                "prompt": prompt,
                "img": image_url,
                "style": style,
                "version": "G1",
                "outputFormat": ["glb"],
            }
        )
        return 99

    async def create_stl_export(self, *, model_url: str) -> int:
        self.exports.append(model_url)
        return 100

    async def get_task(self, task_id: int) -> Lux3DTask:
        seen = self._seen.get(task_id, 0)
        self._seen[task_id] = seen + 1
        if task_id == 99:
            if seen == 0:
                return Lux3DTask(status=1, outputs=[])
            return Lux3DTask(status=3, outputs=["https://cdn.example/a.zip", "https://cdn.example/mesh.glb"])
        if seen == 0:
            return Lux3DTask(status=1, outputs=[])
        slots: list[str | None] = [None] * 7
        slots[1] = "https://cdn.example/mesh.glb"
        slots[5] = "https://cdn.example/model.stl"
        return Lux3DTask(status=3, outputs=slots)

    async def download(self, url: str, dest: Path) -> None:
        dest.write_bytes(b"stl" if url.endswith(".stl") else b"glb")
        self.downloads.append(url)


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        api_key="test-key",
        base_url="https://api.aholo3d.cn",
        region="cn",
        cors_origins=["http://localhost:5173"],
        data_dir=tmp_path,
        run_timeout_seconds=5,
        poll_interval_seconds=0.01,
    )


def _client(tmp_path: Path, fake: FakeLux3D) -> TestClient:
    settings = _settings(tmp_path)
    app = create_app(settings, client=fake, store=RunStore(settings.data_dir / "runs"))
    return TestClient(app)


def test_parse_g1_outputs_keeps_slot_order():
    parsed = parse_g1_outputs(["zip-url", "glb-url", "ply-url"])
    assert parsed == {"zip_url": "zip-url", "glb_url": "glb-url", "ply_url": "ply-url"}


def test_missing_image_does_not_call_lux3d(tmp_path: Path):
    fake = FakeLux3D()
    with _client(tmp_path, fake) as client:
        response = client.post("/api/v1/runs", data={"workflow_id": "text-to-3d", "prompt": "一把椅子"})
    assert response.status_code == 422
    assert fake.created == []


def test_upload_saves_reference_then_downloads_model(tmp_path: Path):
    fake = FakeLux3D()
    with _client(tmp_path, fake) as client:
        created = client.post(
            "/api/v1/runs",
            data={"workflow_id": "text-to-3d", "prompt": "一把浅色原木餐椅"},
            files={"image": ("ref.png", PNG, "image/png")},
        )
        assert created.status_code == 202
        run_id = created.json()["run_id"]
        body = client.get(f"/api/v1/runs/{run_id}").json()
        glb = client.get(body["outputs"]["model_glb"])
        stl = client.get(body["outputs"]["model_stl"])
        reference = client.get(body["outputs"]["reference_image"])

    assert body["status"] == "succeeded"
    assert body["artifacts"]["image_url"] == "https://cdn.example/ref.jpg"
    assert fake.created == [
        {
            "prompt": "一把浅色原木餐椅",
            "img": "https://cdn.example/ref.jpg",
            "style": None,
            "version": "G1",
            "outputFormat": ["glb"],
        }
    ]
    assert fake.exports == ["https://cdn.example/mesh.glb"]
    assert (tmp_path / "runs" / run_id / "reference.png").read_bytes() == PNG
    assert (tmp_path / "runs" / run_id / "model.glb").read_bytes() == b"glb"
    assert (tmp_path / "runs" / run_id / "model.stl").read_bytes() == b"stl"
    assert not (tmp_path / "runs" / run_id / "model.ply").exists()
    assert glb.content == b"glb"
    assert stl.content == b"stl"
    assert reference.content == PNG


def test_upload_failure_stops_before_create(tmp_path: Path):
    fake = FakeLux3D(fail_upload=True)
    with _client(tmp_path, fake) as client:
        created = client.post(
            "/api/v1/runs",
            data={"workflow_id": "text-to-3d", "prompt": "椅子"},
            files={"image": ("ref.png", PNG, "image/png")},
        )
        body = client.get(f"/api/v1/runs/{created.json()['run_id']}").json()
    assert body["status"] == "failed"
    assert body["error"]["code"] == "UPLOAD_FAILED"
    assert body["nodes"][1]["status"] == "succeeded"
    assert body["nodes"][2]["status"] == "failed"
    assert fake.created == []
    assert (tmp_path / "runs" / body["run_id"] / "reference.png").is_file()


def test_restart_marks_running_task_interrupted(tmp_path: Path):
    root = tmp_path / "runs"
    record = new_record("abc", prompt="椅子", style=None, image_url="https://cdn.example/a.jpg")
    record["status"] = "running"
    RunStore(root).create(record)
    reloaded = RunStore(root)
    assert reloaded.get("abc")["status"] == "failed"
    assert reloaded.get("abc")["error"]["code"] == "INTERRUPTED"
    assert json.loads((root / "abc" / "run.json").read_text())["status"] == "failed"
