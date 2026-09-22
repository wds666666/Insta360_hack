from pathlib import Path
from urllib.parse import urlparse

import httpx

from insta360_hack.engine.context import RunContext
from insta360_hack.engine.errors import NodeError
from insta360_hack.nodes.references import SUFFIXES


def suffix_from_name(name: str) -> str:
    suffix = Path(name).suffix.lower()
    if suffix == ".jpeg":
        return ".jpg"
    if suffix in SUFFIXES:
        return suffix
    return ""


class SaveImage:
    name = "save_image"

    async def execute(self, ctx: RunContext) -> None:
        directory = ctx.run_dir()
        directory.mkdir(parents=True, exist_ok=True)
        names: list[str] = []
        if ctx.reference_images:
            single = len(ctx.reference_images) == 1
            for index, (raw, suffix) in enumerate(ctx.reference_images, start=1):
                if suffix not in SUFFIXES:
                    raise NodeError("INVALID_INPUT", "参考图只支持 jpg、png、webp")
                filename = f"reference{suffix}" if single else f"reference-{index}{suffix}"
                (directory / filename).write_bytes(raw)
                names.append(filename)
            ctx.reference_images = []
        else:
            url = ctx.record["inputs"]["image_url"]
            suffix = suffix_from_name(Path(urlparse(url).path).name) or ".jpg"
            filename = f"reference{suffix}"
            await _download(url, directory / filename)
            names.append(filename)
        run_id = ctx.record["run_id"]
        paths = [f"/api/v1/runs/{run_id}/files/{name}" for name in names]
        ctx.record["artifacts"]["reference_names"] = names
        ctx.record["artifacts"]["reference_name"] = names[0]
        ctx.record["artifacts"]["reference_files"] = paths
        ctx.record["artifacts"]["reference_file"] = paths[0]
        ctx.record["outputs"]["reference_image"] = paths[0]
        ctx.record["outputs"]["reference_images"] = paths
        ctx.touch()


async def _download(url: str, dest: Path) -> None:
    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as http:
            response = await http.get(url)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise NodeError("SAVE_IMAGE", f"下载参考图失败: {exc}") from exc
    dest.write_bytes(response.content)
