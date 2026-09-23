from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from insta360_hack.insta360.service import ALLOWED_FILE_NAMES


router = APIRouter(prefix="/api/v1/camera")
_NO_STORE = {"Cache-Control": "no-store"}


async def _capture_in_background(request: Request, capture_id: str) -> None:
    lock: asyncio.Lock = request.app.state.camera_lock
    try:
        await asyncio.to_thread(request.app.state.camera_service.capture, capture_id)
    finally:
        lock.release()


@router.post("/captures", status_code=202)
async def create_capture(request: Request, background_tasks: BackgroundTasks):
    lock: asyncio.Lock = request.app.state.camera_lock
    if lock.locked():
        raise HTTPException(
            status_code=409,
            detail={"code": "CAMERA_BUSY", "message": "相机正在执行另一个拍摄任务"},
        )
    await lock.acquire()
    capture_id = uuid.uuid4().hex
    try:
        request.app.state.capture_store.create(capture_id)
        background_tasks.add_task(_capture_in_background, request, capture_id)
    except Exception:
        lock.release()
        raise
    return {"capture_id": capture_id, "status": "pending"}


@router.get("/captures/{capture_id}")
async def get_capture(capture_id: str, request: Request):
    record = request.app.state.capture_store.get(capture_id)
    if record is None:
        raise HTTPException(status_code=404, detail="capture 不存在")
    return JSONResponse(record, headers=_NO_STORE)


@router.get("/captures/{capture_id}/files/{name}")
async def get_capture_file(capture_id: str, name: str, request: Request):
    if name not in ALLOWED_FILE_NAMES:
        raise HTTPException(status_code=404, detail="文件不存在")
    path = request.app.state.capture_store.file_path(capture_id, name)
    if path is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path, media_type="image/jpeg")
