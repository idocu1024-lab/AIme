from fastapi import APIRouter

from aime.api.admin import router as admin_router
from aime.api.auth import router as auth_router
from aime.api.entity import router as entity_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(entity_router)
api_router.include_router(admin_router)
