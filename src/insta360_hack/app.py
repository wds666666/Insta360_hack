import asyncio
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from insta360_hack.api.camera import router as camera_router
from insta360_hack.api.runs import router as runs_router
from insta360_hack.config import Settings, load_settings
from insta360_hack.engine.context import make_context
from insta360_hack.engine.runner import run_workflow
from insta360_hack.engine.store import RunStore
from insta360_hack.insta360.service import CameraService, CaptureStore
from insta360_hack.lux3d.client import Lux3DClient
from insta360_hack.openrouter.client import OpenRouterClient


def create_app(
    settings: Settings | None = None,
    client: object | None = None,
    images: object | None = None,
    store: RunStore | None = None,
    capture_store: CaptureStore | None = None,
    camera_service: CameraService | None = None,
) -> FastAPI:
    settings = settings or load_settings()
    store = store or RunStore(settings.data_dir / "runs")
    capture_store = capture_store or CaptureStore(settings.data_dir / "captures")
    camera_service = camera_service or CameraService(settings, capture_store)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        http = None
        if client is None:
            http = httpx.AsyncClient(timeout=120, follow_redirects=True)
            app.state.client = Lux3DClient(http, settings)
            app.state.images = images or OpenRouterClient(http, settings)
        else:
            app.state.client = client
            app.state.images = images
        resumes = [
            asyncio.create_task(
                run_workflow(
                    make_context(
                        record,
                        image_bytes=None,
                        image_suffix=None,
                        client=app.state.client,
                        images=app.state.images,
                        settings=settings,
                        store=store,
                    ),
                    start_at=start_at,
                )
            )
            for record, start_at in store.pending_resumes
        ]
        store.pending_resumes.clear()
        yield
        for task in resumes:
            task.cancel()
        if resumes:
            await asyncio.gather(*resumes, return_exceptions=True)
        if http is not None:
            await http.aclose()

    app = FastAPI(title="insta360-hack", lifespan=lifespan)
    app.state.settings = settings
    app.state.store = store
    app.state.capture_store = capture_store
    app.state.camera_service = camera_service
    app.state.camera_lock = asyncio.Lock()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(runs_router)
    app.include_router(camera_router)
    return app


app = create_app()
