from insta360_hack.engine.context import RunContext
from insta360_hack.engine.errors import NodeError
from insta360_hack.nodes.references import load_reference_images
from insta360_hack.openrouter.client import OpenRouterError


class PlanCutaway:
    name = "plan_cutaway"

    async def execute(self, ctx: RunContext) -> None:
        prompt = ctx.record["inputs"]["prompt"]
        style = ctx.record["inputs"].get("style")
        if style:
            prompt = f"{prompt}\n风格：{style}"
        try:
            planned = await ctx.images.plan_cutaway(prompt=prompt, images=load_reference_images(ctx))
        except OpenRouterError as exc:
            raise NodeError(exc.code, exc.message) from exc
        ctx.record["artifacts"]["image_prompt"] = planned
        ctx.touch()
