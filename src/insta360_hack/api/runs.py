import re
import uuid

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from insta360_hack.engine.context import make_context
from insta360_hack.engine.runner import run_workflow
from insta360_hack.engine.store import new_record
from insta360_hack.engine.workflows import WORKFLOW_ID
from insta360_hack.nodes.save_image import suffix_from_name
from insta360_hack.nodes.validate import STYLES

router = APIRouter(prefix="/api/v1")
_MAX_IMAGE_BYTES = 20 * 1024 * 1024
_FILE_NAME = re.compile(r"^(reference\.(jpg|png|webp)|model\.(glb|stl))$")
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
    image: UploadFile | None = File(None),
):
    if workflow_id != WORKFLOW_ID:
        raise HTTPException(status_code=422, detail="v1 只支持 text-to-3d")
    prompt = prompt.strip()
    if not prompt:
        raise HTTPException(status_code=422, detail="prompt 不能为空")
    style = (style or "").strip() or None
    if style is not None and style not in STYLES:
        raise HTTPException(status_code=422, detail="style 不在允许列表")
    image_url = (image_url or "").strip() or None
    image_bytes, image_suffix = await _read_image(image)
    if bool(image_bytes) == bool(image_url):
        raise HTTPException(status_code=422, detail="参考图文件和 image_url 需要二选一")

    run_id = uuid.uuid4().hex
    record = new_record(run_id, prompt=prompt, style=style, image_url=image_url)
    store = request.app.state.store
    store.create(record)
    ctx = make_context(
        record,
        image_bytes=image_bytes,
        image_suffix=image_suffix,
        client=request.app.state.client,
        settings=request.app.state.settings,
        store=store,
    )
    background_tasks.add_task(run_workflow, ctx)
    return {"run_id": run_id, "workflow_id": WORKFLOW_ID, "status": "pending"}


@router.get("/runs/{run_id}")
async def get_run(run_id: str, request: Request):
    record = request.app.state.store.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="run 不存在")
    return record


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


async def _read_image(image: UploadFile | None) -> tuple[bytes | None, str | None]:
    if image is None:
        return None, None
    raw = await image.read()
    if not raw:
        return None, None
    if len(raw) > _MAX_IMAGE_BYTES:
        raise HTTPException(status_code=422, detail="参考图不能超过 20MB")
    suffix = suffix_from_name(image.filename or "")
    if not suffix:
        content_type = (image.content_type or "").split(";")[0].strip().lower()
        suffix = _CONTENT_SUFFIX.get(content_type, "")
    if not suffix:
        raise HTTPException(status_code=422, detail="参考图只支持 jpg、png、webp")
    return raw, suffix
