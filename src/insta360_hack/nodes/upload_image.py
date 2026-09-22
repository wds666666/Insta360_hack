from insta360_hack.engine.context import RunContext
from insta360_hack.engine.errors import NodeError


class UploadImage:
    name = "upload_image"

    async def execute(self, ctx: RunContext) -> None:
        filename = ctx.record["artifacts"].get("optimized_name")
        if not filename:
            raise NodeError("INVALID_INPUT", "缺少优化后的参考图")
        path = ctx.run_dir() / filename
        ctx.record["artifacts"]["image_url"] = await ctx.client.upload_file(path)
