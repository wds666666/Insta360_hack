from insta360_hack.engine.context import RunContext
from insta360_hack.engine.errors import NodeError

STYLES = {
    "photorealistic",
    "cartoon",
    "anime",
    "hand_painted",
    "cyberpunk",
    "fantasy",
    "glass",
}


class Validate:
    name = "validate"

    async def execute(self, ctx: RunContext) -> None:
        prompt = (ctx.record["inputs"].get("prompt") or "").strip()
        if not prompt:
            raise NodeError("INVALID_INPUT", "prompt 不能为空")
        ctx.record["inputs"]["prompt"] = prompt
        style = ctx.record["inputs"].get("style") or None
        if style is not None and style not in STYLES:
            raise NodeError("INVALID_INPUT", "style 不在允许列表")
        ctx.record["inputs"]["style"] = style
        has_file = bool(ctx.image_bytes)
        has_url = bool(ctx.record["inputs"].get("image_url"))
        if has_file == has_url:
            raise NodeError("INVALID_INPUT", "参考图文件和 image_url 需要二选一")
