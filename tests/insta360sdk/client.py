from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import httpx


DEFAULT_BASE_URL = "http://192.168.42.1"


class OSCError(RuntimeError):
    """Base exception for OSC communication failures."""


class OSCResponseError(OSCError):
    """An OSC endpoint returned a protocol-level error."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class Insta360OSCClient:
    """Minimal synchronous OSC client for taking an on-device stitched photo."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            transport=transport,
            trust_env=False,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json;charset=utf-8",
                "X-XSRF-Protected": "1",
            },
        )

    def __enter__(self) -> Insta360OSCClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _json_request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            response = self._client.request(method, path, json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OSCError(f"{method} {path} 请求失败: {exc}") from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise OSCError(f"{method} {path} 返回了无效 JSON") from exc
        if not isinstance(body, dict):
            raise OSCError(f"{method} {path} 返回内容不是 JSON 对象")

        error = body.get("error")
        if isinstance(error, dict):
            raise OSCResponseError(
                str(error.get("code", "unknownError")),
                str(error.get("message", "相机返回未知错误")),
            )
        return body

    def info(self) -> dict[str, Any]:
        return self._json_request("GET", "/osc/info")

    def state(self) -> dict[str, Any]:
        return self._json_request("POST", "/osc/state", payload={})

    def execute(
        self,
        name: str,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": name}
        if parameters is not None:
            payload["parameters"] = parameters
        return self._json_request("POST", "/osc/commands/execute", payload=payload)

    def command_status(self, command_id: str) -> dict[str, Any]:
        return self._json_request(
            "POST",
            "/osc/commands/status",
            payload={"id": command_id},
        )

    def get_options(self, *option_names: str) -> dict[str, Any]:
        response = self.execute(
            "camera.getOptions",
            {"optionNames": list(option_names)},
        )
        results = response.get("results")
        options = results.get("options") if isinstance(results, dict) else None
        if not isinstance(options, dict):
            raise OSCError("camera.getOptions 响应缺少 results.options")
        return options

    def set_options(self, **options: Any) -> None:
        response = self.execute("camera.setOptions", {"options": options})
        if response.get("state") != "done":
            raise OSCError(f"camera.setOptions 未完成: {response}")

    def take_picture(self) -> dict[str, Any]:
        return self.execute("camera.takePicture")

    def wait_for_command(
        self,
        initial_response: dict[str, Any],
        *,
        timeout: float = 90.0,
        poll_interval: float = 1.0,
    ) -> dict[str, Any]:
        if initial_response.get("state") == "done":
            return initial_response

        command_id = initial_response.get("id")
        if not isinstance(command_id, str) or not command_id:
            raise OSCError("拍照响应缺少命令 id")

        deadline = time.monotonic() + timeout
        response = initial_response
        while response.get("state") == "inProgress":
            if time.monotonic() >= deadline:
                raise OSCError(f"等待拍照命令 {command_id} 超时（{timeout:g} 秒）")
            time.sleep(poll_interval)
            response = self.command_status(command_id)

        if response.get("state") != "done":
            raise OSCError(f"拍照命令 {command_id} 未成功完成: {response}")
        return response

    @staticmethod
    def picture_url(command_result: dict[str, Any]) -> str:
        results = command_result.get("results")
        file_url = results.get("fileUrl") if isinstance(results, dict) else None
        if not isinstance(file_url, str) or not file_url:
            raise OSCError("拍照完成响应缺少 results.fileUrl")
        return file_url

    def download(self, url: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._client.stream("GET", url) as response:
                response.raise_for_status()
                with destination.open("wb") as output:
                    for chunk in response.iter_bytes():
                        output.write(chunk)
        except (httpx.HTTPError, OSError) as exc:
            destination.unlink(missing_ok=True)
            raise OSCError(f"下载照片失败: {exc}") from exc
        return destination
