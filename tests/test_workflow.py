import asyncio
import base64
import json
import os
import time
from datetime import datetime
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from insta360_hack.app import create_app
from insta360_hack.config import Settings
from insta360_hack.engine.store import RunStore, new_record
from insta360_hack.engine.workflows import NODE_NAMES
from insta360_hack.lux3d.client import Lux3DError
from insta360_hack.lux3d.models import Lux3DTask, output_slots, parse_g1_outputs
from insta360_hack.nodes import NODES
from insta360_hack.openrouter.client import OpenRouterClient

PNG = b"\x89PNG-test-image"
OPTIMIZED = b"optimized-png"


class FakeImages:
    def __init__(self):
        self.calls: list[dict] = []

    async def generate(self, *, prompt: str, image_bytes: bytes, media_type: str) -> tuple[bytes, str]:
        self.calls.append({"prompt": prompt, "image_bytes": image_bytes, "media_type": media_type})
        return OPTIMIZED, "image/png"


class FakeLux3D:
    def __init__(self, *, fail_upload: bool = False):
        self.fail_upload = fail_upload
        self.created: list[dict] = []
        self.exports: list[str] = []
        self.downloads: list[str] = []
        self.output_at_upload: dict | None = None
        self._seen: dict[int, int] = {}

    async def upload_file(self, path: Path) -> str:
        if self.fail_upload:
            raise Lux3DError("UPLOAD_FAILED", "参考图上传失败")
        assert path.name == "optimized.png"
        assert path.read_bytes() == OPTIMIZED
        self.output_at_upload = json.loads((path.parent / "run.json").read_text())["outputs"]
        return "https://cdn.example/optimized.png"

    async def create_img_to_3d(self, *, image_url: str) -> int:
        self.created.append({"img": image_url, "version": "G1", "outputFormat": ["glb"]})
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


def test_output_slots_keep_positions():
    assert output_slots(
        [None, {"content": "null"}, {"content": "NOT_REQUESTED"}, {"content": "https://cdn.example/a.stl"}]
    ) == [None, None, None, "https://cdn.example/a.stl"]


def test_node_order_matches_workflow():
    assert [node.name for node in NODES] == NODE_NAMES


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        api_key="test-key",
        openrouter_api_key="test-or-key",
        base_url="https://api.aholo3d.cn",
        region="cn",
        cors_origins=["http://localhost:5173"],
        data_dir=tmp_path,
        run_timeout_seconds=5,
        poll_interval_seconds=0.01,
    )


def _client(
    tmp_path: Path,
    fake: FakeLux3D,
    images: FakeImages,
    store: RunStore | None = None,
) -> TestClient:
    settings = _settings(tmp_path)
    app = create_app(
        settings,
        client=fake,
        images=images,
        store=store or RunStore(settings.data_dir / "runs"),
    )
    return TestClient(app)


def test_parse_g1_outputs_keeps_slot_order():
    parsed = parse_g1_outputs(["zip-url", "glb-url", "ply-url"])
    assert parsed == {"zip_url": "zip-url", "glb_url": "glb-url", "ply_url": "ply-url"}


def test_missing_image_does_not_call_lux3d(tmp_path: Path):
    fake = FakeLux3D()
    images = FakeImages()
    with _client(tmp_path, fake, images) as client:
        response = client.post("/api/v1/runs", data={"workflow_id": "img-to-3d", "prompt": "一把椅子"})
    assert response.status_code == 422
    assert fake.created == []
    assert images.calls == []


def test_upload_saves_reference_then_downloads_model(tmp_path: Path):
    fake = FakeLux3D()
    images = FakeImages()
    with _client(tmp_path, fake, images) as client:
        created = client.post(
            "/api/v1/runs",
            data={"workflow_id": "img-to-3d", "prompt": "一把浅色原木餐椅", "style": "cartoon"},
            files={"image": ("ref.png", PNG, "image/png")},
        )
        assert created.status_code == 202
        run_id = created.json()["run_id"]
        body = client.get(f"/api/v1/runs/{run_id}").json()
        glb = client.get(body["outputs"]["model_glb"])
        stl = client.get(body["outputs"]["model_stl"])
        reference = client.get(body["outputs"]["reference_image"])
        optimized = client.get(body["outputs"]["optimized_image"])
        listed = client.get("/api/v1/runs").json()["runs"]

    assert body["status"] == "succeeded"
    assert body["artifacts"]["image_url"] == "https://cdn.example/optimized.png"
    assert images.calls == [
        {
            "prompt": "一把浅色原木餐椅\n风格：cartoon",
            "image_bytes": PNG,
            "media_type": "image/png",
        }
    ]
    assert fake.created == [
        {"img": "https://cdn.example/optimized.png", "version": "G1", "outputFormat": ["glb"]}
    ]
    assert "prompt" not in fake.created[0]
    assert "ply" not in fake.created[0]["outputFormat"]
    assert fake.output_at_upload["optimized_image"].endswith("/optimized.png")
    assert fake.output_at_upload["model_glb"] is None
    assert fake.exports == ["https://cdn.example/mesh.glb"]
    run_dir = tmp_path / "runs" / run_id
    assert (run_dir / "reference.png").read_bytes() == PNG
    assert (run_dir / "optimized.png").read_bytes() == OPTIMIZED
    assert (run_dir / "model.glb").read_bytes() == b"glb"
    assert (run_dir / "model.stl").read_bytes() == b"stl"
    assert not (run_dir / "model.ply").exists()
    assert glb.content == b"glb"
    assert stl.content == b"stl"
    assert reference.content == PNG
    assert optimized.content == OPTIMIZED
    assert body["nodes"][2]["label"] == "优化参考图"
    assert isinstance(body["artifacts"]["poll_mesh_elapsed_seconds"], int)
    assert body["artifacts"]["poll_mesh_started_at"]
    assert isinstance(body["artifacts"]["optimize_image_elapsed_seconds"], int)
    assert body["artifacts"]["optimize_image_started_at"]
    assert body["inputs"]["mode"] == "auto"
    assert listed[0]["run_id"] == run_id
    assert listed[0]["prompt"] == "一把浅色原木餐椅"
    assert listed[0]["reference_image"].endswith("/reference.png")


def test_upload_failure_stops_before_create(tmp_path: Path):
    fake = FakeLux3D(fail_upload=True)
    images = FakeImages()
    with _client(tmp_path, fake, images) as client:
        created = client.post(
            "/api/v1/runs",
            data={"workflow_id": "img-to-3d", "prompt": "椅子"},
            files={"image": ("ref.png", PNG, "image/png")},
        )
        body = client.get(f"/api/v1/runs/{created.json()['run_id']}").json()
    assert body["status"] == "failed"
    assert body["error"]["code"] == "UPLOAD_FAILED"
    assert body["nodes"][2]["status"] == "succeeded"
    assert body["nodes"][3]["status"] == "failed"
    assert body["outputs"]["optimized_image"].endswith("/optimized.png")
    assert body["outputs"]["model_glb"] is None
    assert fake.created == []
    run_dir = tmp_path / "runs" / body["run_id"]
    assert (run_dir / "reference.png").is_file()
    assert (run_dir / "optimized.png").read_bytes() == OPTIMIZED


def test_list_runs_reads_saved_tasks_newest_first(tmp_path: Path):
    root = tmp_path / "runs"
    older = new_record("older", prompt="旧椅子", style=None, image_url=None)
    newer = new_record("newer", prompt="新房间", style=None, image_url=None)
    missing_time = new_record("plain", prompt="没有时间戳", style=None, image_url=None)
    older["created_at"] = "2026-09-22T01:00:00+00:00"
    newer["created_at"] = "2026-09-22T03:00:00+00:00"
    del missing_time["created_at"]
    store = RunStore(root, recover=False)
    store.create(older)
    store.create(missing_time)
    store.create(newer)
    plain_file = root / "plain" / "run.json"
    middle = datetime.fromisoformat("2026-09-22T02:00:00+00:00").timestamp()
    os.utime(plain_file, (middle, middle))
    reloaded = RunStore(root, recover=False)
    with _client(tmp_path, FakeLux3D(), FakeImages(), store=reloaded) as client:
        body = client.get("/api/v1/runs").json()
    assert [item["run_id"] for item in body["runs"]] == ["newer", "plain", "older"]
    assert body["runs"][0]["prompt"] == "新房间"
    assert body["runs"][1]["created_at"]


def test_list_runs_includes_a_folder_not_loaded_in_memory(tmp_path: Path):
    root = tmp_path / "runs"
    store = RunStore(root, recover=False)
    record = new_record("disk-only", prompt="只在磁盘上", style=None, image_url=None)
    directory = root / "disk-only"
    directory.mkdir(parents=True)
    (directory / "run.json").write_text(json.dumps(record))
    (directory / "reference.jpg").write_bytes(b"jpg")
    with _client(tmp_path, FakeLux3D(), FakeImages(), store=store) as client:
        body = client.get("/api/v1/runs").json()
        opened = client.get("/api/v1/runs/disk-only")
    assert body["runs"][0]["run_id"] == "disk-only"
    assert body["runs"][0]["reference_image"].endswith("/reference.jpg")
    assert opened.status_code == 200


def test_confirm_mode_waits_for_mesh_decision(tmp_path: Path):
    fake = FakeLux3D()
    images = FakeImages()
    with _client(tmp_path, fake, images) as client:
        created = client.post(
            "/api/v1/runs",
            data={"workflow_id": "img-to-3d", "prompt": "一间空房间", "mode": "confirm"},
            files={"image": ("ref.png", PNG, "image/png")},
        )
        assert created.status_code == 202
        run_id = created.json()["run_id"]
        paused = client.get(f"/api/v1/runs/{run_id}").json()
        assert paused["status"] == "awaiting_mesh"
        assert paused["outputs"]["optimized_image"].endswith("/optimized.png")
        assert paused["outputs"]["model_glb"] is None
        assert paused["nodes"][2]["status"] == "succeeded"
        assert paused["nodes"][3]["status"] == "pending"
        assert fake.created == []
        refused = client.post("/api/v1/runs/missing/mesh")
        assert refused.status_code == 404
        continued = client.post(f"/api/v1/runs/{run_id}/mesh")
        assert continued.status_code == 202
        done = client.get(f"/api/v1/runs/{run_id}").json()
        assert done["status"] == "succeeded"
        assert done["outputs"]["model_glb"].endswith("/model.glb")
        assert fake.created == [
            {"img": "https://cdn.example/optimized.png", "version": "G1", "outputFormat": ["glb"]}
        ]
        again = client.post(f"/api/v1/runs/{run_id}/mesh")
        assert again.status_code == 409


def test_awaiting_mesh_survives_restart(tmp_path: Path):
    root = tmp_path / "runs"
    record = new_record("pause", prompt="房间", style=None, image_url=None, mode="confirm")
    record["status"] = "awaiting_mesh"
    RunStore(root).create(record)
    assert RunStore(root).get("pause")["status"] == "awaiting_mesh"


def test_restart_marks_running_task_interrupted(tmp_path: Path):
    root = tmp_path / "runs"
    record = new_record("abc", prompt="椅子", style=None, image_url="https://cdn.example/a.jpg")
    record["status"] = "running"
    record["current_node"] = "optimize_image"
    record["nodes"][0]["status"] = "succeeded"
    record["nodes"][1]["status"] = "succeeded"
    record["nodes"][2]["status"] = "running"
    RunStore(root).create(record)
    reloaded = RunStore(root)
    saved = reloaded.get("abc")
    assert saved["status"] == "failed"
    assert saved["error"]["code"] == "INTERRUPTED"
    assert saved["nodes"][2]["status"] == "failed"
    assert saved["nodes"][3]["status"] == "skipped"
    assert json.loads((root / "abc" / "run.json").read_text())["status"] == "failed"


def test_restart_resumes_interrupted_mesh(tmp_path: Path):
    root = tmp_path / "runs"
    record = new_record("mesh", prompt="房间", style=None, image_url=None)
    record["status"] = "failed"
    record["error"] = {"code": "INTERRUPTED", "message": "服务重启，任务中断"}
    record["artifacts"] = {"lux3d_task_id": 99, "image_url": "https://cdn.example/optimized.png"}
    for node in record["nodes"]:
        if node["name"] == "poll_mesh":
            node["status"] = "running"
            break
        node["status"] = "succeeded"
    store = RunStore(root)
    store.create(record)
    reloaded = RunStore(root)
    assert reloaded.get("mesh")["status"] == "running"
    assert reloaded.pending_resumes[0][1] == "poll_mesh"
    fake = FakeLux3D()
    with _client(tmp_path, fake, FakeImages(), store=reloaded) as client:
        deadline = time.monotonic() + 3
        body = {"status": "running"}
        while time.monotonic() < deadline:
            body = client.get("/api/v1/runs/mesh").json()
            if body["status"] in {"succeeded", "failed"}:
                break
            time.sleep(0.05)
    assert body["status"] == "succeeded", body.get("error")
    assert body["outputs"]["model_glb"].endswith("/model.glb")
    assert (root / "mesh" / "model.glb").read_bytes() == b"glb"


def test_openrouter_sends_reference_image():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["json"] = json.loads(request.content)
        seen["auth"] = request.headers["authorization"]
        body = {
            "data": [
                {"b64_json": base64.b64encode(OPTIMIZED).decode("ascii"), "media_type": "image/png"}
            ]
        }
        return httpx.Response(200, json=body)

    async def run() -> None:
        settings = Settings(
            api_key="test-key",
            openrouter_api_key="test-or-key",
            base_url="https://api.aholo3d.cn",
            region="cn",
            cors_origins=[],
            data_dir=Path("."),
            run_timeout_seconds=5,
            poll_interval_seconds=1,
        )
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http:
            raw, media = await OpenRouterClient(http, settings).generate(
                prompt="椅子", image_bytes=PNG, media_type="image/png"
            )
        assert raw == OPTIMIZED
        assert media == "image/png"

    asyncio.run(run())
    assert seen["auth"] == "Bearer test-or-key"
    assert seen["json"]["model"] == "google/gemini-3.1-flash-image"
    assert seen["json"]["prompt"] == "椅子"
    assert seen["json"]["resolution"] == "1K"
    assert seen["json"]["aspect_ratio"] == "16:9"
    reference = seen["json"]["input_references"][0]["image_url"]["url"]
    assert reference == "data:image/png;base64," + base64.b64encode(PNG).decode("ascii")
