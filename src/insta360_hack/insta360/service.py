from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from insta360_hack.config import Settings
from insta360_hack.insta360.capture import capture_bundle
from insta360_hack.insta360.client import (
    Insta360OSCClient,
    OSCError,
    OSCResponseError,
)
from insta360_hack.insta360.projections import FFmpegTimeoutError


CAPTURE_FILES = {
    "panorama": "panorama.jpg",
    "little_planet": "little_planet.jpg",
    "front": "view_front.jpg",
    "right": "view_right.jpg",
    "back": "view_back.jpg",
    "left": "view_left.jpg",
    "up": "view_up.jpg",
    "down": "view_down.jpg",
}
ALLOWED_FILE_NAMES = frozenset(CAPTURE_FILES.values())
_CAPTURE_ID = re.compile(r"^[0-9a-f]{32}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class CaptureStore:
    def __init__(self, root: Path):
        self.root = root
        self.captures: dict[str, dict[str, Any]] = {}
        self.load()

    def load(self) -> None:
        if not self.root.exists():
            return
        for path in self.root.glob("*/capture.json"):
            try:
                record = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            capture_id = record.get("capture_id")
            if not isinstance(capture_id, str) or not _CAPTURE_ID.fullmatch(capture_id):
                continue
            if record.get("status") in {"pending", "running"}:
                record["status"] = "failed"
                record["error"] = {
                    "code": "INTERRUPTED",
                    "message": "服务重启，拍摄任务中断",
                }
                record["updated_at"] = _now()
                self.save(record)
            self.captures[capture_id] = record

    def create(self, capture_id: str) -> dict[str, Any]:
        if not _CAPTURE_ID.fullmatch(capture_id):
            raise ValueError("无效 capture_id")
        created = _now()
        record: dict[str, Any] = {
            "capture_id": capture_id,
            "status": "pending",
            "step": "pending",
            "step_label": "等待拍摄",
            "created_at": created,
            "updated_at": created,
            "error": None,
            "camera": None,
            "candidates": {},
        }
        self.captures[capture_id] = record
        self.save(record)
        return record

    def save(self, record: dict[str, Any]) -> None:
        capture_id = record["capture_id"]
        if not _CAPTURE_ID.fullmatch(capture_id):
            raise ValueError("无效 capture_id")
        directory = self.root / capture_id
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "capture.json"
        temporary = directory / "capture.json.tmp"
        temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2))
        temporary.replace(path)
        self.captures[capture_id] = record

    def get(self, capture_id: str) -> dict[str, Any] | None:
        if not _CAPTURE_ID.fullmatch(capture_id):
            return None
        current = self.captures.get(capture_id)
        if current is not None:
            return current
        path = self.root / capture_id / "capture.json"
        if not path.is_file():
            return None
        try:
            record = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        self.captures[capture_id] = record
        return record

    def directory(self, capture_id: str) -> Path:
        if not _CAPTURE_ID.fullmatch(capture_id):
            raise ValueError("无效 capture_id")
        return self.root / capture_id

    def file_path(self, capture_id: str, name: str) -> Path | None:
        if name not in ALLOWED_FILE_NAMES or self.get(capture_id) is None:
            return None
        root = self.directory(capture_id).resolve()
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            return None
        return path

    def reference_images(
        self, capture_id: str, views: list[str]
    ) -> list[tuple[bytes, str]]:
        record = self.get(capture_id)
        if record is None:
            raise KeyError("CAPTURE_NOT_FOUND")
        if record.get("status") != "succeeded":
            raise RuntimeError("CAPTURE_NOT_READY")
        images: list[tuple[bytes, str]] = []
        for view in views:
            filename = CAPTURE_FILES.get(view)
            path = self.file_path(capture_id, filename or "")
            if path is None:
                raise FileNotFoundError(view)
            images.append((path.read_bytes(), ".jpg"))
        return images


class CameraService:
    def __init__(
        self,
        settings: Settings,
        store: CaptureStore,
        *,
        camera_factory: Callable[[], Any] | None = None,
        capture_runner: Callable[..., dict[str, Any]] = capture_bundle,
    ):
        self.settings = settings
        self.store = store
        self.camera_factory = camera_factory or (
            lambda: Insta360OSCClient(
                settings.insta360_base_url,
                timeout=settings.insta360_request_timeout,
            )
        )
        self.capture_runner = capture_runner

    def capture(self, capture_id: str) -> None:
        record = self.store.get(capture_id)
        if record is None:
            return
        record.update(
            status="running",
            step="starting",
            step_label="连接相机",
            error=None,
            updated_at=_now(),
        )
        self.store.save(record)

        def progress(step: str, label: str) -> None:
            record.update(step=step, step_label=label, updated_at=_now())
            self.store.save(record)

        try:
            result = self.capture_runner(
                self.store.directory(capture_id),
                camera_factory=self.camera_factory,
                capture_timeout=self.settings.insta360_capture_timeout,
                poll_interval=self.settings.insta360_poll_interval,
                view_size=self.settings.projection_view_size,
                view_fov=self.settings.projection_view_fov,
                planet_size=self.settings.projection_planet_size,
                planet_fov=self.settings.projection_planet_fov,
                ffmpeg_bin=self.settings.ffmpeg_bin,
                ffmpeg_timeout=self.settings.ffmpeg_timeout,
                progress=progress,
            )
            base = f"/api/v1/camera/captures/{capture_id}/files"
            record.update(
                status="succeeded",
                step="done",
                step_label="拍摄与投影完成",
                error=None,
                camera=result.get("camera"),
                candidates={
                    key: f"{base}/{filename}"
                    for key, filename in CAPTURE_FILES.items()
                },
                updated_at=_now(),
            )
        except Exception as exc:
            if isinstance(exc, FFmpegTimeoutError):
                code = "FFMPEG_TIMEOUT"
            elif isinstance(exc, OSCResponseError):
                normalized = re.sub(r"[^A-Za-z0-9]+", "_", exc.code).strip("_")
                code = f"CAMERA_{normalized.upper() or 'PROTOCOL_ERROR'}"
            elif isinstance(exc, OSCError):
                code = "CAMERA_OSC_ERROR"
            else:
                code = "CAMERA_CAPTURE_FAILED"
            record.update(
                status="failed",
                step="failed",
                step_label="拍摄失败",
                error={"code": str(code), "message": str(exc)},
                updated_at=_now(),
            )
        self.store.save(record)
