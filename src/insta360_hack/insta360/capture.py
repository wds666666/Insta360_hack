from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, ContextManager

from PIL import Image

from insta360_hack.insta360.client import Insta360OSCClient, OSCError
from insta360_hack.insta360.projections import export_projection_bundle


CARD_ERRORS = {
    "noCard": "相机没有存储卡",
    "noSpace": "相机存储卡空间不足",
    "invalidFormat": "相机存储卡格式不正确",
    "writeProtect": "相机存储卡处于写保护状态",
    "otherError": "相机存储卡状态异常",
}
Progress = Callable[[str, str], None]
CameraFactory = Callable[[], ContextManager[Insta360OSCClient]]


def check_camera_state(response: dict[str, Any]) -> dict[str, Any]:
    state = response.get("state")
    if not isinstance(state, dict):
        raise OSCError("/osc/state 响应缺少 state")
    card_state = state.get("_cardState")
    if card_state != "pass":
        detail = CARD_ERRORS.get(str(card_state), f"未知状态 {card_state!r}")
        raise OSCError(detail)
    return state


def validate_erp_jpeg(path: Path) -> tuple[int, int, str]:
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
    if abs(width / height - 2.0) > 0.05:
        raise OSCError(
            f"图片尺寸 {width}x{height} 不是接近 2:1 的 ERP 全景图，"
            "请确认机内拼接是否生效"
        )
    return width, height, image_format


def capture_bundle(
    output_dir: Path,
    *,
    camera_factory: CameraFactory,
    capture_timeout: float,
    poll_interval: float,
    view_size: int,
    view_fov: int,
    planet_size: int,
    planet_fov: int,
    ffmpeg_bin: str,
    ffmpeg_timeout: float,
    progress: Progress | None = None,
) -> dict[str, Any]:
    notify = progress or (lambda _step, _label: None)
    output_dir.mkdir(parents=True, exist_ok=True)
    panorama = output_dir / "panorama.jpg"

    with camera_factory() as camera:
        notify("camera_info", "读取相机信息")
        info = camera.info()
        notify("camera_state", "检查相机与存储卡")
        camera_state = check_camera_state(camera.state())
        notify("configure", "启用机内全景拼接")
        options = camera.get_options("photoStitchingSupport", "photoStitching")
        stitching_support = options.get("photoStitchingSupport")
        if not isinstance(stitching_support, list) or "ondevice" not in stitching_support:
            raise OSCError("当前相机或固件不支持 ondevice 机内拼接")
        camera.set_options(captureMode="image", photoStitching="ondevice")
        notify("capture", "拍照并等待相机处理")
        completed = camera.wait_for_command(
            camera.take_picture(),
            timeout=capture_timeout,
            poll_interval=poll_interval,
        )
        file_url = camera.picture_url(completed)
        notify("download", "下载并校验全景图")
        camera.download(file_url, panorama)
        width, height, image_format = validate_erp_jpeg(panorama)

    notify("projections", "生成小行星与六向视图")
    projections = export_projection_bundle(
        panorama,
        output_dir=output_dir,
        view_size=view_size,
        view_fov=view_fov,
        planet_size=planet_size,
        planet_fov=planet_fov,
        ffmpeg_bin=ffmpeg_bin,
        ffmpeg_timeout=ffmpeg_timeout,
    )
    return {
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
            "sourceUrl": file_url,
            "format": image_format,
            "width": width,
            "height": height,
            "bytes": panorama.stat().st_size,
        },
        "projections": projections,
    }
