from insta360_hack.engine.context import RunContext
from insta360_hack.engine.errors import NodeError


class DownloadModel:
    name = "download_model"

    async def execute(self, ctx: RunContext) -> None:
        mesh_slots = ctx.record["artifacts"].get("mesh_output_urls") or []
        export_slots = ctx.record["artifacts"].get("export_output_urls") or []
        glb_url = ctx.record["artifacts"].get("mesh_glb_url")
        if not glb_url and len(mesh_slots) > 1:
            glb_url = mesh_slots[1]
        stl_url = export_slots[5] if len(export_slots) > 5 else None
        if not glb_url or not stl_url:
            raise NodeError("BAD_OUTPUT", "缺少网格 GLB 或 STL 下载地址")
        directory = ctx.run_dir()
        await ctx.client.download(glb_url, directory / "model.glb")
        await ctx.client.download(stl_url, directory / "model.stl")
        run_id = ctx.record["run_id"]
        ctx.record["outputs"] = {
            "reference_image": ctx.record["artifacts"].get("reference_file"),
            "model_glb": f"/api/v1/runs/{run_id}/files/model.glb",
            "model_stl": f"/api/v1/runs/{run_id}/files/model.stl",
        }
        ctx.record["artifacts"]["mesh_glb_url"] = glb_url
        ctx.record["artifacts"]["stl_url"] = stl_url
