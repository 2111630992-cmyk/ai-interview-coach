"""AI 服务层共享的上下文类型与接口。

真实实现（ai_service.AIService）与 Mock 实现（mock_ai.MockAIService）
实现同一组方法，因此上层路由完全不需要知道当前跑的是哪一个。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.interviewers import Interviewer


@dataclass
class QuestionContext:
    """生成「面试官这一轮说什么」所需的全部上下文。"""

    intent: str
    stage: str
    competency: str | None
    probe_questions: list[str]
    turns: list[Any]
    job_title: str
    company: str | None
    interview_type_label: str
    difficulty_label: str
    elapsed_min: float
    duration_min: int
    remaining_competencies: list[str]
    pressure_mode: bool
    language_label: str = "中文"
    plan_summary: str = ""
    resume_highlights: list[str] = field(default_factory=list)
    # 本轮由哪位面试官发问（人格会改变提问口径）
    interviewer: Interviewer | None = None
    # 本轮换了面试官（多轮模式）—— 需要一句话自我介绍，否则考生会一头雾水
    interviewer_changed: bool = False


@dataclass
class EvaluateContext:
    question: str
    answer: str
    stage: str
    competency: str | None
    job_title: str
    jd_model: dict | None = None
    answer_latency_ms: int | None = None
    # 客观表达指标（视频/语音作答才有值）
    delivery_metrics: dict | None = None
    # 面试官听到这个回答后实际追问的内容 —— 让评分反映真实交锋而非孤立判断
    interviewer_response: str | None = None
    # 候选人主动跳过
    skipped: bool = False
    interviewer: Interviewer | None = None


@dataclass
class SuggestedAnswerContext:
    question: str
    answer: str
    job_title: str
    interviewer_name: str
    interviewer_focus: list[str] = field(default_factory=list)
    jd_model: dict | None = None
    resume_highlights: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)


@dataclass
class ReportContext:
    job_title: str
    company: str | None
    config: dict
    turns: list[dict]
    dimension_scores: dict[str, float]
    total_score: float
    jd_model: dict | None = None
    # 视频面试的表达指标汇总，报告里单独成段
    delivery_summary: dict | None = None


class AIServiceProtocol(Protocol):
    """AI 服务接口。所有方法都不应抛裸异常，失败请抛 core.errors.AppError 子类。"""

    is_mock: bool

    async def parse_resume(self, raw_text: str): ...

    async def analyze_jd(self, title: str, company: str | None, raw_text: str): ...

    async def match(
        self,
        *,
        resume_parsed: dict,
        jd_model: dict,
        job_title: str,
        company: str | None,
    ): ...

    async def make_plan(self, **kwargs) -> Any: ...

    def stream_question(self, ctx: QuestionContext) -> AsyncIterator[str]: ...

    async def evaluate(self, ctx: EvaluateContext): ...

    async def make_suggested_answer(self, ctx: SuggestedAnswerContext): ...

    async def make_report(self, ctx: ReportContext): ...

    def usage_snapshot(self) -> dict: ...


def usage_delta(before: dict, after: dict) -> dict:
    """计算一次请求消耗的 token 增量。"""

    def _g(d: dict, k: str) -> int:
        return int(d.get(k, 0) or 0)

    by_task: dict[str, int] = {}
    b_task, a_task = before.get("by_task", {}), after.get("by_task", {})
    for k, v in a_task.items():
        d = int(v) - int(b_task.get(k, 0))
        if d:
            by_task[k] = d

    return {
        "prompt_tokens": _g(after, "prompt_tokens") - _g(before, "prompt_tokens"),
        "completion_tokens": _g(after, "completion_tokens") - _g(before, "completion_tokens"),
        "total_tokens": _g(after, "total_tokens") - _g(before, "total_tokens"),
        "calls": _g(after, "calls") - _g(before, "calls"),
        "by_task": by_task,
    }
