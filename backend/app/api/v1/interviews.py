"""面试：创建 / 列表 / 详情 / SSE 推进 / 提示 / 跳过 / 参考答案 / 暂停续做 / 结束 / 报告。

SSE 事件协议（`text/event-stream`）：
    event: stage     data: {"stage":..., "progress":0.5, "elapsed_min":...}
    event: token     data: {"delta":"那你"}                  # 打字机效果
    event: question  data: {turn_id, turn_index, question, is_followup, interviewer, ...}
    event: eval      data: {turn_id, score, is_weak}         # 练习模式才下发
    event: done      data: {turn_index, stage_finished, session_finished, usage}
    event: error     data: {code, message, detail}
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter
from sqlmodel import select
from sse_starlette.sse import EventSourceResponse

from app.api.deps import AIDep
from app.constants import (
    ACTIVE_STATUSES,
    STATUS_ABORTED,
    STATUS_FINISHED,
    STATUS_PAUSED,
)
from app.core.deps import CurrentUser, SessionDep
from app.core.errors import AppError, InterviewStateError, NotFoundError
from app.interviewers import Interviewer, get_interviewer, list_interviewers
from app.models import InterviewSession, JobDescription, Report, Resume, Turn
from app.schemas.api import (
    AnswerRequest,
    InterviewCreate,
    InterviewDetail,
    InterviewerPublic,
    InterviewSummary,
    ReportPublic,
    SkipRequest,
    TrackUpdateRequest,
    TurnPublic,
)
from app.services.ai_types import usage_delta
from app.services.interview_service import (
    advance_turn,
    create_session,
    elapsed_minutes,
    finish_session,
    generate_suggested_answer,
    get_session_or_404,
    get_turns,
    load_context_names,
    pause_session,
    resume_session,
    roster_interviewer,
    skip_current_question,
    update_turn_tracking,
)

logger = logging.getLogger("app.api.interview")

router = APIRouter(prefix="/interviews", tags=["面试"])


def _persona_public(persona: Interviewer | None) -> InterviewerPublic | None:
    if persona is None:
        return None
    return InterviewerPublic(**persona.public())


# ======================================================================
# 序列化辅助
# ======================================================================


def _sse(event: str, data: dict[str, Any]) -> dict[str, str]:
    return {"event": event, "data": json.dumps(data, ensure_ascii=False)}


def _reported_usage(before: dict, after: dict) -> dict:
    return usage_delta(before, after)


async def _context_names(
    db: SessionDep, sessions: list[InterviewSession]
) -> tuple[dict[str, str], dict[str, str]]:
    """转发到服务层，保持路由层只关心 HTTP。"""
    return await load_context_names(db, sessions)


async def _summary(
    db: SessionDep,
    session: InterviewSession,
    *,
    resume_names: dict[str, str] | None = None,
    jd_titles: dict[str, str] | None = None,
    turn_count: int | None = None,
) -> InterviewSummary:
    if turn_count is None:
        turn_count = len(await get_turns(db, session.id))

    resume_filename = (resume_names or {}).get(session.resume_id, "")
    if not resume_filename:
        r = (await db.exec(select(Resume).where(Resume.id == session.resume_id))).first()
        resume_filename = r.filename if r else ""

    jd_title = (jd_titles or {}).get(session.jd_id or "")
    if session.jd_id and not jd_title:
        j = (await db.exec(select(JobDescription).where(JobDescription.id == session.jd_id))).first()
        jd_title = j.title if j else None

    return InterviewSummary(
        id=session.id,
        status=session.status,
        config=session.config or {},
        plan_summary=session.plan_summary,
        current_stage=session.current_stage,
        current_turn_index=session.current_turn_index,
        turn_count=turn_count,
        total_score=session.total_score,
        dimensions=session.dimensions,
        delivery_summary=session.delivery_summary or {},
        resume_filename=resume_filename,
        jd_title=jd_title,
        current_interviewer=_persona_public(
            roster_interviewer(session, session.current_stage or "intro")
        ),
        started_at=session.started_at,
        finished_at=session.finished_at,
        created_at=session.created_at,
    )


def _turn_public(
    t: Turn, *, expose_scores: bool, session: InterviewSession | None = None
) -> TurnPublic:
    persona = roster_interviewer(session, t.stage) if session is not None else None
    return TurnPublic(
        id=t.id,
        turn_index=t.turn_index,
        stage=t.stage,
        competency=t.competency,
        question=t.question,
        answer=t.answer,
        is_followup=t.is_followup,
        followup_depth=t.followup_depth,
        parent_turn_id=t.parent_turn_id,
        interviewer=_persona_public(persona),
        hinted=t.hinted,
        skipped=t.skipped,
        marked=t.marked,
        delivery_metrics=t.delivery_metrics,
        recording_key=t.recording_key,
        has_suggested_answer=bool(t.suggested_answer),
        evaluation=t.evaluation if expose_scores else None,
        created_at=t.created_at,
    )


def _report_public(r: Report, session: InterviewSession | None = None) -> ReportPublic:
    return ReportPublic(
        id=r.id,
        session_id=r.session_id,
        verdict=r.verdict,
        verdict_label=r.verdict_label,
        summary=r.summary,
        dimension_scores=r.dimension_scores or {},
        top_problems=r.top_problems or [],
        per_turn_feedback=r.per_turn_feedback or [],
        training_plan=r.training_plan or [],
        delivery_summary=(session.delivery_summary if session else {}) or {},
        created_at=r.created_at,
    )


# ======================================================================
# CRUD
# ======================================================================


@router.post("", response_model=InterviewDetail, summary="创建面试（生成面试计划）")
async def create(
    payload: InterviewCreate, db: SessionDep, user: CurrentUser, ai: AIDep
) -> InterviewDetail:
    resume = (
        await db.exec(
            select(Resume).where(Resume.id == payload.resume_id, Resume.user_id == user.id)
        )
    ).first()
    if resume is None:
        raise NotFoundError("简历不存在")

    jd = None
    if payload.jd_id:
        jd = (
            await db.exec(
                select(JobDescription).where(
                    JobDescription.id == payload.jd_id, JobDescription.user_id == user.id
                )
            )
        ).first()
        if jd is None:
            raise NotFoundError("岗位 JD 不存在")

    session = await create_session(
        db=db,
        user_id=user.id,
        resume=resume,
        jd=jd,
        config=payload.config.model_dump(),
        ai=ai,
    )
    summary = await _summary(db, session, turn_count=0)
    expose = bool((session.config or {}).get("realtime_feedback"))
    return InterviewDetail(
        **summary.model_dump(),
        plan=session.plan or {},
        roster=session.roster or {},
        token_usage=session.token_usage or {},
        turns=[],
        expose_scores=expose,
    )


@router.get("", response_model=list[InterviewSummary], summary="面试历史")
async def list_interviews(db: SessionDep, user: CurrentUser) -> list[InterviewSummary]:
    rows = await db.exec(
        select(InterviewSession)
        .where(InterviewSession.user_id == user.id)
        .order_by(InterviewSession.created_at.desc())
    )
    sessions = list(rows.all())
    if not sessions:
        return []

    resume_names, jd_titles = await _context_names(db, sessions)

    # 一次性统计每个会话的轮次数，避免 N+1
    session_ids = [s.id for s in sessions]
    turn_rows = await db.exec(
        select(Turn.session_id).where(Turn.session_id.in_(session_ids))  # type: ignore[attr-defined]
    )
    counts: dict[str, int] = {}
    for sid in turn_rows.all():
        counts[sid] = counts.get(sid, 0) + 1

    return [
        await _summary(
            db,
            s,
            resume_names=resume_names,
            jd_titles=jd_titles,
            turn_count=counts.get(s.id, 0),
        )
        for s in sessions
    ]


@router.get("/{session_id}", response_model=InterviewDetail, summary="面试详情")
async def get_detail(session_id: str, db: SessionDep, user: CurrentUser) -> InterviewDetail:
    session = await get_session_or_404(db, session_id, user.id)
    turns = await get_turns(db, session.id)
    summary = await _summary(db, session, turn_count=len(turns))
    expose = bool((session.config or {}).get("realtime_feedback"))
    return InterviewDetail(
        **summary.model_dump(),
        plan=session.plan or {},
        roster=session.roster or {},
        token_usage=session.token_usage or {},
        turns=[_turn_public(t, expose_scores=expose, session=session) for t in turns],
        expose_scores=expose,
    )


@router.get("/meta/interviewers", response_model=list[InterviewerPublic], summary="面试官人格列表")
async def interviewers(language: str = "zh") -> list[InterviewerPublic]:
    """给前端「选择面试官」用。放在 /{session_id} 之前，避免被当成 session_id。"""
    return [InterviewerPublic(**p.public()) for p in list_interviewers(language)]


@router.get("/meta/interviewer/{interviewer_type}", response_model=InterviewerPublic, summary="单个面试官人格")
async def interviewer_detail(interviewer_type: str, language: str = "zh") -> InterviewerPublic:
    return InterviewerPublic(**get_interviewer(interviewer_type, language).public())


# ======================================================================
# SSE 推进
# ======================================================================


def _progress(session: InterviewSession) -> float:
    duration = max(1, int((session.config or {}).get("duration_min", 30)))
    return round(min(1.0, elapsed_minutes(session) / duration), 3)


def _assert_can_advance(session: InterviewSession) -> None:
    """统一的「能不能继续推进」校验，避免各端点各写一套状态判断。"""
    if session.status == STATUS_FINISHED:
        raise InterviewStateError("这场面试已经结束了")
    if session.status == STATUS_ABORTED:
        raise InterviewStateError("这场面试已放弃，请重新创建一场")
    if session.status == STATUS_PAUSED:
        raise InterviewStateError("面试处于暂停状态，请先调用 /resume 继续")
    if session.status not in ACTIVE_STATUSES:
        raise InterviewStateError("当前面试状态不允许该操作")


async def _sse_advance(
    *,
    db: SessionDep,
    ai: Any,
    session: InterviewSession,
    answer: str | None,
    client_elapsed_ms: int | None,
    first: bool,
    delivery_metrics: dict | None = None,
    recording_key: str | None = None,
    skipped: bool = False,
    event_source=None,
):
    """把 advance_turn 的事件流编码成 SSE。"""
    usage_before = ai.usage_snapshot()
    try:
        yield _sse(
            "stage",
            {
                "stage": session.current_stage or "intro",
                "progress": _progress(session),
                "elapsed_min": round(elapsed_minutes(session), 2),
                "first": first,
            },
        )

        result_payload = None
        stream = event_source if event_source is not None else advance_turn(
            db=db,
            ai=ai,
            session=session,
            answer=answer,
            client_elapsed_ms=client_elapsed_ms,
            delivery_metrics=delivery_metrics,
            recording_key=recording_key,
            skipped=skipped,
        )
        async for kind, payload in stream:
            if kind == "token":
                yield _sse("token", {"delta": payload})
            else:
                result_payload = payload

        if result_payload is None:  # pragma: no cover - advance_turn 保证会产出
            yield _sse("error", {"code": "NO_RESULT", "message": "面试推进失败"})
            return

        result = result_payload
        turn: Turn = result.turn

        usage = _reported_usage(usage_before, ai.usage_snapshot())
        session.token_usage = _merge_usage(session.token_usage or {}, usage)
        db.add(session)
        await db.commit()

        # 单题评分只在开启「实时反馈」时才下发，避免破坏沉浸感
        if result.evaluation is not None and (session.config or {}).get("realtime_feedback"):
            yield _sse(
                "eval",
                {
                    "turn_id": turn.id,
                    "score": result.evaluation.weighted_score(),
                    "is_weak": result.evaluation.is_weak,
                },
            )

        yield _sse(
            "question",
            {
                "turn_id": turn.id,
                "turn_index": turn.turn_index,
                "question": turn.question,
                "is_followup": turn.is_followup,
                "followup_depth": turn.followup_depth,
                "stage": turn.stage,
                "competency": turn.competency,
                "interviewer": (
                    _persona_public(roster_interviewer(session, turn.stage)).model_dump()
                    if roster_interviewer(session, turn.stage)
                    else None
                ),
            },
        )

        yield _sse(
            "done",
            {
                "turn_index": turn.turn_index,
                "stage_finished": result.decision.stage_finished,
                "session_finished": result.decision.session_finished,
                "progress": _progress(session),
                "usage": usage,
            },
        )

    except AppError as exc:
        logger.warning("SSE 业务异常：%s", exc.message)
        yield _sse("error", exc.to_body())
    except Exception:  # 流已开始，只能用事件报错
        # logger.exception 自带 traceback，不需要再传异常对象
        logger.exception("SSE 未处理异常")
        yield _sse(
            "error",
            {"code": "INTERNAL", "message": "服务器出了点问题，请点击重试", "detail": {}},
        )


def _merge_usage(acc: dict, delta: dict) -> dict:
    merged = dict(acc)
    for key in ("prompt_tokens", "completion_tokens", "total_tokens", "calls"):
        merged[key] = int(merged.get(key, 0) or 0) + int(delta.get(key, 0) or 0)
    by_task = dict(merged.get("by_task") or {})
    for k, v in (delta.get("by_task") or {}).items():
        by_task[k] = int(by_task.get(k, 0)) + int(v)
    merged["by_task"] = by_task
    return merged


@router.post("/{session_id}/start", summary="开始面试（SSE 流式出第一题）")
async def start(session_id: str, db: SessionDep, user: CurrentUser, ai: AIDep):
    session = await get_session_or_404(db, session_id, user.id)
    _assert_can_advance(session)
    turns = await get_turns(db, session.id)
    if turns:
        raise InterviewStateError("面试已经开始过了，请直接提交回答")

    return EventSourceResponse(
        _sse_advance(db=db, ai=ai, session=session, answer=None, client_elapsed_ms=None, first=True),
        ping=15,
    )


@router.post("/{session_id}/answer", summary="提交回答并流式获取下一题（SSE）")
async def answer(
    session_id: str, payload: AnswerRequest, db: SessionDep, user: CurrentUser, ai: AIDep
):
    session = await get_session_or_404(db, session_id, user.id)
    _assert_can_advance(session)

    turns = await get_turns(db, session.id)
    if not turns:
        raise InterviewStateError("面试还没开始，请先调用 /start")
    if turns[-1].answer:
        raise InterviewStateError("当前问题已经回答过了，请获取下一题")

    # 视频面试：前端把实测的表达指标一起上报，评分时作为客观依据
    metrics = payload.delivery_metrics.model_dump() if payload.delivery_metrics else None

    return EventSourceResponse(
        _sse_advance(
            db=db,
            ai=ai,
            session=session,
            answer=payload.answer,
            client_elapsed_ms=payload.client_elapsed_ms,
            first=False,
            delivery_metrics=metrics,
            recording_key=payload.recording_key,
        ),
        ping=15,
    )


@router.post("/{session_id}/skip", summary="跳过当前题并进入下一题（SSE）")
async def skip(
    session_id: str, payload: SkipRequest, db: SessionDep, user: CurrentUser, ai: AIDep
):
    """答不出来时的出口。

    真实面试里卡住也要继续往下走；让学生因为一道题卡死而放弃整场是产品设计的失败。
    跳过记 0 分，并在报告里体现。
    """
    session = await get_session_or_404(db, session_id, user.id)
    _assert_can_advance(session)
    if not (session.config or {}).get("allow_skip", True):
        raise InterviewStateError("本场面试未开启跳过功能")

    turns = await get_turns(db, session.id)
    if not turns:
        raise InterviewStateError("面试还没开始，请先调用 /start")
    if turns[-1].answer:
        raise InterviewStateError("当前问题已经回答过了，请获取下一题")

    return EventSourceResponse(
        _sse_advance(
            db=db,
            ai=ai,
            session=session,
            answer=None,
            client_elapsed_ms=payload.client_elapsed_ms,
            first=False,
            event_source=skip_current_question(
                db=db,
                ai=ai,
                session=session,
                reason=payload.reason,
                client_elapsed_ms=payload.client_elapsed_ms,
            ),
        ),
        ping=15,
    )


@router.post("/{session_id}/next", summary="生成下一题（断流恢复用，SSE）")
async def next_question(session_id: str, db: SessionDep, user: CurrentUser, ai: AIDep):
    """在「上一题已作答、但面试官下一题未成功发出」时恢复推进。

    正常流程不会走到这里：`/answer` 在同一个请求里既记录回答又生成下一题。
    但客户端可能在回答已落库、问题还在生成时断线（关标签页 / 切网络），
    此时 `/answer` 会因为"最后一题已答过"而拒绝，需要一个不携带回答的推进入口。
    """
    session = await get_session_or_404(db, session_id, user.id)
    _assert_can_advance(session)

    turns = await get_turns(db, session.id)
    if not turns:
        raise InterviewStateError("面试还没开始，请先调用 /start")
    if not turns[-1].answer:
        raise InterviewStateError("当前问题还没有回答，请先提交回答")

    return EventSourceResponse(
        _sse_advance(db=db, ai=ai, session=session, answer=None, client_elapsed_ms=None, first=False),
        ping=15,
    )


# ======================================================================
# 提示 / 标记 / 参考答案 / 暂停续做
# ======================================================================


@router.post(
    "/{session_id}/turns/{turn_id}/hint",
    summary="请求回答结构提示（会被记录）",
)
async def request_hint(
    session_id: str, turn_id: str, db: SessionDep, user: CurrentUser
) -> dict:
    session = await get_session_or_404(db, session_id, user.id)
    turn, hint_text = await update_turn_tracking(
        db=db, session=session, turn_id=turn_id, hinted=True
    )
    return {
        "turn_id": turn.id,
        "hint": hint_text,
        "already_used": hint_text is None,
        "hinted": turn.hinted,
        "message": (
            "本场第一次提示已给出。报告里会记录你使用过提示。"
            if hint_text
            else "这道题已经用过提示了。提示不会给答案，只给回答结构。"
        ),
    }


@router.post("/{session_id}/turns/{turn_id}/mark", summary="标记/取消标记这道题要复习")
async def mark_turn(
    session_id: str, turn_id: str, payload: TrackUpdateRequest, db: SessionDep, user: CurrentUser
) -> dict:
    session = await get_session_or_404(db, session_id, user.id)
    turn, _ = await update_turn_tracking(
        db=db, session=session, turn_id=turn_id, marked=payload.marked
    )
    return {"turn_id": turn.id, "marked": turn.marked}


@router.post(
    "/{session_id}/turns/{turn_id}/suggested-answer",
    summary="生成参考答案（按需，只生成一次）",
)
async def suggested_answer(
    session_id: str, turn_id: str, db: SessionDep, user: CurrentUser, ai: AIDep
) -> dict:
    """缺失事实时返回占位符而不是编造内容。生成结果会缓存，重复请求不重复计费。"""
    session = await get_session_or_404(db, session_id, user.id)
    turn, payload = await generate_suggested_answer(
        db=db, ai=ai, session=session, turn_id=turn_id
    )
    return {"turn_id": turn.id, "suggested_answer": payload}


@router.post("/{session_id}/pause", summary="暂停面试（暂停时间不计入时长）")
async def pause(session_id: str, db: SessionDep, user: CurrentUser) -> dict:
    session = await get_session_or_404(db, session_id, user.id)
    session = await pause_session(db=db, session=session)
    return {"ok": True, "status": session.status}


@router.post("/{session_id}/resume", summary="继续面试")
async def resume(session_id: str, db: SessionDep, user: CurrentUser) -> dict:
    session = await get_session_or_404(db, session_id, user.id)
    session = await resume_session(db=db, session=session)
    return {
        "ok": True,
        "status": session.status,
        "paused_seconds": int((session.config or {}).get("_paused_seconds", 0) or 0),
    }


# ======================================================================
# 结束 / 报告
# ======================================================================


@router.post("/{session_id}/finish", response_model=ReportPublic, summary="结束面试并生成报告")
async def finish(session_id: str, db: SessionDep, user: CurrentUser, ai: AIDep) -> ReportPublic:
    session = await get_session_or_404(db, session_id, user.id)
    report = await finish_session(db=db, ai=ai, session=session)
    return _report_public(report, session)


@router.post("/{session_id}/abort", summary="放弃本次面试")
async def abort(session_id: str, db: SessionDep, user: CurrentUser) -> dict:
    session = await get_session_or_404(db, session_id, user.id)
    if session.status == STATUS_FINISHED:
        raise InterviewStateError("这场面试已经结束，无法放弃")
    session.status = STATUS_ABORTED
    db.add(session)
    await db.commit()
    return {"ok": True, "status": session.status}


@router.get("/{session_id}/report", response_model=ReportPublic, summary="获取面试报告")
async def get_report(session_id: str, db: SessionDep, user: CurrentUser) -> ReportPublic:
    session = await get_session_or_404(db, session_id, user.id)
    report = (await db.exec(select(Report).where(Report.session_id == session.id))).first()
    if report is None:
        raise NotFoundError("本场面试还没有生成报告")
    return _report_public(report, session)
