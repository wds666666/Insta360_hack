import argparse
import asyncio
import json
import uuid
from pathlib import Path

import httpx

from insta360_hack.config import load_settings
from insta360_hack.engine.context import make_context
from insta360_hack.engine.runner import run_workflow
from insta360_hack.engine.store import RunStore, new_record
from insta360_hack.lux3d.client import Lux3DClient
from insta360_hack.nodes.save_image import suffix_from_name
from insta360_hack.openrouter.client import OpenRouterClient


def main() -> None:
    parser = argparse.ArgumentParser(description="本地跑图生 3D 工作流")
    parser.add_argument("--prompt")
    parser.add_argument("--image", type=Path)
    parser.add_argument("--image-url")
    parser.add_argument("--style")
    parser.add_argument("--resume", help="继续轮询已创建的 run_id，不再次提交任务")
    args = parser.parse_args()
    if args.resume:
        raise SystemExit(asyncio.run(_resume(args.resume)))
    if not args.prompt:
        parser.error("新建任务需要 --prompt")
    raise SystemExit(asyncio.run(_run(args)))


async def _run(args: argparse.Namespace) -> int:
    if bool(args.image) == bool(args.image_url):
        raise SystemExit("参考图文件和 --image-url 需要二选一")
    settings = load_settings()
    store = RunStore(settings.data_dir / "runs")
    image_bytes = None
    image_suffix = None
    image_url = args.image_url
    if args.image:
        image_bytes = args.image.read_bytes()
        image_suffix = suffix_from_name(args.image.name)
        image_url = None
    record = new_record(uuid.uuid4().hex, prompt=args.prompt, style=args.style, image_url=image_url)
    store.create(record)
    print(f"run_id={record['run_id']}", flush=True)
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as http:
        ctx = make_context(
            record,
            image_bytes=image_bytes,
            image_suffix=image_suffix,
            client=Lux3DClient(http, settings),
            images=OpenRouterClient(http, settings),
            settings=settings,
            store=store,
        )
        await run_workflow(ctx)
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0 if record["status"] == "succeeded" else 1


async def _resume(run_id: str) -> int:
    from insta360_hack.engine.errors import NodeError
    from insta360_hack.lux3d.client import Lux3DError
    from insta360_hack.nodes.download_model import DownloadModel
    from insta360_hack.nodes.export_stl import ExportStl
    from insta360_hack.nodes.poll import PollLux3D

    settings = load_settings()
    store = RunStore(settings.data_dir / "runs", recover=False)
    record = store.get(run_id)
    if record is None:
        raise SystemExit(f"run 不存在: {run_id}")
    artifacts = record["artifacts"]
    if not artifacts.get("lux3d_task_id") and not artifacts.get("mesh_glb_url"):
        raise SystemExit("这个 run 还没有 Lux3D 任务，不能续跑")
    if not artifacts.get("mesh_output_urls"):
        urls = artifacts.get("lux3d_output_urls") or []
        if len(urls) >= 2:
            artifacts["mesh_output_urls"] = urls
        elif artifacts.get("lux3d_glb_url"):
            artifacts["mesh_output_urls"] = [None, artifacts["lux3d_glb_url"]]
    print(f"run_id={run_id} 继续导出网格 GLB 和 STL", flush=True)
    record["status"] = "running"
    record["error"] = None
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as http:
        ctx = make_context(
            record,
            image_bytes=None,
            image_suffix=None,
            client=Lux3DClient(http, settings),
            images=None,
            settings=settings,
            store=store,
        )
        try:
            if artifacts.get("lux3d_task_id"):
                await PollLux3D("poll_mesh", "lux3d_task_id", "mesh_output_urls", "网格生成").execute(ctx)
            await ExportStl().execute(ctx)
            await PollLux3D("poll_stl", "export_task_id", "export_output_urls", "导出 STL").execute(ctx)
            await DownloadModel().execute(ctx)
        except (NodeError, Lux3DError) as exc:
            record["status"] = "failed"
            record["error"] = {"code": exc.code, "message": exc.message}
            ctx.touch()
            print(json.dumps(record, ensure_ascii=False, indent=2))
            return 1
    record["status"] = "succeeded"
    record["current_node"] = None
    ctx.touch()
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    main()
