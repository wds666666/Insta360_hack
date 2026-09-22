from insta360_hack.engine.context import RunContext
from insta360_hack.engine.errors import NodeError


class ExportStl:
    name = "export_stl"

    async def execute(self, ctx: RunContext) -> None:
        slots = ctx.record["artifacts"].get("mesh_output_urls") or []
        glb_url = slots[1] if len(slots) > 1 else None
        if not glb_url:
            raise NodeError("BAD_OUTPUT", "没有网格 GLB，不能导出 STL")
        ctx.record["artifacts"]["mesh_glb_url"] = glb_url
        task_id = await ctx.client.create_stl_export(model_url=glb_url)
        ctx.record["artifacts"]["export_task_id"] = task_id
