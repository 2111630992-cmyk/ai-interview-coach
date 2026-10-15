"""面试会话、单轮问答、面试报告。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, Float, Integer, String, Text
from sqlmodel import Field, SQLModel

from app.constants import STATUS_CREATED
from app.models.base import new_id, utcnow


class InterviewSession(SQLModel, table=True):
    __tablename__ = "interview_sessions"

    id: str = Field(default_factory=new_id, sa_column=Column(String(32), primary_key=True))
    user_id: str = Field(sa_column=Column(String(32), index=True, nullable=False))
    resume_id: str = Field(sa_column=Column(String(32), nullable=False))
    jd_id: str | None = Field(default=None, sa_column=Column(String(32), nullable=True))

    # {interview_type, duration_min, difficulty, language, pressure_mode, realtime_feedback,
    #  voice_enabled, mode, interviewer_mode, interviewer_type, allow_hint, allow_skip,
    #  require_camera, _paused_seconds}
    config: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    # 面试计划：{total_rounds, stages:[], competencies:[], constraints:[]}
    plan: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    plan_summary: str = Field(default="", sa_column=Column(Text, nullable=False))
    # 环节 → 面试官人格。随会话固化：换面试官会同时改变提问口径与评分侧重
    roster: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))

    status: str = Field(
        default=STATUS_CREATED, sa_column=Column(String(16), index=True, nullable=False)
    )
    current_stage: str | None = Field(default=None, sa_column=Column(String(32), nullable=True))
    current_turn_index: int = Field(default=0, sa_column=Column(Integer, nullable=False))

    total_score: float | None = Field(default=None, sa_column=Column(Float, nullable=True))
    # {relevance: 0-100, structure:.., depth:.., delivery:.., fit:..}
    dimensions: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    # 视频/语音作答的整场表达指标汇总
    delivery_summary: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))

    # 成本可观测性
    token_usage: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))

    started_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    finished_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(DateTime(timezone=True), nullable=False)
    )


class Turn(SQLModel, table=True):
    __tablename__ = "turns"

    id: str = Field(default_factory=new_id, sa_column=Column(String(32), primary_key=True))
    session_id: str = Field(sa_column=Column(String(32), index=True, nullable=False))

    turn_index: int = Field(sa_column=Column(Integer, nullable=False))
    stage: str = Field(sa_column=Column(String(32), nullable=False))
    competency: str | None = Field(default=None, sa_column=Column(String(200), nullable=True))
    parent_turn_id: str | None = Field(default=None, sa_column=Column(String(32), nullable=True))
    followup_depth: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    is_followup: bool = Field(default=False)

    # 本轮由哪位面试官发问（人格 key），前端据此显示头像、姓名与风格提示
    interviewer: str | None = Field(default=None, sa_column=Column(String(32), nullable=True))

    question: str = Field(default="", sa_column=Column(Text, nullable=False))
    answer: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    # 面试官内部笔记（不给学生看）：下一轮该追什么
    internal_note: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    # 单题评分结构见 services/prompts.py::EVALUATOR_SYSTEM_PROMPT
    evaluation: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))

    # ---- 真实面试行为记录 ----
    # 用了提示就记录。报告里会显示"本场使用了 N 次提示"——诚实机制，避免自欺
    hinted: bool = Field(default=False, sa_column=Column(Boolean, default=False, nullable=False))
    # 主动跳过（实在答不出来）。记 0 分但不中断面试，避免学生因一题卡死而放弃整场
    skipped: bool = Field(default=False, sa_column=Column(Boolean, default=False, nullable=False))
    # 考生标记「要复习这题」
    marked: bool = Field(default=False, sa_column=Column(Boolean, default=False, nullable=False))
    # 按需生成的参考答案：{outline, key_points, improvements, reference_answer, generated_at}
    suggested_answer: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))

    answer_latency_ms: int | None = Field(default=None, sa_column=Column(Integer, nullable=True))
    # 表达指标：{duration_ms, word_count, speech_rate, filler_count, filler_ratio,
    #           long_pause_count, longest_pause_ms, transcript_source}
    delivery_metrics: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    # 本地录像在浏览器 IndexedDB 中的 key。**视频不上传服务器**，隐私优先
    recording_key: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))

    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(DateTime(timezone=True), nullable=False)
    )


class Report(SQLModel, table=True):
    __tablename__ = "reports"

    id: str = Field(default_factory=new_id, sa_column=Column(String(32), primary_key=True))
    session_id: str = Field(
        sa_column=Column(String(32), unique=True, index=True, nullable=False)
    )
    user_id: str = Field(sa_column=Column(String(32), index=True, nullable=False))

    verdict: str = Field(default="borderline", sa_column=Column(String(16), nullable=False))
    verdict_label: str = Field(default="", sa_column=Column(String(32), nullable=False))
    summary: str = Field(default="", sa_column=Column(Text, nullable=False))
    dimension_scores: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    top_problems: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    per_turn_feedback: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    training_plan: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(DateTime(timezone=True), nullable=False)
    )
