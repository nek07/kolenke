"""kolenke API. Run: uvicorn kolenke.main:app --host 127.0.0.1 --port 8765 (from the backend folder)."""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.routing import APIRoute

from kolenke import db
from kolenke.api import api_router
from kolenke.api.security import LocalOnlyMiddleware
from kolenke.config import ensure_dirs, get_config
from kolenke.workers import scheduler


def _operation_id(route: APIRoute) -> str:
    return route.name  # short names for the generated frontend client


def create_app() -> FastAPI:
    cfg = get_config()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        ensure_dirs(cfg)
        db.init()
        if cfg.background:
            scheduler.start()
        yield
        scheduler.stop()

    app = FastAPI(title="kolenke", version="2.0.0", lifespan=lifespan, generate_unique_id_function=_operation_id)
    app.add_middleware(LocalOnlyMiddleware)
    app.include_router(api_router)
    return app


app = create_app()
