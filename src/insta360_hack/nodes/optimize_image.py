import time
from datetime import datetime, timezone

from insta360_hack.engine.context import RunContext
from insta360_hack.engine.errors import NodeError
from insta360_hack.nodes.references import load_reference_images
from insta360_hack.openrouter.client import OpenRouterError

_SUFFIX = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


class OptimizeImage:
    name = "optimize_image"

    async def execute(self, ctx: RunContext) -> None:
        prompt = (ctx.record["artifacts"].get("image_prompt") or "").strip()
        if not prompt:
            raise NodeError("INVALID_INPUT", "还没有剖面说明")
        started = time.time()
        ctx.record["artifacts"]["optimize_image_started_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        ctx.touch()
        try:
            raw, out_type = await ctx.images.generate(prompt=prompt, images=load_reference_images(ctx))
        except OpenRouterError as exc:
            ctx.record["artifacts"]["optimize_image_elapsed_seconds"] = max(0, int(time.time() - started))
            raise NodeError(exc.code, exc.message) from exc
        ctx.record["artifacts"]["optimize_image_elapsed_seconds"] = max(0, int(time.time() - started))
        out_suffix = _SUFFIX.get(out_type)
        if out_suffix is None:
            raise NodeError("IMAGE", f"优化参考图格式不支持: {out_type}")
        filename = f"optimized{out_suffix}"
        (ctx.run_dir() / filename).write_bytes(raw)
        file_path = f"/api/v1/runs/{ctx.record['run_id']}/files/{filename}"
        ctx.record["artifacts"]["optimized_name"] = filename
        ctx.record["artifacts"]["optimized_file"] = file_path
        ctx.record["outputs"]["optimized_image"] = file_path
        ctx.touch()
