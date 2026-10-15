"""v1 路由聚合。"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import auth, interviews, jds, match, resumes, stats

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(resumes.router)
api_router.include_router(jds.router)
api_router.include_router(match.router)
api_router.include_router(interviews.router)
api_router.include_router(stats.router)

__all__ = ["api_router"]
