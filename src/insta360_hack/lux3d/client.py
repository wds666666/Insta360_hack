import asyncio
import hashlib
import math
from pathlib import Path

import httpx

from insta360_hack.config import Settings
from insta360_hack.lux3d.models import Lux3DTask, output_slots


class Lux3DError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class Lux3DClient:
    def __init__(self, http: httpx.AsyncClient, settings: Settings):
        self.http = http
        self.settings = settings

    def _gateway(self, path: str) -> str:
        return f"{self.settings.base_url}{self.settings.path_prefix}{path}"

    def _headers(self) -> dict[str, str]:
        if not self.settings.api_key:
            raise Lux3DError("CONFIG", "缺少 LUX3D_API_KEY")
        return {"Authorization": self.settings.api_key}

    async def upload_file(self, path: Path) -> str:
        token = await self._upload_token()
        payload = path.read_bytes()
        digest = hashlib.md5(payload).hexdigest()
        domain = str(token["globalDomain"]).rstrip("/")
        ous_headers = {"ous-token-v2": token["ousToken"]}
        block_size = int(token["blockSize"])
        if len(payload) <= block_size:
            await self._single_upload(domain, ous_headers, digest, path.name, payload)
        else:
            await self._block_upload(domain, ous_headers, digest, path.name, payload, block_size)
        return await self._wait_upload_url(domain, ous_headers)

    async def create_img_to_3d(self, *, image_url: str) -> int:
        data = await self._request(
            "POST",
            self._gateway("/lux3d/v1/generate/img-to-3d/task/create"),
            headers={**self._headers(), "Content-Type": "application/json"},
            json={"img": image_url, "version": "G1", "outputFormat": ["glb"]},
        )
        return int(self._unwrap(data))

    async def create_stl_export(self, *, model_url: str) -> int:
        data = await self._request(
            "POST",
            self._gateway("/lux3d/v1/multi-format-export/task/create"),
            headers={**self._headers(), "Content-Type": "application/json"},
            json={"modelUrl": model_url, "outputFormat": ["stl"]},
        )
        return int(self._unwrap(data))

    async def get_task(self, task_id: int) -> Lux3DTask:
        last: Lux3DError | None = None
        for attempt in range(3):
            try:
                return await self._get_task_once(task_id)
            except Lux3DError as exc:
                if exc.code not in {"HTTP", "NETWORK"}:
                    raise
                last = exc
                if attempt < 2:
                    await asyncio.sleep(1)
        assert last is not None
        raise last

    async def download(self, url: str, dest: Path) -> None:
        last: Exception | None = None
        for attempt in range(3):
            partial = dest.with_suffix(dest.suffix + ".part")
            try:
                async with self.http.stream(
                    "GET", url, timeout=300, headers={"User-Agent": "insta360-hack"}
                ) as response:
                    response.raise_for_status()
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with partial.open("wb") as handle:
                        async for chunk in response.aiter_bytes():
                            handle.write(chunk)
                partial.replace(dest)
                return
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text[:200].replace("\n", " ")
                raise Lux3DError(
                    "DOWNLOAD", f"下载模型失败: HTTP {exc.response.status_code} {detail}"
                ) from exc
            except httpx.HTTPError as exc:
                last = exc
                partial.unlink(missing_ok=True)
                if attempt < 2:
                    await asyncio.sleep(2)
        raise Lux3DError("DOWNLOAD", f"下载模型失败: {type(last).__name__}: {last}") from last

    async def _get_task_once(self, task_id: int) -> Lux3DTask:
        data = await self._request(
            "GET",
            self._gateway("/lux3d/v1/generate/task/get"),
            headers=self._headers(),
            params={"taskid": task_id},
        )
        body = self._unwrap(data)
        if not isinstance(body, dict):
            raise Lux3DError("BAD_OUTPUT", "查询结果格式不对")
        outputs = output_slots(body.get("outputs"))
        return Lux3DTask(status=int(body["status"]), outputs=outputs)

    async def _upload_token(self) -> dict:
        try:
            response = await self.http.get(self._gateway("/asset/v1/token"), headers=self._headers())
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise Lux3DError("UPLOAD", f"获取上传凭证失败: {exc}") from exc
        payload = response.json()
        if isinstance(payload, dict) and "ousToken" not in payload and "c" in payload:
            if str(payload.get("c")) != "0":
                raise Lux3DError(str(payload.get("c")), str(payload.get("m") or "获取上传凭证失败"))
            inner = payload.get("d")
            payload = inner if isinstance(inner, dict) else {}
        if isinstance(payload, dict):
            if "ousToken" not in payload and "ous_token" in payload:
                payload["ousToken"] = payload["ous_token"]
            if "globalDomain" not in payload and "global_domain" in payload:
                payload["globalDomain"] = payload["global_domain"]
            if "blockSize" not in payload and "block_size" in payload:
                payload["blockSize"] = payload["block_size"]
        if not isinstance(payload, dict) or "ousToken" not in payload or "globalDomain" not in payload:
            keys = list(payload) if isinstance(payload, dict) else type(payload).__name__
            raise Lux3DError("UPLOAD", f"上传凭证格式不对，字段为 {keys}")
        return payload

    async def _single_upload(
        self, domain: str, headers: dict[str, str], digest: str, filename: str, payload: bytes
    ) -> None:
        data = await self._request(
            "POST",
            f"{domain}/ous/api/v2/single/upload",
            headers=headers,
            files={
                "md5": (None, digest),
                "file": (filename, payload, "application/octet-stream"),
            },
        )
        self._unwrap(data)

    async def _block_upload(
        self,
        domain: str,
        headers: dict[str, str],
        digest: str,
        filename: str,
        payload: bytes,
        block_size: int,
    ) -> None:
        blocks = math.ceil(len(payload) / block_size)
        data = await self._request(
            "POST",
            f"{domain}/ous/api/v2/block/upload/init",
            headers=headers,
            params={"md5": digest, "blocks": blocks, "size": len(payload), "name": filename},
        )
        body = self._unwrap(data) or {}
        if body.get("deduplicated"):
            return
        for index in range(blocks):
            start = index * block_size
            chunk = payload[start : start + block_size]
            part = await self._request(
                "POST",
                f"{domain}/ous/api/v2/block/upload/part",
                headers=headers,
                data={"block": str(index + 1)},
                files={"file": (filename, chunk, "application/octet-stream")},
            )
            self._unwrap(part)

    async def _wait_upload_url(self, domain: str, headers: dict[str, str]) -> str:
        deadline = asyncio.get_running_loop().time() + 60
        while True:
            data = await self._request("GET", f"{domain}/ous/api/v2/upload/status", headers=headers)
            body = self._unwrap(data) or {}
            status = int(body.get("status", -1))
            if status == 5:
                url = body.get("url")
                if not url:
                    raise Lux3DError("UPLOAD", "上传成功但没有返回 url")
                return str(url)
            if status in {6, 8}:
                raise Lux3DError("UPLOAD_FAILED", str(body.get("errorMsg") or "参考图上传失败"))
            if asyncio.get_running_loop().time() > deadline:
                raise Lux3DError("UPLOAD_TIMEOUT", "参考图上传超时")
            await asyncio.sleep(0.3)

    async def _request(self, method: str, url: str, **kwargs) -> dict:
        try:
            response = await self.http.request(method, url, **kwargs)
            response.raise_for_status()
        except httpx.TransportError as exc:
            raise Lux3DError("NETWORK", f"{type(exc).__name__}: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            raise Lux3DError("HTTP", f"{exc.response.status_code} {exc.response.text[:300]}") from exc
        return response.json()

    @staticmethod
    def _unwrap(payload: dict):
        code = str(payload.get("c"))
        if code != "0":
            raise Lux3DError(code, str(payload.get("m") or "Lux3D 调用失败"))
        return payload.get("d")
