"""LLM 结构化输出模型。

原则：所有模型调用的返回值都必须经这里校验。
- 尽量给默认值 —— 模型偶尔漏字段不应该让整场面试崩掉。
- 数值统一做 clamp 与归一化，避免模型返回 "4分" / 4.5 / 85 这类脏数据。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.constants import DIMENSION_WEIGHTS, DIMENSIONS, STAGES

# ======================================================================
# 简历解析
# ======================================================================


class EducationItem(BaseModel):
    school: str = ""
    major: str = ""
    degree: str = ""
    period: str = ""
    gpa: str = ""


class ProjectItem(BaseModel):
    name: str = ""
    role: str = ""
    period: str = ""
    description: str = ""
    tech: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)


class InternshipItem(BaseModel):
    company: str = ""
    role: str = ""
    period: str = ""
    description: str = ""
    achievements: list[str] = Field(default_factory=list)


class ResumeParse(BaseModel):
    name: str = ""
    education: list[EducationItem] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    projects: list[ProjectItem] = Field(default_factory=list)
    internships: list[InternshipItem] = Field(default_factory=list)
    awards: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)


# ======================================================================
# JD 分析
# ======================================================================


class JDParse(BaseModel):
    hard_skills: list[str] = Field(default_factory=list)
    soft_skills: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    weights: dict[str, float] = Field(default_factory=dict)
    summary: str = ""

    @field_validator("weights", mode="before")
    @classmethod
    def _normalize_weights(cls, v: Any) -> dict[str, float]:
        """把权重归一化到总和为 1；非法输入直接丢掉而不是报错。"""
        if not isinstance(v, dict):
            return {}
        cleaned: dict[str, float] = {}
        for k, raw in v.items():
            try:
                num = float(raw)
            except (TypeError, ValueError):
                continue
            if num < 0:
                continue
            cleaned[str(k)] = num
        total = sum(cleaned.values())
        if total <= 0:
            return cleaned
        return {k: round(v / total, 4) for k, v in cleaned.items()}


# ======================================================================
# 匹配分析
# ======================================================================


class MatchOut(BaseModel):
    match_score: int = 0
    strengths: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    likely_questions: list[str] = Field(default_factory=list)
    summary: str = ""

    @model_validator(mode="after")
    def _clamp(self) -> MatchOut:
        self.match_score = max(0, min(100, int(self.match_score)))
        self.likely_questions = self.likely_questions[:5]
        return self


# ======================================================================
# 面试计划
# ======================================================================

_VALID_STAGES = set(STAGES)


class StagePlan(BaseModel):
    stage: str
    weight: float = 0.0
    goal: str = ""

    @field_validator("stage", mode="before")
    @classmethod
    def _valid_stage(cls, v: Any) -> str:
        s = str(v or "").strip().lower()
        if s not in _VALID_STAGES:
            raise ValueError(f"未知环节: {v!r}")
        return s


class CompetencyItem(BaseModel):
    name: str
    source: Literal["jd", "resume", "general"] = "jd"
    weight: float = 0.1
    probe_questions: list[str] = Field(default_factory=list)

    @field_validator("name", mode="before")
    @classmethod
    def _non_empty(cls, v: Any) -> str:
        s = str(v or "").strip()
        if not s:
            raise ValueError("考察点名称不能为空")
        return s[:200]


class InterviewPlan(BaseModel):
    total_rounds: int = 6
    stages: list[StagePlan] = Field(default_factory=list)
    competencies: list[CompetencyItem] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    opening_line: str = ""

    @model_validator(mode="after")
    def _ensure_stages(self) -> InterviewPlan:
        """模型漏了环节就补齐，保证六环节齐全。"""
        present = {s.stage for s in self.stages}
        for stage in STAGES:
            if stage not in present:
                from app.constants import STAGE_META

                self.stages.append(
                    StagePlan(
                        stage=stage,
                        weight=STAGE_META[stage]["weight"],
                        goal=STAGE_META[stage]["goal"],
                    )
                )
        return self

    def stage_by_name(self, stage: str) -> StagePlan | None:
        return next((s for s in self.stages if s.stage == stage), None)

    def competency_names(self) -> list[str]:
        return [c.name for c in self.competencies]


# ======================================================================
# 单题评分
# ======================================================================

_SCORE_MIN, _SCORE_MAX = 1.0, 5.0


class Problem(BaseModel):
    issue: str = ""
    why: str = ""
    fix: str = ""


def _normalize_score(raw: Any) -> float:
    """把模型可能返回的各种刻度统一到 1-5。

    支持：1-5、0-10、0-100、字符串（"4分" / "4.5/5"）。
    """
    if isinstance(raw, dict):
        raw = raw.get("score", raw.get("value", 3))
    if isinstance(raw, str):
        import re

        m = re.search(r"-?\d+(?:\.\d+)?", raw)
        raw = float(m.group()) if m else 3.0
    try:
        num = float(raw)
    except (TypeError, ValueError):
        return 3.0
    if num > 10:  # 百分制
        num = num / 20.0
    elif num > 5:  # 十分制
        num = num / 2.0
    return round(max(_SCORE_MIN, min(_SCORE_MAX, num)), 2)


class Evaluation(BaseModel):
    relevance: float = 3.0
    structure: float = 3.0
    depth: float = 3.0
    delivery: float = 3.0
    fit: float = 3.0

    evidence: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    problems: list[Problem] = Field(default_factory=list)
    # 面试官视角的「这会在下一轮被追问什么」——比 problems 更前瞻
    risk_points: list[str] = Field(default_factory=list)
    rewritten_answer: str = ""
    is_weak: bool = False

    @field_validator(*DIMENSIONS, mode="before")
    @classmethod
    def _scores(cls, v: Any) -> float:
        return _normalize_score(v)

    @model_validator(mode="after")
    def _derive_weak(self) -> Evaluation:
        if not self.is_weak:
            self.is_weak = self.weighted_score() < 3.0
        return self

    def weighted_score(self) -> float:
        """按权重计算 1-5 的加权分。"""
        total = sum(getattr(self, d) * w for d, w in DIMENSION_WEIGHTS.items())
        return round(total, 2)

    def to_100(self) -> float:
        """映射到 0-100，用于报告雷达图。"""
        return round((self.weighted_score() - 1) / 4 * 100, 1)

    def dimension_100(self, dim: str) -> float:
        return round((getattr(self, dim) - 1) / 4 * 100, 1)


# ======================================================================
# 参考答案（按需生成，防幻觉）
# ======================================================================


class SuggestedAnswer(BaseModel):
    """考生点「看参考答案」时生成。

    关键约束：**缺少事实时保留占位符，绝不猜测** —— 例如 `[补充具体指标]`。
    否则模型会顺手编造漂亮但不存在的成绩，等于教学生编简历。
    """

    outline: list[str] = Field(default_factory=list)
    key_points: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    reference_answer: str = ""
    placeholders: list[str] = Field(default_factory=list)
    generated_at: str = ""


# ======================================================================
# 表达指标（视频 / 语音作答）
# ======================================================================


class DeliveryMetrics(BaseModel):
    """由前端从 ASR 结果与录音时间轴算出的**客观**指标。

    存在意义：把「表达流畅」从模型的主观印象变成可核对的数字。
    纯文字作答时这些字段为 0，`transcript_source = "typed"`。
    """

    duration_ms: int = 0
    word_count: int = 0
    speech_rate: float = 0.0  # 字 / 分钟
    filler_count: int = 0
    filler_ratio: float = 0.0  # 口头禅字数占比 0-1
    long_pause_count: int = 0
    longest_pause_ms: int = 0
    transcript_source: Literal["asr", "typed", "mixed"] = "typed"

    def is_voice(self) -> bool:
        return self.transcript_source in ("asr", "mixed")


# ======================================================================
# 面试报告
# ======================================================================

Verdict = Literal["strong_pass", "pass", "borderline", "fail"]

VERDICT_LABELS: dict[str, str] = {
    "strong_pass": "强烈推荐通过",
    "pass": "可以通过",
    "borderline": "边缘，需补强",
    "fail": "不通过",
}


class TopProblem(BaseModel):
    title: str = ""
    evidence: str = ""
    why_bad: str = ""
    how_to_fix: str = ""
    demo_answer: str = ""


class TrainingDay(BaseModel):
    day: int = 1
    task: str = ""
    goal: str = ""
    link_competency: str = ""


class ReportOut(BaseModel):
    verdict: Verdict = "borderline"
    summary: str = ""
    top_problems: list[TopProblem] = Field(default_factory=list)
    training_plan: list[TrainingDay] = Field(default_factory=list)

    @model_validator(mode="after")
    def _limit(self) -> ReportOut:
        self.top_problems = self.top_problems[:3]  # 硬约束：最多 3 条
        return self
