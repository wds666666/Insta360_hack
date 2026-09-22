from insta360_hack.engine.context import RunContext


class CreateTextTo3D:
    name = "create_text_to_3d"

    async def execute(self, ctx: RunContext) -> None:
        task_id = await ctx.client.create_text_to_3d(
            prompt=ctx.record["inputs"]["prompt"],
            image_url=ctx.record["artifacts"]["image_url"],
            style=ctx.record["inputs"].get("style"),
        )
        ctx.record["artifacts"]["lux3d_task_id"] = task_id
