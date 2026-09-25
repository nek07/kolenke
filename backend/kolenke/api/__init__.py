from fastapi import APIRouter

from kolenke.api.routes import chats, companies, pipeline, settings, system, vacancies

api_router = APIRouter(prefix="/api")
for module in (settings, vacancies, pipeline, companies, chats, system):
    api_router.include_router(module.router)

__all__ = ["api_router"]
