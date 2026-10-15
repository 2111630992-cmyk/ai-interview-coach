"""简历：上传解析 / 列表 / 详情 / 手动修正 / 删除。"""

from __future__ import annotations

from fastapi import APIRouter, File, UploadFile
from sqlmodel import select

from app.api.deps import AIDep
from app.core.config import settings
from app.core.deps import CurrentUser, SessionDep
from app.core.errors import InvalidInputError, NotFoundError
from app.core.logging import logger, redact
from app.models import InterviewSession, MatchAnalysis, Resume
from app.schemas.api import ResumePublic
from app.services.resume_parser import extract_text

router = APIRouter(prefix="/resumes", tags=["简历"])


def _to_public(r: Resume) -> ResumePublic:
    return ResumePublic(
        id=r.id,
        filename=r.filename,
        parsed=r.parsed or {},
        parse_warning=r.parse_warning,
        text_length=len(r.raw_text or ""),
        created_at=r.created_at,
    )


@router.post("", response_model=ResumePublic, summary="上传并解析简历")
async def upload_resume(
    db: SessionDep,
    user: CurrentUser,
    ai: AIDep,
    # B008：`File(...)` 作为默认值是 FastAPI 的官方参数声明方式，不是 bug
    file: UploadFile = File(..., description="PDF / DOCX / TXT，不超过 5MB"),
) -> ResumePublic:
    data = await file.read()
    filename = file.filename or "resume"

    # 文件校验与文本抽取都抛出 AppError 子类，路由不需要额外 try/except
    text = extract_text(filename, data, max_bytes=settings.upload_max_bytes)
    logger.info("简历解析：file=%s, %s", filename, redact(text, keep=0))

    parsed = await ai.parse_resume(text)
    parsed_dict = parsed.model_dump()

    warning = None
    if not parsed_dict.get("highlights") and not parsed_dict.get("projects"):
        warning = "解析结果较少，可能是简历结构比较特殊，建议手动补充项目经历后再开始面试。"

    resume = Resume(
        user_id=user.id,
        filename=filename,
        raw_text=text,
        parsed=parsed_dict,
        parse_warning=warning,
    )
    db.add(resume)
    await db.commit()
    await db.refresh(resume)
    return _to_public(resume)


@router.get("", response_model=list[ResumePublic], summary="简历列表")
async def list_resumes(db: SessionDep, user: CurrentUser) -> list[ResumePublic]:
    rows = await db.exec(
        select(Resume).where(Resume.user_id == user.id).order_by(Resume.created_at.desc())
    )
    return [_to_public(r) for r in rows.all()]


@router.get("/{resume_id}", response_model=ResumePublic, summary="简历详情")
async def get_resume(resume_id: str, db: SessionDep, user: CurrentUser) -> ResumePublic:
    resume = (
        await db.exec(
            select(Resume).where(Resume.id == resume_id, Resume.user_id == user.id)
        )
    ).first()
    if resume is None:
        raise NotFoundError("简历不存在")
    return _to_public(resume)


@router.patch("/{resume_id}", response_model=ResumePublic, summary="手动修正解析结果")
async def update_resume(
    resume_id: str,
    payload: dict,
    db: SessionDep,
    user: CurrentUser,
) -> ResumePublic:
    """LLM 抽取难免出错，允许用户直接改结构化的 `parsed`。"""
    resume = (
        await db.exec(
            select(Resume).where(Resume.id == resume_id, Resume.user_id == user.id)
        )
    ).first()
    if resume is None:
        raise NotFoundError("简历不存在")

    parsed = payload.get("parsed")
    if not isinstance(parsed, dict):
        raise InvalidInputError("请求体需要包含 parsed 对象")

    resume.parsed = parsed
    resume.parse_warning = None
    db.add(resume)
    await db.commit()
    await db.refresh(resume)
    return _to_public(resume)


@router.delete("/{resume_id}", summary="删除简历")
async def delete_resume(resume_id: str, db: SessionDep, user: CurrentUser) -> dict:
    resume = (
        await db.exec(
            select(Resume).where(Resume.id == resume_id, Resume.user_id == user.id)
        )
    ).first()
    if resume is None:
        raise NotFoundError("简历不存在")

    # 已被面试/匹配引用的简历不允许直接删，避免产生孤儿数据
    used = (
        await db.exec(select(InterviewSession).where(InterviewSession.resume_id == resume_id))
    ).first()
    if used is not None:
        raise InvalidInputError("这份简历已经被面试记录使用，删除会影响历史报告，请保留。")

    for m in (await db.exec(select(MatchAnalysis).where(MatchAnalysis.resume_id == resume_id))).all():
        await db.delete(m)

    await db.delete(resume)
    await db.commit()
    return {"ok": True}
