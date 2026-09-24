from fastapi import APIRouter

from .endpoints import auth, imports, knowledge_ingestion, timetable

api_router = APIRouter()
api_router.include_router(timetable.router, prefix="", tags=["timetable"])
api_router.include_router(imports.router, prefix="/imports", tags=["imports"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(
    knowledge_ingestion.router, prefix="/knowledge", tags=["knowledge-ingestion"]
)
