"""匹配分析：简历 × JD。同一组合命中缓存，不重复调用模型。"""

from __future__ import annotations

from fastapi import APIRouter
from sqlmodel import select

from app.api.deps import AIDep
from app.core.deps import CurrentUser, SessionDep
from app.core.errors import NotFoundError
from app.models import JobDescription, MatchAnalysis, Resume
from app.schemas.api import MatchPublic, MatchRequest

router = APIRouter(tags=["匹配分析"])


def _to_public(m: MatchAnalysis, *, cached: bool) -> MatchPublic:
    return MatchPublic(
        id=m.id,
        resume_id=m.resume_id,
        jd_id=m.jd_id,
        match_score=m.match_score,
        strengths=m.strengths or [],
        risks=m.risks or [],
        likely_questions=m.likely_questions or [],
        summary=m.summary,
        cached=cached,
        created_at=m.created_at,
    )


@router.post("/match", response_model=MatchPublic, summary="简历与岗位匹配分析")
async def analyze_match(
    payload: MatchRequest, db: SessionDep, user: CurrentUser, ai: AIDep
) -> MatchPublic:
    resume = (
        await db.exec(
            select(Resume).where(Resume.id == payload.resume_id, Resume.user_id == user.id)
        )
    ).first()
    if resume is None:
        raise NotFoundError("简历不存在")

    jd = (
        await db.exec(
            select(JobDescription).where(
                JobDescription.id == payload.jd_id, JobDescription.user_id == user.id
            )
        )
    ).first()
    if jd is None:
        raise NotFoundError("岗位 JD 不存在")

    # 缓存：同一份简历投同一个 JD，结果不会变
    cached_row = (
        await db.exec(
            select(MatchAnalysis)
            .where(
                MatchAnalysis.user_id == user.id,
                MatchAnalysis.resume_id == resume.id,
                MatchAnalysis.jd_id == jd.id,
            )
            .order_by(MatchAnalysis.created_at.desc())
        )
    ).first()
    if cached_row is not None:
        return _to_public(cached_row, cached=True)

    result = await ai.match(
        resume_parsed=resume.parsed or {},
        jd_model=jd.competency_model or {},
        job_title=jd.title,
        company=jd.company,
    )

    row = MatchAnalysis(
        user_id=user.id,
        resume_id=resume.id,
        jd_id=jd.id,
        match_score=result.match_score,
        strengths=result.strengths,
        risks=result.risks,
        likely_questions=result.likely_questions,
        summary=result.summary,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _to_public(row, cached=False)


@router.get("/match", response_model=list[MatchPublic], summary="历史匹配分析")
async def list_matches(db: SessionDep, user: CurrentUser) -> list[MatchPublic]:
    rows = await db.exec(
        select(MatchAnalysis)
        .where(MatchAnalysis.user_id == user.id)
        .order_by(MatchAnalysis.created_at.desc())
    )
    return [_to_public(m, cached=True) for m in rows.all()]
