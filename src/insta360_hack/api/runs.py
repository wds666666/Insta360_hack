import re
import uuid

from fastapi import APIRouter, BackgroundTasks, Body, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from insta360_hack.engine.context import make_context
from insta360_hack.engine.runner import run_workflow
from insta360_hack.engine.store import new_record
from insta360_hack.engine.workflows import WORKFLOW_ID
from insta360_hack.nodes.references import MAX_REFERENCE_IMAGES
from insta360_hack.nodes.save_image import suffix_from_name
from insta360_hack.nodes.validate import STYLES

router = APIRouter(prefix="/api/v1")
_MAX_IMAGE_BYTES = 20 * 1024 * 1024
_FILE_NAME = re.compile(
    r"^(reference(?:-\d{1,2})?\.(jpg|png|webp)|optimized\.(jpg|png|webp)|model\.(glb|stl))$"
)
_MEDIA = {
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".glb": "model/gltf-binary",
    ".stl": "model/stl",
}
_CONTENT_SUFFIX = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


@router.post("/runs", status_code=202)
async def create_run(
    request: Request,
    background_tasks: BackgroundTasks,
    workflow_id: str = Form(...),
    prompt: str = Form(...),
    style: str | None = Form(None),
    image_url: str | None = Form(None),
    mode: str = Form("auto"),
    image: list[UploadFile] | None = File(None),
):
    if workflow_id != WORKFLOW_ID:
        raise HTTPException(status_code=422, detail="v1 只支持 img-to-3d")
    prompt = prompt.strip()
    if not prompt:
        raise HTTPException(status_code=422, detail="prompt 不能为空")
    style = (style or "").strip() or None
    if style is not None and style not in STYLES:
        raise HTTPException(status_code=422, detail="style 不在允许列表")
    image_url = (image_url or "").strip() or None
    mode = (mode or "auto").strip()
    if mode not in {"auto", "confirm"}:
        raise HTTPException(status_code=422, detail="mode 只能是 auto 或 confirm")
    reference_images = await _read_images(image)
    if bool(reference_images) == bool(image_url):
        raise HTTPException(status_code=422, detail="参考图文件和 image_url 需要二选一")

    run_id = uuid.uuid4().hex
    record = new_record(run_id, prompt=prompt, style=style, image_url=image_url, mode=mode)
    store = request.app.state.store
    store.create(record)
    ctx = make_context(
        record,
        reference_images=reference_images,
        client=request.app.state.client,
        images=request.app.state.images,
        settings=request.app.state.settings,
        store=store,
    )
    background_tasks.add_task(run_workflow, ctx)
    return {"run_id": run_id, "workflow_id": WORKFLOW_ID, "status": "pending"}


_NO_STORE = {"Cache-Control": "no-store"}


@router.get("/runs")
async def list_runs(request: Request):
    return JSONResponse({"runs": request.app.state.store.summaries()}, headers=_NO_STORE)


@router.post("/runs/{run_id}/image", status_code=202)
async def continue_image(
    run_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    prompt: str | None = Body(None, embed=True),
):
    store = request.app.state.store
    record = store.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="run 不存在")
    if record.get("status") != "awaiting_image":
        raise HTTPException(status_code=409, detail="现在不能生成优化图")
    revised = (prompt or "").strip()
    if revised:
        record.setdefault("artifacts", {})["image_prompt"] = revised
    if not (record.get("artifacts") or {}).get("image_prompt"):
        raise HTTPException(status_code=422, detail="剖面说明不能为空")
    record["status"] = "running"
    store.save(record)
    ctx = make_context(
        record,
        image_bytes=None,
        image_suffix=None,
        client=request.app.state.client,
        images=request.app.state.images,
        settings=request.app.state.settings,
        store=store,
    )
    background_tasks.add_task(run_workflow, ctx, start_at="optimize_image")
    return {"run_id": run_id, "workflow_id": WORKFLOW_ID, "status": "running"}


@router.post("/runs/{run_id}/mesh", status_code=202)
async def continue_mesh(run_id: str, request: Request, background_tasks: BackgroundTasks):
    store = request.app.state.store
    record = store.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="run 不存在")
    if record.get("status") != "awaiting_mesh":
        raise HTTPException(status_code=409, detail="现在不能生成网格")
    record["status"] = "running"
    store.save(record)
    ctx = make_context(
        record,
        image_bytes=None,
        image_suffix=None,
        client=request.app.state.client,
        images=request.app.state.images,
        settings=request.app.state.settings,
        store=store,
    )
    background_tasks.add_task(run_workflow, ctx, start_at="upload_image")
    return {"run_id": run_id, "workflow_id": WORKFLOW_ID, "status": "running"}


@router.get("/runs/{run_id}")
async def get_run(run_id: str, request: Request):
    record = request.app.state.store.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="run 不存在")
    return JSONResponse(record, headers=_NO_STORE)


@router.get("/runs/{run_id}/files/{name}")
async def get_file(run_id: str, name: str, request: Request):
    if _FILE_NAME.match(name) is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    if request.app.state.store.get(run_id) is None:
        raise HTTPException(status_code=404, detail="run 不存在")
    root = (request.app.state.settings.data_dir / "runs" / run_id).resolve()
    path = (root / name).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path, media_type=_MEDIA[path.suffix])


async def _read_images(images: list[UploadFile] | None) -> list[tuple[bytes, str]]:
    ready: list[tuple[bytes, str]] = []
    for image in images or []:
        item = await _read_image(image)
        if item is not None:
            ready.append(item)
    if len(ready) > MAX_REFERENCE_IMAGES:
        raise HTTPException(status_code=422, detail=f"参考图最多 {MAX_REFERENCE_IMAGES} 张")
    return ready


async def _read_image(image: UploadFile | None) -> tuple[bytes, str] | None:
    if image is None:
        return None
    raw = await image.read()
    if not raw:
        return None
    if len(raw) > _MAX_IMAGE_BYTES:
        raise HTTPException(status_code=422, detail="参考图不能超过 20MB")
    suffix = suffix_from_name(image.filename or "")
    if not suffix:
        content_type = (image.content_type or "").split(";")[0].strip().lower()
        suffix = _CONTENT_SUFFIX.get(content_type, "")
    if not suffix:
        raise HTTPException(status_code=422, detail="参考图只支持 jpg、png、webp")
    return raw, suffix
