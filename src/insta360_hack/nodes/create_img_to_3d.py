from insta360_hack.engine.context import RunContext


class CreateImgTo3D:
    name = "create_img_to_3d"

    async def execute(self, ctx: RunContext) -> None:
        task_id = await ctx.client.create_img_to_3d(image_url=ctx.record["artifacts"]["image_url"])
        ctx.record["artifacts"]["lux3d_task_id"] = task_id
