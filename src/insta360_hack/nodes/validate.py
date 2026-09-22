from insta360_hack.engine.context import RunContext
from insta360_hack.engine.errors import NodeError
from insta360_hack.nodes.references import MAX_REFERENCE_IMAGES, SUFFIXES

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
        has_file = bool(ctx.reference_images)
        has_url = bool(ctx.record["inputs"].get("image_url"))
        if has_file == has_url:
            raise NodeError("INVALID_INPUT", "参考图文件和 image_url 需要二选一")
        if len(ctx.reference_images) > MAX_REFERENCE_IMAGES:
            raise NodeError("INVALID_INPUT", f"参考图最多 {MAX_REFERENCE_IMAGES} 张")
        for _raw, suffix in ctx.reference_images:
            if suffix not in SUFFIXES:
                raise NodeError("INVALID_INPUT", "参考图只支持 jpg、png、webp")
