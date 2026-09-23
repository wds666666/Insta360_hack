from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from insta360_hack.insta360.capture import (
    capture_bundle,
    check_camera_state,
    validate_erp_jpeg,
)
from insta360_hack.insta360.client import (
    DEFAULT_BASE_URL,
    Insta360OSCClient,
    OSCError,
)

_check_camera_state = check_camera_state
_validate_erp_jpeg = validate_erp_jpeg


def parse_args() -> argparse.Namespace:
    default_name = datetime.now().strftime("x5_%Y%m%d_%H%M%S.jpg")
    parser = argparse.ArgumentParser(
        description="通过 OSC 控制 Insta360 X5 拍摄并导出全景图片包"
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent / "output" / default_name,
    )
    parser.add_argument("--views-output-dir", type=Path)
    parser.add_argument("--request-timeout", type=float, default=15)
    parser.add_argument("--capture-timeout", type=float, default=120)
    parser.add_argument("--poll-interval", type=float, default=1)
    parser.add_argument("--view-size", type=int, default=1600)
    parser.add_argument("--view-fov", type=int, default=90)
    parser.add_argument("--planet-size", type=int, default=1600)
    parser.add_argument("--planet-fov", type=int, default=300)
    parser.add_argument("--ffmpeg-bin", default="ffmpeg")
    parser.add_argument("--ffmpeg-timeout", type=float, default=120)
    return parser.parse_args()


def capture(args: argparse.Namespace) -> dict:
    output_dir = args.views_output_dir or (
        args.output.parent / f"{args.output.stem}_views"
    )
    result = capture_bundle(
        output_dir,
        camera_factory=lambda: Insta360OSCClient(
            args.base_url, timeout=args.request_timeout
        ),
        capture_timeout=args.capture_timeout,
        poll_interval=args.poll_interval,
        view_size=args.view_size,
        view_fov=args.view_fov,
        planet_size=args.planet_size,
        planet_fov=args.planet_fov,
        ffmpeg_bin=args.ffmpeg_bin,
        ffmpeg_timeout=args.ffmpeg_timeout,
        progress=lambda _step, label: print(label, file=sys.stderr, flush=True),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    (output_dir / "panorama.jpg").replace(args.output)
    result["image"]["path"] = str(args.output.resolve())
    return {"ok": True, **result}


def main() -> int:
    try:
        result = capture(parse_args())
    except OSCError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
