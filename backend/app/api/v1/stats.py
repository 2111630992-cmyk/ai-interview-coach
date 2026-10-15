"""统计：分数趋势与工作台概览。"""

from __future__ import annotations

from fastapi import APIRouter
from sqlmodel import select

from app.constants import DIMENSION_LABELS
from app.core.deps import CurrentUser, SessionDep
from app.models import InterviewSession, JobDescription, MatchAnalysis, Resume
from app.schemas.api import TrendPoint
from app.services.interview_service import load_context_names

router = APIRouter(prefix="/stats", tags=["统计"])


@router.get("/trend", response_model=list[TrendPoint], summary="分数趋势")
async def trend(db: SessionDep, user: CurrentUser, limit: int = 20) -> list[TrendPoint]:
    rows = await db.exec(
        select(InterviewSession)
        .where(
            InterviewSession.user_id == user.id,
            InterviewSession.total_score.is_not(None),  # type: ignore[union-attr]
        )
        .order_by(InterviewSession.created_at.desc())
        .limit(max(1, min(limit, 100)))
    )
    sessions = list(rows.all())[::-1]  # 返回按时间正序，便于画折线
    if not sessions:
        return []
    _, jd_titles = await load_context_names(db, sessions)
    return [
        TrendPoint(
            session_id=s.id,
            date=s.finished_at or s.created_at,
            jd_title=jd_titles.get(s.jd_id or ""),
            interview_type=(s.config or {}).get("interview_type", ""),
            total_score=s.total_score,
        )
        for s in sessions
    ]


@router.get("/overview", summary="工作台概览")
async def overview(db: SessionDep, user: CurrentUser) -> dict:
    resumes = list(
        (await db.exec(select(Resume).where(Resume.user_id == user.id))).all()
    )
    jds = list(
        (await db.exec(select(JobDescription).where(JobDescription.user_id == user.id))).all()
    )
    sessions = list(
        (await db.exec(select(InterviewSession).where(InterviewSession.user_id == user.id))).all()
    )
    matches = list(
        (await db.exec(select(MatchAnalysis).where(MatchAnalysis.user_id == user.id))).all()
    )

    scored = [s for s in sessions if s.total_score is not None]

    # 五维平均（只统计有维度的会话）
    dim_acc: dict[str, float] = {}
    dim_n: dict[str, int] = {}
    for s in scored:
        for d, v in (s.dimensions or {}).items():
            dim_acc[d] = dim_acc.get(d, 0.0) + float(v)
            dim_n[d] = dim_n.get(d, 0) + 1
    dimension_avg = {
        DIMENSION_LABELS.get(d, d): round(dim_acc[d] / dim_n[d], 1) for d in dim_acc if dim_n[d]
    }

    return {
        "resume_count": len(resumes),
        "jd_count": len(jds),
        "interview_count": len(sessions),
        "finished_count": len(scored),
        "match_count": len(matches),
        "avg_score": round(sum(s.total_score for s in scored) / len(scored), 1) if scored else None,
        "best_score": max((s.total_score for s in scored), default=None),
        "dimension_avg": dimension_avg,
    }
