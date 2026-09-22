from insta360_hack.engine.context import RunContext


class UploadImage:
    name = "upload_image"

    async def execute(self, ctx: RunContext) -> None:
        image_url = ctx.record["inputs"].get("image_url")
        if image_url:
            ctx.record["artifacts"]["image_url"] = image_url
            return
        filename = ctx.record["artifacts"]["reference_name"]
        path = ctx.run_dir() / filename
        ctx.record["artifacts"]["image_url"] = await ctx.client.upload_file(path)
