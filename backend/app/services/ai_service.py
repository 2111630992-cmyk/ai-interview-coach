"""真实 LLM 实现。

每个方法负责：拼提示词 → 调传输层 → 拿回强类型对象。
业务逻辑（该问什么、怎么算分）不在这里，见 interview_engine.py 与 api 层。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from app.constants import (
    DIFFICULTIES,
    DIMENSION_LABELS,
    INTERVIEW_TYPES,
    LANGUAGES,
)
from app.schemas.llm import (
    Evaluation,
    InterviewPlan,
    JDParse,
    MatchOut,
    ReportOut,
    ResumeParse,
    SuggestedAnswer,
)
from app.services import prompts
from app.services.ai_types import (
    EvaluateContext,
    QuestionContext,
    ReportContext,
    SuggestedAnswerContext,
)
from app.services.llm_client import LLMTransport

logger = logging.getLogger("app.ai")


class AIService:
    """基于 OpenAI 兼容端点的实现。"""

    is_mock = False

    def __init__(self, transport: LLMTransport) -> None:
        self.transport = transport

    def usage_snapshot(self) -> dict:
        return self.transport.usage.as_dict()

    # ------------------------------------------------------------------
    # 解析类
    # ------------------------------------------------------------------
    async def parse_resume(self, raw_text: str) -> ResumeParse:
        return await self.transport.complete_json(
            system=prompts.RESUME_PARSE_SYSTEM,
            user=prompts.resume_parse_user(raw_text),
            schema=ResumeParse,
            task="resume_parse",
            temperature=0.1,
        )

    async def analyze_jd(self, title: str, company: str | None, raw_text: str) -> JDParse:
        return await self.transport.complete_json(
            system=prompts.JD_PARSE_SYSTEM,
            user=prompts.jd_parse_user(title, company, raw_text),
            schema=JDParse,
            task="jd_parse",
            temperature=0.2,
        )

    async def match(
        self,
        *,
        resume_parsed: dict,
        jd_model: dict,
        job_title: str,
        company: str | None,
    ) -> MatchOut:
        return await self.transport.complete_json(
            system=prompts.MATCH_SYSTEM,
            user=prompts.match_user(resume_parsed, jd_model, job_title, company),
            schema=MatchOut,
            task="match",
            temperature=0.2,
        )

    # ------------------------------------------------------------------
    # 面试计划
    # ------------------------------------------------------------------
    async def make_plan(
        self,
        *,
        resume_parsed: dict,
        jd_model: dict | None,
        job_title: str,
        company: str | None,
        config: dict,
    ) -> InterviewPlan:
        return await self.transport.complete_json(
            system=prompts.PLAN_SYSTEM,
            user=prompts.plan_user(
                resume_parsed=resume_parsed,
                jd_model=jd_model,
                job_title=job_title,
                company=company,
                config=config,
                language_label=LANGUAGES.get(config.get("language", "zh"), "中文"),
                difficulty_label=DIFFICULTIES.get(config.get("difficulty", "campus"), "校招"),
                interview_type_label=INTERVIEW_TYPES.get(
                    config.get("interview_type", "comprehensive"), "综合终面"
                ),
            ),
            schema=InterviewPlan,
            task="plan",
            temperature=0.4,
        )

    # ------------------------------------------------------------------
    # 面试官措辞（流式纯文本）
    # ------------------------------------------------------------------
    async def stream_question(self, ctx: QuestionContext) -> AsyncIterator[str]:
        # 面试官人格注入系统提示词：人格只改变「怎么问」，不改变「问什么」
        system = prompts.build_question_system(ctx.interviewer)
        user = self._question_user(ctx)
        async for piece in self.transport.stream_text(
            system=system,
            user=user,
            task="interviewer",
            temperature=0.7,
        ):
            yield piece

    def _question_user(self, ctx: QuestionContext) -> str:
        return prompts.question_user(
            intent=ctx.intent,
            stage=ctx.stage,
            competency=ctx.competency,
            probe_questions=ctx.probe_questions,
            turns=ctx.turns,
            job_title=ctx.job_title,
            company=ctx.company,
            interview_type_label=ctx.interview_type_label,
            difficulty_label=ctx.difficulty_label,
            elapsed_min=ctx.elapsed_min,
            duration_min=ctx.duration_min,
            remaining_competencies=ctx.remaining_competencies,
            pressure_mode=ctx.pressure_mode,
            language_label=ctx.language_label,
            plan_summary=ctx.plan_summary,
            resume_highlights=ctx.resume_highlights,
            interviewer_changed=ctx.interviewer_changed,
        )

    # ------------------------------------------------------------------
    # 评分（独立调用，低温度）
    # ------------------------------------------------------------------
    async def evaluate(self, ctx: EvaluateContext) -> Evaluation:
        return await self.transport.complete_json(
            system=prompts.build_evaluator_system(ctx.interviewer),
            user=prompts.evaluator_user(
                question=ctx.question,
                answer=ctx.answer,
                stage=ctx.stage,
                competency=ctx.competency,
                job_title=ctx.job_title,
                jd_model=ctx.jd_model,
                answer_latency_ms=ctx.answer_latency_ms,
                delivery_metrics=ctx.delivery_metrics,
                interviewer_response=ctx.interviewer_response,
                skipped=ctx.skipped,
            ),
            schema=Evaluation,
            task="evaluator",
            temperature=0.2,
            model=self.transport.cfg.eval_model,
        )

    # ------------------------------------------------------------------
    # 参考答案（按需生成）
    # ------------------------------------------------------------------
    async def make_suggested_answer(self, ctx: SuggestedAnswerContext) -> SuggestedAnswer:
        return await self.transport.complete_json(
            system=prompts.SUGGESTED_ANSWER_SYSTEM,
            user=prompts.suggested_answer_user(
                question=ctx.question,
                answer=ctx.answer,
                job_title=ctx.job_title,
                jd_model=ctx.jd_model,
                interviewer_name=ctx.interviewer_name,
                interviewer_focus=ctx.interviewer_focus,
                resume_highlights=ctx.resume_highlights,
                evidence=ctx.evidence,
            ),
            schema=SuggestedAnswer,
            task="suggested_answer",
            temperature=0.3,
            model=self.transport.cfg.eval_model,
        )

    # ------------------------------------------------------------------
    # 报告
    # ------------------------------------------------------------------
    async def make_report(self, ctx: ReportContext) -> ReportOut:
        return await self.transport.complete_json(
            system=prompts.REPORTER_SYSTEM,
            user=prompts.reporter_user(
                job_title=ctx.job_title,
                company=ctx.company,
                config=ctx.config,
                turns=ctx.turns,
                dimension_scores=ctx.dimension_scores,
                total_score=ctx.total_score,
                jd_model=ctx.jd_model,
                delivery_summary=ctx.delivery_summary,
            ),
            schema=ReportOut,
            task="report",
            temperature=0.3,
            model=self.transport.cfg.eval_model,
        )


def dimension_score_100(evaluation: Evaluation) -> dict[str, float]:
    """把单题五维映射到 0-100，供报告雷达图使用。"""
    return {d: evaluation.dimension_100(d) for d in DIMENSION_LABELS}
