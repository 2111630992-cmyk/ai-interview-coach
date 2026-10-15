"""面试编排服务。

把「状态机 + 持久化 + 评分 + 报告」从路由里抽出来，让路由只负责 HTTP 与 SSE 编码。

关键设计：
- **决策在服务端（deterministic），措辞在 LLM（streaming）** —— 见 interview_engine。
- **评分与提问并发** —— 追问的下一句不该等评分跑完，用户观感差别很大。
- 断流兜底：客户端断开时，已生成的那部分问题仍会落库，不留半截数据。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.constants import (
    DIMENSION_LABELS,
    DIMENSIONS,
    INTERVIEW_TYPES,
    LANGUAGES,
    STAGE_META,
    STAGES,
    STATUS_CREATED,
    STATUS_FINISHED,
    STATUS_PAUSED,
    STATUS_RUNNING,
)
from app.core.errors import InterviewStateError, NotFoundError
from app.interviewers import Interviewer, build_round_roster, get_interviewer
from app.models import InterviewSession, JobDescription, Report, Resume, Turn
from app.schemas.llm import Evaluation, InterviewPlan, ReportOut
from app.services.ai_types import (
    EvaluateContext,
    QuestionContext,
    ReportContext,
    SuggestedAnswerContext,
)
from app.services.interview_engine import TurnDecision, TurnView, decide_next

logger = logging.getLogger("app.interview")

NEUTRAL_SCORE = 3.0


# ======================================================================
# 查询辅助
# ======================================================================


async def get_session_or_404(db: AsyncSession, session_id: str, user_id: str) -> InterviewSession:
    session = (
        await db.exec(
            select(InterviewSession).where(
                InterviewSession.id == session_id, InterviewSession.user_id == user_id
            )
        )
    ).first()
    if session is None:
        # 不区分「不存在」与「不属于你」，避免越权探测
        raise NotFoundError("面试不存在")
    return session


async def get_turns(db: AsyncSession, session_id: str) -> list[Turn]:
    result = await db.exec(
        select(Turn).where(Turn.session_id == session_id).order_by(Turn.turn_index)
    )
    return list(result.all())


async def load_context_names(
    db: AsyncSession, sessions: list[InterviewSession]
) -> tuple[dict[str, str], dict[str, str]]:
    """批量取「简历名」与「JD 标题」，供列表页展示，避免 N+1 查询。

    返回 (resume_id -> filename, jd_id -> title)。
    """
    resume_ids = {s.resume_id for s in sessions if s.resume_id}
    jd_ids = {s.jd_id for s in sessions if s.jd_id}

    resume_names: dict[str, str] = {}
    if resume_ids:
        rows = await db.exec(select(Resume).where(Resume.id.in_(resume_ids)))  # type: ignore[attr-defined]
        resume_names = {r.id: r.filename for r in rows.all()}

    jd_titles: dict[str, str] = {}
    if jd_ids:
        rows = await db.exec(select(JobDescription).where(JobDescription.id.in_(jd_ids)))  # type: ignore[attr-defined]
        jd_titles = {j.id: j.title for j in rows.all()}

    return resume_names, jd_titles


def to_views(turns: list[Turn]) -> list[TurnView]:
    return [
        TurnView(
            question=t.question,
            answer=t.answer,
            stage=t.stage,
            competency=t.competency,
            is_followup=t.is_followup,
            followup_depth=t.followup_depth,
        )
        for t in turns
    ]


def elapsed_minutes(session: InterviewSession) -> float:
    if session.started_at is None:
        return 0.0
    started = session.started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - started).total_seconds() / 60)


def parse_plan(session: InterviewSession) -> InterviewPlan:
    return InterviewPlan.model_validate(session.plan or {})


# ======================================================================
# 创建会话
# ======================================================================


async def create_session(
    *,
    db: AsyncSession,
    user_id: str,
    resume: Resume,
    jd: JobDescription | None,
    config: dict,
    ai: Any,
) -> InterviewSession:
    job_title = jd.title if jd else "目标岗位"
    company = jd.company if jd else None
    jd_model = jd.competency_model if jd else None

    # 练习模式 = 每题即时反馈；模拟模式 = 全程隐藏分数
    # 把派生字段固化进 config，避免各处重复推导
    config = dict(config)
    config["realtime_feedback"] = config.get("feedback_mode") == "practice"

    plan = await ai.make_plan(
        resume_parsed=resume.parsed or {},
        jd_model=jd_model,
        job_title=job_title,
        company=company,
        config=config,
    )

    plan_summary = " → ".join(
        f"{STAGE_META[s['stage']]['label']}({int(s['weight'] * 100)}%)"
        for s in plan.model_dump().get("stages", [])
    )

    # 固化「环节 → 面试官」分配表：换面试官会同时改变提问口径与评分侧重
    roster = build_round_roster(
        stage_order=list(STAGES),
        mode=str(config.get("interviewer_mode", "panel")),
        single_type=config.get("interviewer_type"),
        language=str(config.get("language", "zh")),
    )

    session = InterviewSession(
        user_id=user_id,
        resume_id=resume.id,
        jd_id=jd.id if jd else None,
        config=config,
        plan=plan.model_dump(),
        plan_summary=plan_summary,
        roster=roster,
        status=STATUS_CREATED,
        current_stage=None,
        current_turn_index=0,
        started_at=datetime.now(timezone.utc),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


def roster_interviewer(session: InterviewSession, stage: str) -> Interviewer | None:
    """从固化的人格分配表里取出该环节的面试官。"""
    entry = (session.roster or {}).get(stage)
    if not entry:
        return None
    try:
        return get_interviewer(str(entry.get("type") or ""), _language_of(session))
    except Exception:
        return None


def _language_of(session: InterviewSession) -> str:
    return str((session.config or {}).get("language", "zh"))


# ======================================================================
# 生成问题上下文
# ======================================================================


def build_question_context(
    *,
    session: InterviewSession,
    plan: InterviewPlan,
    turns: list[TurnView],
    decision: TurnDecision,
    resume_parsed: dict,
    job_title: str,
    company: str | None,
    previous_interviewer: str | None = None,
) -> QuestionContext:
    config = session.config or {}
    covered = {t.competency for t in turns if t.competency and not t.is_followup}
    remaining = [c.name for c in plan.competencies if c.name not in covered]
    duration_min = int(config.get("duration_min", 30))

    interviewer = roster_interviewer(session, decision.stage)
    # 追问不换人；只有进入新环节且面试官不同才算换人
    changed = (
        interviewer is not None
        and not decision.is_followup
        and previous_interviewer is not None
        and previous_interviewer != interviewer.type
    )

    return QuestionContext(
        intent=decision.intent,
        stage=decision.stage,
        competency=decision.competency,
        probe_questions=decision.probe_questions,
        turns=turns,
        job_title=job_title,
        company=company,
        interview_type_label=INTERVIEW_TYPES.get(
            config.get("interview_type", "comprehensive"), "面试"
        ),
        difficulty_label={"intern": "实习", "campus": "校招", "bigtech": "大厂"}.get(
            config.get("difficulty", "campus"), "校招"
        ),
        elapsed_min=elapsed_minutes(session),
        duration_min=duration_min,
        remaining_competencies=remaining,
        pressure_mode=bool(config.get("pressure_mode", True)),
        language_label=LANGUAGES.get(config.get("language", "zh"), "中文"),
        plan_summary=session.plan_summary,
        resume_highlights=list((resume_parsed or {}).get("highlights") or []),
        interviewer=interviewer,
        interviewer_changed=changed,
    )


# ======================================================================
# 单题评分
# ======================================================================


async def evaluate_turn(
    *,
    ai: Any,
    question: str,
    answer: str,
    stage: str,
    competency: str | None,
    job_title: str,
    jd_model: dict | None,
    answer_latency_ms: int | None,
    delivery_metrics: dict | None = None,
    interviewer_response: str | None = None,
    skipped: bool = False,
    interviewer: Interviewer | None = None,
) -> Evaluation:
    """评分失败不应该让整场面试崩掉：降级为中性分并打日志。"""
    try:
        return await ai.evaluate(
            EvaluateContext(
                question=question,
                answer=answer,
                stage=stage,
                competency=competency,
                job_title=job_title,
                jd_model=jd_model,
                answer_latency_ms=answer_latency_ms,
                delivery_metrics=delivery_metrics,
                interviewer_response=interviewer_response,
                skipped=skipped,
                interviewer=interviewer,
            )
        )
    except Exception as exc:
        logger.error("单题评分失败，降级为中性分：%s", exc)
        return Evaluation(
            relevance=NEUTRAL_SCORE,
            structure=NEUTRAL_SCORE,
            depth=NEUTRAL_SCORE,
            delivery=NEUTRAL_SCORE,
            fit=NEUTRAL_SCORE,
            evidence=[],
            strengths=[],
            problems=[],
            risk_points=[],
            rewritten_answer="（本题评分服务异常，未生成改写示范）",
            is_weak=False,
        )


# ======================================================================
# 轮次编排（供 SSE 使用）
# ======================================================================


@dataclass
class TurnStreamResult:
    turn: Turn
    evaluation: Evaluation | None
    decision: TurnDecision


# 后台任务集合：保持强引用，避免被 GC 提前回收
_BACKGROUND_TASKS: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


async def _persist_evaluation(turn_id: str, evaluation: Evaluation) -> None:
    """用独立会话写入评分。

    用于客户端中途断流、原请求会话可能已关闭的场景。
    """
    from sqlmodel.ext.asyncio.session import AsyncSession as FreshSession

    from app.core.db import engine

    try:
        async with FreshSession(engine, expire_on_commit=False) as db:
            turn = (await db.exec(select(Turn).where(Turn.id == turn_id))).first()
            if turn is not None:
                turn.evaluation = evaluation.model_dump()
                db.add(turn)
                await db.commit()
    except Exception as exc:
        logger.error("后台写入评分失败(turn=%s): %s", turn_id, exc)


async def _await_and_persist(turn_id: str, task: asyncio.Task[Evaluation]) -> None:
    try:
        evaluation = await task
    except Exception as exc:
        logger.error("后台评分任务失败(turn=%s): %s", turn_id, exc)
        return
    await _persist_evaluation(turn_id, evaluation)


async def advance_turn(
    *,
    db: AsyncSession,
    ai: Any,
    session: InterviewSession,
    answer: str | None,
    client_elapsed_ms: int | None = None,
    delivery_metrics: dict | None = None,
    recording_key: str | None = None,
    skipped: bool = False,
) -> AsyncIterator[tuple[str, Any]]:
    """推进一轮面试，产出事件流。

    产出 `("token", 文本片段)` 若干次，最后产出一次 `("result", TurnStreamResult)`。

    流程：
    1. （可选）把 answer 落库到当前待答轮次，并**并发**发起评分 —— 不阻塞提问
    2. 用确定性引擎算出本轮动作（追问 or 换考察点 or 收尾）
    3. 流式生成面试官话术，边生成边抛出 token
    4. 落库新轮次；等待评分结果并落库
       若客户端中途断流，评分任务转入后台用独立会话写入，不丢数据
    """
    turns = await get_turns(db, session.id)
    plan = parse_plan(session)

    jd = None
    if session.jd_id:
        jd = (
            await db.exec(select(JobDescription).where(JobDescription.id == session.jd_id))
        ).first()
    resume = (await db.exec(select(Resume).where(Resume.id == session.resume_id))).first()
    resume_parsed = (resume.parsed if resume else {}) or {}
    job_title = jd.title if jd else "目标岗位"
    company = jd.company if jd else None
    jd_model = jd.competency_model if jd else None

    # ---------- 1. 记录本次回答并并发起评分 ----------
    eval_task: asyncio.Task[Evaluation] | None = None
    answered_turn: Turn | None = None
    if answer is not None:
        if not turns:
            raise InterviewStateError("面试尚未开始，无法提交回答")
        current = turns[-1]
        if current.answer:
            raise InterviewStateError("当前问题已经回答过了，请获取下一题")
        current.answer = answer
        current.answer_latency_ms = client_elapsed_ms
        current.delivery_metrics = delivery_metrics or None
        current.recording_key = recording_key or None
        current.skipped = skipped
        db.add(current)
        await db.commit()
        await db.refresh(current)
        answered_turn = current

        # 评分时把「面试官听到后实际追问了什么」一并给它 —— 让分数反映真实交锋
        eval_task = asyncio.create_task(
            evaluate_turn(
                ai=ai,
                question=current.question,
                answer=answer,
                stage=current.stage,
                competency=current.competency,
                job_title=job_title,
                jd_model=jd_model,
                answer_latency_ms=client_elapsed_ms,
                delivery_metrics=delivery_metrics or None,
                skipped=skipped,
                interviewer=roster_interviewer(session, current.stage),
            )
        )

    # ---------- 2. 决策 ----------
    decision = decide_next(
        plan=plan,
        config=session.config or {},
        turns=to_views(turns),
        elapsed_min=elapsed_minutes(session),
    )

    # ---------- 2a. 面试结束 ----------
    if decision.session_finished:
        evaluation: Evaluation | None = None
        if eval_task is not None and answered_turn is not None:
            evaluation = await eval_task
            answered_turn.evaluation = evaluation.model_dump()
            db.add(answered_turn)
            await db.commit()
        yield (
            "result",
            TurnStreamResult(
                turn=turns[-1] if turns else _placeholder_turn(session),
                evaluation=evaluation,
                decision=decision,
            ),
        )
        return

    # ---------- 3. 流式生成问题 ----------
    ctx = build_question_context(
        session=session,
        plan=plan,
        turns=to_views(turns),
        decision=decision,
        resume_parsed=resume_parsed,
        job_title=job_title,
        company=company,
        previous_interviewer=turns[-1].interviewer if turns else None,
    )

    buffer: list[str] = []
    finished_stream = False
    try:
        async for piece in ai.stream_question(ctx):
            buffer.append(piece)
            yield ("token", piece)
        finished_stream = True
    finally:
        # 无论正常结束还是客户端断流，都把已生成的内容落库，
        # 避免"问题只存在于浏览器里，刷新就丢"
        text = "".join(buffer).strip() or _fallback_question(decision)
        if not buffer:
            logger.warning("面试官生成空内容，使用兜底问题：%s", text)

        new_turn = Turn(
            session_id=session.id,
            turn_index=(turns[-1].turn_index + 1) if turns else 1,
            stage=decision.stage,
            competency=decision.competency,
            parent_turn_id=(turns[-1].id if (turns and decision.is_followup) else None),
            followup_depth=decision.followup_depth,
            is_followup=decision.is_followup,
            question=text,
            internal_note=decision.reason,
            interviewer=ctx.interviewer.type if ctx.interviewer else None,
        )
        db.add(new_turn)
        session.current_stage = decision.stage
        session.current_turn_index = new_turn.turn_index
        if session.status == STATUS_CREATED:
            session.status = STATUS_RUNNING
        db.add(session)
        await db.commit()
        await db.refresh(new_turn)

        # 客户端断流：评分任务移交后台，用独立会话落库
        if eval_task is not None and not finished_stream and answered_turn is not None:
            _spawn(_await_and_persist(answered_turn.id, eval_task))

    # ---------- 4. 等待评分并落库 ----------
    evaluation: Evaluation | None = None
    if eval_task is not None and answered_turn is not None:
        evaluation = await eval_task
        answered_turn.evaluation = evaluation.model_dump()
        db.add(answered_turn)
        await db.commit()

    yield (
        "result",
        TurnStreamResult(turn=new_turn, evaluation=evaluation, decision=decision),
    )


def _placeholder_turn(session: InterviewSession) -> Turn:
    return Turn(
        session_id=session.id,
        turn_index=session.current_turn_index,
        stage=session.current_stage or "intro",
        question="",
    )


_FALLBACK_BY_STAGE: dict[str, str] = {
    "intro": "请先做一个 1 分钟的自我介绍，重点讲和你应聘岗位最相关的经历。",
    "resume_deep_dive": "挑一个你投入最多的项目，讲讲你具体负责了哪一部分？",
    "hard_skill": "结合你的项目经历，讲讲你最熟悉的一项技术，以及你在上面做过的一个具体优化。",
    "behavioral": "讲一次你和队友出现分歧的经历，你当时是怎么处理的？",
    "pressure": "你刚才提到的那些数据，是怎么统计出来的？",
    "candidate_ask": "你有什么想问我的吗？",
}


def _fallback_question(decision: TurnDecision) -> str:
    return _FALLBACK_BY_STAGE.get(decision.stage, "请继续讲讲你在这方面的经历。")


# ======================================================================
# 分数聚合与报告
# ======================================================================


def aggregate_scores(turns: list[Turn]) -> tuple[float, dict[str, float]]:
    """把逐题评分聚合成五维均分（0-100）与加权总分（0-100）。"""
    evaluated = [t for t in turns if t.evaluation]
    if not evaluated:
        return 0.0, {d: 0.0 for d in DIMENSIONS}

    totals = {d: 0.0 for d in DIMENSIONS}
    weighted_total = 0.0
    for t in evaluated:
        ev = Evaluation.model_validate(t.evaluation)
        for d in DIMENSIONS:
            totals[d] += ev.dimension_100(d)
        weighted_total += ev.to_100()

    n = len(evaluated)
    return round(weighted_total / n, 1), {d: round(totals[d] / n, 1) for d in DIMENSIONS}


def summarize_delivery(turns: list[Turn]) -> dict:
    """汇总整场的客观表达指标。

    只在确实有语音作答时才有意义；纯文字面试返回 {"is_voice": False}，
    这样报告提示词和前端都不会拿到误导性的"语速 0 字/分钟"。
    """
    voice_turns = [
        t
        for t in turns
        if (t.delivery_metrics or {}).get("transcript_source") in ("asr", "mixed")
        and (t.delivery_metrics or {}).get("duration_ms")
    ]
    if not voice_turns:
        return {"is_voice": False}

    n = len(voice_turns)

    def _avg(key: str) -> float:
        return sum(float((t.delivery_metrics or {}).get(key) or 0) for t in voice_turns) / n

    total_ms = sum(int((t.delivery_metrics or {}).get("duration_ms") or 0) for t in voice_turns)
    return {
        "is_voice": True,
        "answered_voice_turns": n,
        "total_speaking_ms": total_ms,
        "avg_speech_rate": round(_avg("speech_rate"), 1),
        "avg_filler_ratio": round(_avg("filler_ratio"), 4),
        "total_filler_count": sum(
            int((t.delivery_metrics or {}).get("filler_count") or 0) for t in voice_turns
        ),
        "total_long_pauses": sum(
            int((t.delivery_metrics or {}).get("long_pause_count") or 0) for t in voice_turns
        ),
        "longest_pause_ms": max(
            int((t.delivery_metrics or {}).get("longest_pause_ms") or 0) for t in voice_turns
        ),
    }


async def finish_session(*, db: AsyncSession, ai: Any, session: InterviewSession) -> Report:
    """生成面试报告。已生成过则直接返回（幂等）。"""
    existing = (
        await db.exec(select(Report).where(Report.session_id == session.id))
    ).first()
    if existing is not None:
        return existing

    turns = await get_turns(db, session.id)
    if not any(t.answer for t in turns):
        raise InterviewStateError("本场面试还没有任何回答，无法生成报告")

    total_score, dimensions = aggregate_scores(turns)
    delivery_summary = summarize_delivery(turns)
    # 诚实机制：把「用了多少次提示 / 跳过了几题」记进报告，避免自欺
    honesty = {
        "hint_count": sum(1 for t in turns if t.hinted),
        "skip_count": sum(1 for t in turns if t.skipped),
        "marked_count": sum(1 for t in turns if t.marked),
    }

    jd = None
    if session.jd_id:
        jd = (await db.exec(select(JobDescription).where(JobDescription.id == session.jd_id))).first()

    ctx = ReportContext(
        job_title=jd.title if jd else "目标岗位",
        company=jd.company if jd else None,
        config=session.config or {},
        turns=[
            {
                "turn_index": t.turn_index,
                "stage": t.stage,
                "competency": t.competency,
                "question": t.question,
                "answer": t.answer,
                "evaluation": t.evaluation,
                "hinted": t.hinted,
                "skipped": t.skipped,
                "delivery_metrics": t.delivery_metrics,
                "interviewer": (
                    roster_interviewer(session, t.stage).name
                    if roster_interviewer(session, t.stage)
                    else None
                ),
            }
            for t in turns
            if t.answer or t.skipped
        ],
        dimension_scores=dimensions,
        total_score=total_score,
        jd_model=jd.competency_model if jd else None,
        delivery_summary=delivery_summary,
    )

    try:
        report_out: ReportOut = await ai.make_report(ctx)
    except Exception as exc:
        logger.error("报告生成失败，降级为本地汇总：%s", exc)
        report_out = _fallback_report(total_score, dimensions, turns)

    report = Report(
        session_id=session.id,
        user_id=session.user_id,
        verdict=report_out.verdict,
        verdict_label={
            "strong_pass": "强烈推荐通过",
            "pass": "可以通过",
            "borderline": "边缘，需补强",
            "fail": "不通过",
        }.get(report_out.verdict, ""),
        summary=report_out.summary,
        dimension_scores=dimensions,
        top_problems=[p.model_dump() for p in report_out.top_problems],
        per_turn_feedback=_per_turn_feedback(turns, session),
        training_plan=[d.model_dump() for d in report_out.training_plan],
    )
    db.add(report)

    session.status = STATUS_FINISHED
    session.finished_at = datetime.now(timezone.utc)
    session.total_score = total_score
    session.dimensions = dimensions
    session.delivery_summary = delivery_summary
    # 诚实机制：用了多少提示、跳过几题，写进 config 供报告页展示
    cfg = dict(session.config or {})
    cfg["_honesty"] = honesty
    session.config = cfg
    db.add(session)
    await db.commit()
    await db.refresh(report)
    return report


def _per_turn_feedback(turns: list[Turn], session: InterviewSession) -> list[dict]:
    out: list[dict] = []
    for t in turns:
        if not t.answer and not t.skipped:
            continue
        ev = t.evaluation or {}
        speaker = roster_interviewer(session, t.stage)
        out.append(
            {
                "turn_id": t.id,
                "turn_index": t.turn_index,
                "stage": t.stage,
                "stage_label": STAGE_META.get(t.stage, {}).get("label", t.stage),
                "competency": t.competency,
                "question": t.question,
                "answer": t.answer,
                "is_followup": t.is_followup,
                "followup_depth": t.followup_depth,
                "interviewer_name": speaker.name if speaker else None,
                "interviewer_title": speaker.title if speaker else None,
                "hinted": t.hinted,
                "skipped": t.skipped,
                "marked": t.marked,
                "delivery_metrics": t.delivery_metrics,
                "recording_key": t.recording_key,
                "scores": {d: ev.get(d) for d in DIMENSIONS},
                "weighted_score": (
                    Evaluation.model_validate(ev).weighted_score() if ev else None
                ),
                "evidence": ev.get("evidence") or [],
                "strengths": ev.get("strengths") or [],
                "problems": ev.get("problems") or [],
                "risk_points": ev.get("risk_points") or [],
                "rewritten_answer": ev.get("rewritten_answer") or "",
            }
        )
    return out


def _fallback_report(
    total_score: float, dimensions: dict[str, float], turns: list[Turn]
) -> ReportOut:
    """报告服务不可用时的本地汇总，保证用户不会拿到空白页。"""
    dim_line = "、".join(
        f"{DIMENSION_LABELS.get(d, d)} {v:.0f}" for d, v in dimensions.items()
    )
    answered = sum(1 for t in turns if t.answer)
    from app.schemas.llm import TopProblem, TrainingDay

    return ReportOut(
        verdict=(
            "pass" if total_score >= 65 else "borderline" if total_score >= 50 else "fail"
        ),
        summary=(
            f"（报告生成服务异常，以下为本地自动汇总）本场共回答 {answered} 题，"
            f"加权总分 {total_score:.0f}/100，五维得分 {dim_line}。"
            "单题点评仍在下方逐题卡片中可见，请重点复看被追问最多的那几道题。"
        ),
        top_problems=[
            TopProblem(
                title="报告生成服务异常",
                evidence="（自动汇总）",
                why_bad="未能生成 AI 复盘分析，无法定位深层问题。",
                how_to_fix="稍后在历史记录中重新生成本场报告，或先按逐题点评自行复盘。",
                demo_answer="",
            )
        ],
        training_plan=[
            TrainingDay(
                day=i + 1,
                task="复看本场逐题点评，把每道题的「问题」逐条改写成新的回答并录音",
                goal="把本场暴露的问题转化为可复用的表达模板",
                link_competency="综合演练",
            )
            for i in range(7)
        ],
    )


# ======================================================================
# 提示 / 标记 / 跳过 / 参考答案
# ======================================================================


# 「提示」给的是**回答结构**，不是答案本身。
# 这是刻意的：给答案等于帮他作弊，给结构才是教他怎么想。
_HINT_BY_STAGE: dict[str, str] = {
    "intro": "按「一句话定位 + 1 个最相关经历 + 与岗位的连接」组织，控制在 60 秒内，不要复述简历。",
    "resume_deep_dive": "按「背景一句 → 我的具体职责 → 2-3 个我实际做的动作 → 量化结果」组织。关键是让面试官听出哪部分是你做的。",
    "hard_skill": "按「它是什么 → 我在哪用过 → 为什么选它而不是另一个 → 边界或踩过的坑」组织。只答一半就只能拿一半分。",
    "behavioral": "用 STAR：情境（什么时候、什么背景）→ 任务（你要解决什么）→ 行动（你具体做了什么）→ 结果（可衡量的变化）。别讲假设，讲发生过的事。",
    "pressure": "被质疑时不要慌也不要硬撑：先承认前提（「这个数字是压测环境下的」），再给出你的依据和适用边界。诚实比完美更能得分。",
    "candidate_ask": "问一个只有内部人才答得上来的问题，例如团队当前最大的技术挑战、这个岗位半年内的核心目标。不要问加班和薪资。",
}


def hint_for_stage(stage: str) -> str:
    return _HINT_BY_STAGE.get(
        stage, "按「结论先行 → 具体做法 → 量化结果 → 一句反思」组织，先给结论能显著提高听感。"
    )


async def update_turn_tracking(
    *,
    db: AsyncSession,
    session: InterviewSession,
    turn_id: str,
    marked: bool | None = None,
    hinted: bool | None = None,
) -> tuple[Turn, str | None]:
    """更新「标记复习 / 使用提示」。

    提示是**只增不减**的：一旦用过就永久记录，防止"看完提示再取消勾选"自欺。
    返回 (turn, hint_text)；hint_text 仅在本次首次请求提示时非空。
    """
    turns = await get_turns(db, session.id)
    turn = next((t for t in turns if t.id == turn_id), None)
    if turn is None:
        raise NotFoundError("该题目不存在")

    if marked is not None:
        turn.marked = marked

    hint_text: str | None = None
    if hinted:
        if session.config and not session.config.get("allow_hint", True):
            raise InterviewStateError("本场面试未开启提示功能")
        if not turn.hinted:
            hint_text = hint_for_stage(turn.stage)
        turn.hinted = True

    db.add(turn)
    await db.commit()
    await db.refresh(turn)
    return turn, hint_text


async def generate_suggested_answer(
    *,
    db: AsyncSession,
    ai: Any,
    session: InterviewSession,
    turn_id: str,
) -> tuple[Turn, dict]:
    """按需生成参考答案，并**缓存进 turn**（同一题永远只花一次模型调用）。"""
    turns = await get_turns(db, session.id)
    turn = next((t for t in turns if t.id == turn_id), None)
    if turn is None:
        raise NotFoundError("该题目不存在")

    # 幂等：已生成过直接返回
    if turn.suggested_answer:
        return turn, turn.suggested_answer

    if not turn.answer:
        raise InterviewStateError("这道题还没有作答，无法生成参考答案")
    if not turn.evaluation:
        raise InterviewStateError("评分还在进行中，请稍等几秒后再看参考答案")

    jd = None
    if session.jd_id:
        jd = (
            await db.exec(select(JobDescription).where(JobDescription.id == session.jd_id))
        ).first()
    resume = (await db.exec(select(Resume).where(Resume.id == session.resume_id))).first()

    speaker = roster_interviewer(session, turn.stage)
    evaluation = Evaluation.model_validate(turn.evaluation)

    try:
        result = await ai.make_suggested_answer(
            SuggestedAnswerContext(
                question=turn.question,
                answer=turn.answer,
                job_title=jd.title if jd else "目标岗位",
                interviewer_name=speaker.name if speaker else "面试官",
                interviewer_focus=list(speaker.focus_areas) if speaker else [],
                jd_model=jd.competency_model if jd else None,
                resume_highlights=list(((resume.parsed if resume else {}) or {}).get("highlights") or []),
                evidence=list(evaluation.evidence or []),
            )
        )
    except Exception as exc:
        logger.error("参考答案生成失败(turn=%s)：%s", turn_id, exc)
        raise InterviewStateError("参考答案生成失败，请稍后重试") from exc

    payload = {
        "outline": result.outline,
        "key_points": result.key_points,
        "improvements": result.improvements,
        "reference_answer": result.reference_answer,
        "placeholders": result.placeholders,
        "generated_at": result.generated_at or datetime.now(timezone.utc).isoformat(),
    }
    turn.suggested_answer = payload
    db.add(turn)
    await db.commit()
    await db.refresh(turn)
    return turn, payload


async def skip_current_question(
    *,
    db: AsyncSession,
    ai: Any,
    session: InterviewSession,
    reason: str,
    client_elapsed_ms: int | None = None,
) -> AsyncIterator[tuple[str, Any]]:
    """跳过当前题并推进到下一题。

    跳过记 0 分但不中断面试 —— 真实面试里答不出来也要继续往下走，
    让学生因为一道题卡死而放弃整场是产品设计的失败。
    """
    marker = "（候选人主动跳过此题）"
    if reason.strip():
        marker = f"（候选人主动跳过此题，说明：{reason.strip()[:200]}）"
    async for event in advance_turn(
        db=db,
        ai=ai,
        session=session,
        answer=marker,
        client_elapsed_ms=client_elapsed_ms,
        skipped=True,
    ):
        yield event


# ======================================================================
# 暂停 / 继续
# ======================================================================


async def pause_session(*, db: AsyncSession, session: InterviewSession) -> InterviewSession:
    """暂停面试。

    暂停期间不计入面试时长 —— 否则学生暂停 10 分钟回来会发现时间被吃光了。
    """
    if session.status == STATUS_FINISHED:
        raise InterviewStateError("面试已经结束，无法暂停")
    if session.status == STATUS_PAUSED:
        return session

    cfg = dict(session.config or {})
    cfg["_paused_at"] = datetime.now(timezone.utc).isoformat()
    session.config = cfg
    session.status = STATUS_PAUSED
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def resume_session(*, db: AsyncSession, session: InterviewSession) -> InterviewSession:
    """继续面试，并把暂停时长从「已用时间」里扣掉。"""
    cfg = dict(session.config or {})
    paused_at_raw = cfg.pop("_paused_at", None)
    if paused_at_raw and session.started_at is not None:
        try:
            paused_at = datetime.fromisoformat(str(paused_at_raw))
            if paused_at.tzinfo is None:
                paused_at = paused_at.replace(tzinfo=timezone.utc)
            paused_s = (datetime.now(timezone.utc) - paused_at).total_seconds()
            cfg["_paused_seconds"] = int(cfg.get("_paused_seconds", 0) or 0) + max(0, int(paused_s))
            # 把开始时间整体后移，等价于"这段时间没发生"
            session.started_at = session.started_at + timedelta(seconds=max(0, int(paused_s)))
            if session.started_at.tzinfo is None:
                session.started_at = session.started_at.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            logger.warning("暂停时间解析失败，跳过时长补偿")

    session.config = cfg
    session.status = STATUS_RUNNING
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session
