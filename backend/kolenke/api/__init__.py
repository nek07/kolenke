from fastapi import APIRouter

from kolenke.api.routes import chats, companies, pipeline, resume, settings, system, vacancies

api_router = APIRouter(prefix="/api")
for module in (settings, vacancies, pipeline, companies, chats, resume, system):
    api_router.include_router(module.router)

__all__ = ["api_router"]
