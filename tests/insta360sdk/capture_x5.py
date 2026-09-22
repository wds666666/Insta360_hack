from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image

try:
    from .client import DEFAULT_BASE_URL, OSCError, Insta360OSCClient
    from .projections import export_projection_bundle
except ImportError:
    from client import DEFAULT_BASE_URL, OSCError, Insta360OSCClient
    from projections import export_projection_bundle


CARD_ERRORS = {
    "noCard": "相机没有存储卡",
    "noSpace": "相机存储卡空间不足",
    "invalidFormat": "相机存储卡格式不正确",
    "writeProtect": "相机存储卡处于写保护状态",
    "otherError": "相机存储卡状态异常",
}


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _check_camera_state(response: dict[str, Any]) -> dict[str, Any]:
    state = response.get("state")
    if not isinstance(state, dict):
        raise OSCError("/osc/state 响应缺少 state")
    card_state = state.get("_cardState")
    if card_state != "pass":
        detail = CARD_ERRORS.get(str(card_state), f"未知状态 {card_state!r}")
        raise OSCError(detail)
    return state


def _validate_erp_jpeg(path: Path) -> tuple[int, int, str]:
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            width, height = image.size
            image_format = image.format or "unknown"
    except (OSError, ValueError) as exc:
        raise OSCError(f"下载文件不是可解码图片: {exc}") from exc

    if image_format.upper() != "JPEG":
        raise OSCError(f"期望 JPEG，实际格式为 {image_format}")
    if width <= 0 or height <= 0:
        raise OSCError(f"图片尺寸无效: {width}x{height}")
    ratio = width / height
    if abs(ratio - 2.0) > 0.05:
        raise OSCError(
            f"图片尺寸 {width}x{height} 不是接近 2:1 的 ERP 全景图，"
            "请确认机内拼接是否生效"
        )
    return width, height, image_format


def capture(args: argparse.Namespace) -> dict[str, Any]:
    output = args.output
    with Insta360OSCClient(args.base_url, timeout=args.request_timeout) as camera:
        _log("1/7 获取相机信息")
        info = camera.info()

        _log("2/7 检查相机和存储卡状态")
        camera_state = _check_camera_state(camera.state())

        _log("3/7 查询机内照片拼接能力")
        options = camera.get_options("photoStitchingSupport", "photoStitching")
        stitching_support = options.get("photoStitchingSupport")
        if not isinstance(stitching_support, list) or "ondevice" not in stitching_support:
            raise OSCError(
                "当前相机/固件未报告 ondevice 机内拼接能力；"
                "为避免下载双鱼眼原图，测试已停止"
            )

        _log("4/7 设置照片模式和机内拼接")
        camera.set_options(captureMode="image", photoStitching="ondevice")

        _log("5/7 拍照并等待相机处理完成")
        command = camera.take_picture()
        completed = camera.wait_for_command(
            command,
            timeout=args.capture_timeout,
            poll_interval=args.poll_interval,
        )
        file_url = camera.picture_url(completed)

        _log("6/7 下载并校验 ERP 全景 JPEG")
        camera.download(file_url, output)
        width, height, image_format = _validate_erp_jpeg(output)

    _log("7/7 导出小行星图和六个主要视角")
    projections = export_projection_bundle(
        output,
        output_dir=args.views_output_dir,
        view_size=args.view_size,
        view_fov=args.view_fov,
        planet_size=args.planet_size,
        planet_fov=args.planet_fov,
        ffmpeg_bin=args.ffmpeg_bin,
    )

    return {
        "ok": True,
        "camera": {
            "manufacturer": info.get("manufacturer"),
            "model": info.get("model"),
            "serialNumber": info.get("serialNumber"),
            "firmwareVersion": info.get("firmwareVersion"),
            "batteryLevel": camera_state.get("batteryLevel"),
        },
        "stitching": {
            "supported": stitching_support,
            "before": options.get("photoStitching"),
            "used": "ondevice",
        },
        "image": {
            "path": str(output.resolve()),
            "sourceUrl": file_url,
            "format": image_format,
            "width": width,
            "height": height,
            "bytes": output.stat().st_size,
        },
        "projections": projections,
    }


def parse_args() -> argparse.Namespace:
    default_name = datetime.now().strftime("x5_%Y%m%d_%H%M%S.jpg")
    parser = argparse.ArgumentParser(
        description="通过 OSC 控制 Insta360 X5 拍摄并下载机内拼接全景图"
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent / "output" / default_name,
    )
    parser.add_argument("--request-timeout", type=float, default=15.0)
    parser.add_argument("--capture-timeout", type=float, default=120.0)
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--views-output-dir", type=Path)
    parser.add_argument("--view-size", type=int, default=1600)
    parser.add_argument("--view-fov", type=int, default=90)
    parser.add_argument("--planet-size", type=int, default=1600)
    parser.add_argument("--planet-fov", type=int, default=300)
    parser.add_argument("--ffmpeg-bin", default="ffmpeg")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = capture(args)
    except OSCError as exc:
        print(
            json.dumps(
                {"ok": False, "error": str(exc)},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
