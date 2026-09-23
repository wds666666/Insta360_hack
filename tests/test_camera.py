import io
import subprocess
import threading
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from insta360_hack.app import create_app
from insta360_hack.config import Settings
from insta360_hack.engine.store import RunStore
from insta360_hack.insta360.service import (
    ALLOWED_FILE_NAMES,
    CameraService,
    CaptureStore,
)
from insta360_hack.insta360.projections import FFmpegTimeoutError
from insta360_hack.insta360 import projections


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        api_key="test",
        openrouter_api_key="test",
        deepseek_api_key="test",
        deepseek_model="test",
        deepseek_base_url="https://example.invalid",
        base_url="https://example.invalid",
        region="cn",
        cors_origins=[],
        data_dir=tmp_path,
        run_timeout_seconds=5,
        poll_interval_seconds=0.01,
        projection_view_size=256,
        projection_planet_size=256,
    )


def _jpeg() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (8, 8), (10, 20, 30)).save(output, "JPEG")
    return output.getvalue()


def test_camera_capture_api_persists_bundle_without_real_camera(tmp_path: Path):
    settings = _settings(tmp_path)
    store = CaptureStore(tmp_path / "captures")

    def fake_capture(output_dir: Path, *, progress, **_kwargs):
        progress("capture", "模拟拍照")
        for name in ALLOWED_FILE_NAMES:
            (output_dir / name).write_bytes(_jpeg())
        return {"camera": {"model": "Insta360 X5", "batteryLevel": 0.8}}

    service = CameraService(settings, store, capture_runner=fake_capture)
    app = create_app(
        settings,
        client=object(),
        images=object(),
        store=RunStore(tmp_path / "runs"),
        capture_store=store,
        camera_service=service,
    )
    with TestClient(app) as client:
        created = client.post("/api/v1/camera/captures")
        assert created.status_code == 202
        capture_id = created.json()["capture_id"]
        status = client.get(f"/api/v1/camera/captures/{capture_id}")
        image = client.get(
            f"/api/v1/camera/captures/{capture_id}/files/view_front.jpg"
        )
        refused = client.get(
            f"/api/v1/camera/captures/{capture_id}/files/capture.json"
        )

    assert status.json()["status"] == "succeeded"
    assert status.json()["camera"]["model"] == "Insta360 X5"
    assert set(status.json()["candidates"]) == {
        "panorama",
        "little_planet",
        "front",
        "right",
        "back",
        "left",
        "up",
        "down",
    }
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/jpeg"
    assert refused.status_code == 404
    saved = tmp_path / "captures" / capture_id
    assert (saved / "capture.json").is_file()
    assert {path.name for path in saved.glob("*.jpg")} == ALLOWED_FILE_NAMES


def test_capture_store_marks_incomplete_capture_failed_on_restart(tmp_path: Path):
    root = tmp_path / "captures"
    store = CaptureStore(root)
    record = store.create("a" * 32)
    record["status"] = "running"
    store.save(record)

    restored = CaptureStore(root).get("a" * 32)
    assert restored["status"] == "failed"
    assert restored["error"]["code"] == "INTERRUPTED"


def test_second_capture_is_rejected_while_camera_is_busy(tmp_path: Path):
    settings = _settings(tmp_path)
    store = CaptureStore(tmp_path / "captures")
    started = threading.Event()
    release = threading.Event()
    first_response = []

    def blocking_capture(_output_dir: Path, **_kwargs):
        started.set()
        assert release.wait(timeout=2)
        return {"camera": {"model": "mock"}}

    service = CameraService(settings, store, capture_runner=blocking_capture)
    app = create_app(
        settings,
        client=object(),
        images=object(),
        store=RunStore(tmp_path / "runs"),
        capture_store=store,
        camera_service=service,
    )
    with TestClient(app) as client:
        thread = threading.Thread(
            target=lambda: first_response.append(
                client.post("/api/v1/camera/captures")
            )
        )
        thread.start()
        assert started.wait(timeout=2)
        busy = client.post("/api/v1/camera/captures")
        release.set()
        thread.join(timeout=2)

    assert busy.status_code == 409
    assert busy.json()["detail"]["code"] == "CAMERA_BUSY"
    assert first_response[0].status_code == 202


def test_ffmpeg_projection_timeout_is_mapped_and_partial_file_removed(
    tmp_path: Path, monkeypatch
):
    source = tmp_path / "panorama.jpg"
    destination = tmp_path / "view_front.jpg"
    source.write_bytes(_jpeg())
    destination.write_bytes(b"partial")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired("ffmpeg", 0.01)
        ),
    )

    try:
        projections._run_v360(
            source,
            destination,
            projection="flat",
            size=256,
            yaw=0,
            pitch=0,
            fov=90,
            ffmpeg_bin="ffmpeg",
            timeout=0.01,
        )
    except FFmpegTimeoutError:
        pass
    else:
        raise AssertionError("应抛出 FFmpegTimeoutError")
    assert not destination.exists()
