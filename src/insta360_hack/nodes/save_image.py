from pathlib import Path
from urllib.parse import urlparse

import httpx

from insta360_hack.engine.context import RunContext
from insta360_hack.engine.errors import NodeError

_SUFFIXES = {".jpg", ".png", ".webp"}


def suffix_from_name(name: str) -> str:
    suffix = Path(name).suffix.lower()
    if suffix == ".jpeg":
        return ".jpg"
    if suffix in _SUFFIXES:
        return suffix
    return ""


class SaveImage:
    name = "save_image"

    async def execute(self, ctx: RunContext) -> None:
        directory = ctx.run_dir()
        directory.mkdir(parents=True, exist_ok=True)
        if ctx.image_bytes is not None:
            suffix = ctx.image_suffix or ""
            if suffix not in _SUFFIXES:
                raise NodeError("INVALID_INPUT", "参考图只支持 jpg、png、webp")
            filename = f"reference{suffix}"
            (directory / filename).write_bytes(ctx.image_bytes)
            ctx.image_bytes = None
        else:
            url = ctx.record["inputs"]["image_url"]
            suffix = suffix_from_name(Path(urlparse(url).path).name) or ".jpg"
            filename = f"reference{suffix}"
            await _download(url, directory / filename)
        ctx.record["artifacts"]["reference_name"] = filename
        ctx.record["artifacts"]["reference_file"] = f"/api/v1/runs/{ctx.record['run_id']}/files/{filename}"


async def _download(url: str, dest: Path) -> None:
    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as http:
            response = await http.get(url)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise NodeError("SAVE_IMAGE", f"下载参考图失败: {exc}") from exc
    dest.write_bytes(response.content)
