from __future__ import annotations

import argparse
import json
from pathlib import Path

from insta360_hack.insta360.client import OSCError
from insta360_hack.insta360.projections import (
    MAIN_VIEWS,
    ViewSpec,
    export_projection_bundle,
)

__all__ = ["MAIN_VIEWS", "ViewSpec", "export_projection_bundle"]


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
    parser.add_argument("--ffmpeg-timeout", type=float, default=120)
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
            ffmpeg_timeout=args.ffmpeg_timeout,
        )
    except OSCError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
