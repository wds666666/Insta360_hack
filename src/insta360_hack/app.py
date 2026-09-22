from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from insta360_hack.api.runs import router
from insta360_hack.config import Settings, load_settings
from insta360_hack.engine.store import RunStore
from insta360_hack.lux3d.client import Lux3DClient


def create_app(settings: Settings | None = None, client: object | None = None, store: RunStore | None = None) -> FastAPI:
    settings = settings or load_settings()
    store = store or RunStore(settings.data_dir / "runs")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        http = None
        if client is None:
            http = httpx.AsyncClient(timeout=120, follow_redirects=True)
            app.state.client = Lux3DClient(http, settings)
        else:
            app.state.client = client
        yield
        if http is not None:
            await http.aclose()

    app = FastAPI(title="insta360-hack", lifespan=lifespan)
    app.state.settings = settings
    app.state.store = store
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()
