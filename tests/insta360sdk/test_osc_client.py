from __future__ import annotations

import io
import json
import shutil
from pathlib import Path

import httpx
import pytest
from PIL import Image

from .capture_x5 import _check_camera_state, _validate_erp_jpeg
from .client import OSCError, OSCResponseError, Insta360OSCClient
from .projections import MAIN_VIEWS, export_projection_bundle


def _jpeg(size: tuple[int, int] = (8, 4)) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", size, (20, 40, 60)).save(output, format="JPEG")
    return output.getvalue()


def test_minimal_capture_flow(tmp_path):
    requests: list[httpx.Request] = []
    photo = _jpeg()

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["X-XSRF-Protected"] == "1"

        if request.url.path == "/osc/info":
            return httpx.Response(
                200,
                json={"manufacturer": "Arashi Vision", "model": "Insta360 X5"},
            )
        if request.url.path == "/osc/state":
            return httpx.Response(
                200,
                json={"state": {"_cardState": "pass", "batteryLevel": 0.8}},
            )
        if request.url.path == "/osc/commands/status":
            assert json.loads(request.content) == {"id": "capture-1"}
            return httpx.Response(
                200,
                json={
                    "name": "camera.takePicture",
                    "state": "done",
                    "results": {"fileUrl": "http://192.168.42.1/photo.jpg"},
                },
            )
        if request.url.path == "/photo.jpg":
            return httpx.Response(200, content=photo, headers={"Content-Type": "image/jpeg"})

        payload = json.loads(request.content)
        if payload["name"] == "camera.getOptions":
            return httpx.Response(
                200,
                json={
                    "name": "camera.getOptions",
                    "state": "done",
                    "results": {
                        "options": {
                            "photoStitchingSupport": ["none", "ondevice"],
                            "photoStitching": "none",
                        }
                    },
                },
            )
        if payload["name"] == "camera.setOptions":
            assert payload["parameters"]["options"] == {
                "captureMode": "image",
                "photoStitching": "ondevice",
            }
            return httpx.Response(
                200,
                json={"name": "camera.setOptions", "state": "done"},
            )
        if payload["name"] == "camera.takePicture":
            return httpx.Response(
                200,
                json={
                    "name": "camera.takePicture",
                    "state": "inProgress",
                    "id": "capture-1",
                },
            )
        raise AssertionError(f"未预期请求: {request.method} {request.url}")

    destination = tmp_path / "capture.jpg"
    with Insta360OSCClient(
        transport=httpx.MockTransport(handler),
        timeout=1,
    ) as camera:
        assert camera.info()["model"] == "Insta360 X5"
        assert camera.state()["state"]["_cardState"] == "pass"
        options = camera.get_options("photoStitchingSupport", "photoStitching")
        assert "ondevice" in options["photoStitchingSupport"]
        camera.set_options(captureMode="image", photoStitching="ondevice")
        completed = camera.wait_for_command(
            camera.take_picture(),
            timeout=1,
            poll_interval=0,
        )
        url = camera.picture_url(completed)
        camera.download(url, destination)

    assert destination.read_bytes() == photo
    assert any(request.url.path == "/osc/commands/status" for request in requests)


def test_protocol_error_exposes_camera_code():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "name": "camera.takePicture",
                "state": "error",
                "error": {
                    "code": "unactivated",
                    "message": "Please activate your camera in insta360 official app.",
                },
            },
        )

    with Insta360OSCClient(transport=httpx.MockTransport(handler)) as camera:
        with pytest.raises(OSCResponseError, match="unactivated") as caught:
            camera.take_picture()
    assert caught.value.code == "unactivated"


def test_missing_ondevice_option_is_not_silently_accepted():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "name": "camera.getOptions",
                "state": "done",
                "results": {
                    "options": {
                        "photoStitchingSupport": ["none"],
                        "photoStitching": "none",
                    }
                },
            },
        )

    with Insta360OSCClient(transport=httpx.MockTransport(handler)) as camera:
        options = camera.get_options("photoStitchingSupport", "photoStitching")
    assert "ondevice" not in options["photoStitchingSupport"]


@pytest.mark.parametrize("card_state", ["noCard", "noSpace", "invalidFormat", "writeProtect"])
def test_bad_card_state_is_rejected(card_state):
    with pytest.raises(OSCError):
        _check_camera_state({"state": {"_cardState": card_state}})


def test_erp_jpeg_validation(tmp_path):
    panorama = tmp_path / "panorama.jpg"
    panorama.write_bytes(_jpeg((16, 8)))
    assert _validate_erp_jpeg(panorama) == (16, 8, "JPEG")

    flat_photo = tmp_path / "flat.jpg"
    flat_photo.write_bytes(_jpeg((16, 9)))
    with pytest.raises(OSCError, match="ERP"):
        _validate_erp_jpeg(flat_photo)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="需要 FFmpeg v360")
def test_export_little_planet_and_main_views(tmp_path):
    panorama = tmp_path / "panorama.jpg"
    image = Image.new("RGB", (512, 256))
    pixels = image.load()
    for y in range(image.height):
        for x in range(image.width):
            pixels[x, y] = (x % 256, y, (x + y) % 256)
    image.save(panorama, format="JPEG")

    result = export_projection_bundle(
        panorama,
        view_size=256,
        planet_size=256,
    )

    assert Path(result["littlePlanet"]["path"]).is_file()
    assert set(result["views"]) == {view.name for view in MAIN_VIEWS}
    for view in result["views"].values():
        assert Path(view["path"]).is_file()
        assert (view["width"], view["height"]) == (256, 256)
