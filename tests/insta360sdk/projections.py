from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from PIL import Image

try:
    from .client import OSCError
except ImportError:
    from client import OSCError


@dataclass(frozen=True)
class ViewSpec:
    name: str
    yaw: int
    pitch: int


MAIN_VIEWS = (
    ViewSpec("front", 0, 0),
    ViewSpec("right", 90, 0),
    ViewSpec("back", 180, 0),
    ViewSpec("left", -90, 0),
    ViewSpec("up", 0, 90),
    ViewSpec("down", 0, -90),
)


def _check_square_jpeg(path: Path, expected_size: int) -> dict[str, Any]:
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            width, height = image.size
            image_format = image.format or "unknown"
    except (OSError, ValueError) as exc:
        raise OSCError(f"投影结果无法解码: {path}: {exc}") from exc

    if image_format.upper() != "JPEG":
        raise OSCError(f"投影结果不是 JPEG: {path}")
    if (width, height) != (expected_size, expected_size):
        raise OSCError(
            f"投影结果尺寸错误: {path}: {width}x{height}，"
            f"期望 {expected_size}x{expected_size}"
        )
    return {
        "path": str(path.resolve()),
        "format": image_format,
        "width": width,
        "height": height,
        "bytes": path.stat().st_size,
    }


def _run_v360(
    source: Path,
    destination: Path,
    *,
    projection: str,
    size: int,
    yaw: int,
    pitch: int,
    fov: int,
    ffmpeg_bin: str,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    video_filter = (
        f"v360=input=equirect:output={projection}:"
        f"yaw={yaw}:pitch={pitch}:roll=0:"
        f"h_fov={fov}:v_fov={fov}:"
        f"w={size}:h={size}:interp=lanczos"
    )
    command = [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-vf",
        video_filter,
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(destination),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        destination.unlink(missing_ok=True)
        detail = completed.stderr.strip() or f"退出码 {completed.returncode}"
        raise OSCError(f"FFmpeg 生成 {destination.name} 失败: {detail}")


def export_projection_bundle(
    panorama: Path,
    *,
    output_dir: Path | None = None,
    view_size: int = 1600,
    view_fov: int = 90,
    planet_size: int = 1600,
    planet_fov: int = 300,
    ffmpeg_bin: str = "ffmpeg",
) -> dict[str, Any]:
    if not panorama.is_file():
        raise OSCError(f"全景原图不存在: {panorama}")
    if not 256 <= view_size <= 8192:
        raise OSCError("view_size 必须在 256 到 8192 之间")
    if not 30 <= view_fov <= 150:
        raise OSCError("view_fov 必须在 30 到 150 度之间")
    if not 256 <= planet_size <= 8192:
        raise OSCError("planet_size 必须在 256 到 8192 之间")
    if not 180 <= planet_fov <= 360:
        raise OSCError("planet_fov 必须在 180 到 360 度之间")

    resolved_ffmpeg = shutil.which(ffmpeg_bin)
    if resolved_ffmpeg is None:
        raise OSCError(
            "未找到 FFmpeg；macOS 可执行 `brew install ffmpeg`，"
            "并确认该版本包含 v360 filter"
        )

    destination_dir = output_dir or panorama.parent / f"{panorama.stem}_views"
    destination_dir.mkdir(parents=True, exist_ok=True)

    little_planet = destination_dir / "little_planet.jpg"
    _run_v360(
        panorama,
        little_planet,
        projection="sg",
        size=planet_size,
        yaw=0,
        pitch=-90,
        fov=planet_fov,
        ffmpeg_bin=resolved_ffmpeg,
    )
    planet_result = _check_square_jpeg(little_planet, planet_size)
    planet_result.update({"projection": "stereographic", "pitch": -90})

    views: dict[str, dict[str, Any]] = {}
    for spec in MAIN_VIEWS:
        destination = destination_dir / f"view_{spec.name}.jpg"
        _run_v360(
            panorama,
            destination,
            projection="flat",
            size=view_size,
            yaw=spec.yaw,
            pitch=spec.pitch,
            fov=view_fov,
            ffmpeg_bin=resolved_ffmpeg,
        )
        result = _check_square_jpeg(destination, view_size)
        result.update({**asdict(spec), "fov": view_fov})
        views[spec.name] = result

    return {
        "outputDir": str(destination_dir.resolve()),
        "littlePlanet": planet_result,
        "views": views,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="从 ERP 全景 JPEG 导出小行星图和六个主要环视视角"
    )
    parser.add_argument("panorama", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--view-size", type=int, default=1600)
    parser.add_argument("--view-fov", type=int, default=90)
    parser.add_argument("--planet-size", type=int, default=1600)
    parser.add_argument("--planet-fov", type=int, default=300)
    parser.add_argument("--ffmpeg-bin", default="ffmpeg")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = export_projection_bundle(
            args.panorama,
            output_dir=args.output_dir,
            view_size=args.view_size,
            view_fov=args.view_fov,
            planet_size=args.planet_size,
            planet_fov=args.planet_fov,
            ffmpeg_bin=args.ffmpeg_bin,
        )
    except OSCError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1

    print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
