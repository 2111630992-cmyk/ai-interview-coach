"""岗位 JD：创建（自动抽取能力模型）/ 列表 / 详情 / 删除。"""

from __future__ import annotations

from fastapi import APIRouter
from sqlmodel import select

from app.api.deps import AIDep
from app.core.deps import CurrentUser, SessionDep
from app.core.errors import InvalidInputError, NotFoundError
from app.models import InterviewSession, JobDescription
from app.schemas.api import JDCreate, JDPublic

router = APIRouter(prefix="/jds", tags=["岗位 JD"])


def _to_public(j: JobDescription) -> JDPublic:
    return JDPublic(
        id=j.id,
        title=j.title,
        company=j.company,
        competency_model=j.competency_model or {},
        raw_text_length=len(j.raw_text or ""),
        created_at=j.created_at,
    )


@router.post("", response_model=JDPublic, summary="创建 JD 并抽取能力模型")
async def create_jd(payload: JDCreate, db: SessionDep, user: CurrentUser, ai: AIDep) -> JDPublic:
    model = await ai.analyze_jd(payload.title, payload.company, payload.raw_text)

    jd = JobDescription(
        user_id=user.id,
        title=payload.title,
        company=payload.company,
        raw_text=payload.raw_text,
        competency_model=model.model_dump(),
    )
    db.add(jd)
    await db.commit()
    await db.refresh(jd)
    return _to_public(jd)


@router.get("", response_model=list[JDPublic], summary="JD 列表")
async def list_jds(db: SessionDep, user: CurrentUser) -> list[JDPublic]:
    rows = await db.exec(
        select(JobDescription)
        .where(JobDescription.user_id == user.id)
        .order_by(JobDescription.created_at.desc())
    )
    return [_to_public(j) for j in rows.all()]


@router.get("/{jd_id}", response_model=JDPublic, summary="JD 详情")
async def get_jd(jd_id: str, db: SessionDep, user: CurrentUser) -> JDPublic:
    jd = (
        await db.exec(
            select(JobDescription).where(
                JobDescription.id == jd_id, JobDescription.user_id == user.id
            )
        )
    ).first()
    if jd is None:
        raise NotFoundError("岗位 JD 不存在")
    return _to_public(jd)


@router.delete("/{jd_id}", summary="删除 JD")
async def delete_jd(jd_id: str, db: SessionDep, user: CurrentUser) -> dict:
    jd = (
        await db.exec(
            select(JobDescription).where(
                JobDescription.id == jd_id, JobDescription.user_id == user.id
            )
        )
    ).first()
    if jd is None:
        raise NotFoundError("岗位 JD 不存在")

    used = (
        await db.exec(select(InterviewSession).where(InterviewSession.jd_id == jd_id))
    ).first()
    if used is not None:
        raise InvalidInputError("这份 JD 已被面试记录使用，删除会影响历史报告，请保留。")

    await db.delete(jd)
    await db.commit()
    return {"ok": True}
