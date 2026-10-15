"""请求 / 响应 DTO。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.constants import (
    DEFAULT_CONFIG,
    DIFFICULTIES,
    DURATIONS,
    FEEDBACK_MODES,
    INTERVIEW_MODES,
    INTERVIEW_TYPES,
    INTERVIEWER_MODES,
    LANGUAGES,
)

# 面试官人格是动态的（中/英两套），这里只做「存在性」校验
_KNOWN_INTERVIEWER_TYPES = {
    "hr",
    "technical",
    "project",
    "behavioral",
    "scenario",
    "stress",
}

# ======================================================================
# 认证
# ======================================================================


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    nickname: str = Field(default="同学", max_length=64)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserPublic(BaseModel):
    id: str
    email: str
    nickname: str
    is_guest: bool
    created_at: datetime | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


# ======================================================================
# 简历
# ======================================================================


class ResumePublic(BaseModel):
    id: str
    filename: str
    parsed: dict
    parse_warning: str | None = None
    text_length: int = 0
    created_at: datetime | None = None


# ======================================================================
# 岗位 JD
# ======================================================================


class JDCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    company: str | None = Field(default=None, max_length=200)
    raw_text: str = Field(min_length=20, max_length=20000)

    @field_validator("title", "raw_text")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class JDPublic(BaseModel):
    id: str
    title: str
    company: str | None = None
    competency_model: dict
    raw_text_length: int = 0
    created_at: datetime | None = None


# ======================================================================
# 匹配分析
# ======================================================================


class MatchRequest(BaseModel):
    resume_id: str
    jd_id: str


class MatchPublic(BaseModel):
    id: str
    resume_id: str
    jd_id: str
    match_score: int
    strengths: list[str]
    risks: list[str]
    likely_questions: list[str]
    summary: str = ""
    cached: bool = False
    created_at: datetime | None = None


# ======================================================================
# 面试
# ======================================================================


class InterviewConfigIn(BaseModel):
    interview_type: str = DEFAULT_CONFIG["interview_type"]
    duration_min: int = DEFAULT_CONFIG["duration_min"]
    difficulty: str = DEFAULT_CONFIG["difficulty"]
    language: str = DEFAULT_CONFIG["language"]
    pressure_mode: bool = DEFAULT_CONFIG["pressure_mode"]

    # ---- 新增：面试形态 ----
    # 文字面试 / 视频面试（摄像头 + 麦克风 + 实时字幕）
    mode: str = DEFAULT_CONFIG["mode"]
    # 练习模式（每题即时评分） / 模拟模式（全程隐藏分数）
    feedback_mode: str = DEFAULT_CONFIG["feedback_mode"]
    # panel = 每个环节换一位面试官（更接近真实校招多轮）；single = 整场同一位
    interviewer_mode: str = DEFAULT_CONFIG["interviewer_mode"]
    interviewer_type: str = DEFAULT_CONFIG["interviewer_type"]

    allow_hint: bool = DEFAULT_CONFIG["allow_hint"]
    allow_skip: bool = DEFAULT_CONFIG["allow_skip"]
    require_camera: bool = DEFAULT_CONFIG["require_camera"]

    # 兼容旧字段：前端不再直接传，由 feedback_mode 派生
    realtime_feedback: bool = DEFAULT_CONFIG["realtime_feedback"]
    voice_enabled: bool = DEFAULT_CONFIG["voice_enabled"]

    @field_validator("interview_type")
    @classmethod
    def _type(cls, v: str) -> str:
        if v not in INTERVIEW_TYPES:
            raise ValueError(f"面试类型必须是 {list(INTERVIEW_TYPES)} 之一")
        return v

    @field_validator("difficulty")
    @classmethod
    def _difficulty(cls, v: str) -> str:
        if v not in DIFFICULTIES:
            raise ValueError(f"难度必须是 {list(DIFFICULTIES)} 之一")
        return v

    @field_validator("language")
    @classmethod
    def _language(cls, v: str) -> str:
        if v not in LANGUAGES:
            raise ValueError(f"语言必须是 {list(LANGUAGES)} 之一")
        return v

    @field_validator("duration_min")
    @classmethod
    def _duration(cls, v: int) -> int:
        if v not in DURATIONS:
            raise ValueError(f"时长必须是 {DURATIONS} 之一")
        return v

    @field_validator("mode")
    @classmethod
    def _mode(cls, v: str) -> str:
        if v not in INTERVIEW_MODES:
            raise ValueError(f"面试形态必须是 {list(INTERVIEW_MODES)} 之一")
        return v

    @field_validator("feedback_mode")
    @classmethod
    def _feedback(cls, v: str) -> str:
        if v not in FEEDBACK_MODES:
            raise ValueError(f"反馈模式必须是 {list(FEEDBACK_MODES)} 之一")
        return v

    @field_validator("interviewer_mode")
    @classmethod
    def _interviewer_mode(cls, v: str) -> str:
        if v not in INTERVIEWER_MODES:
            raise ValueError(f"面试官模式必须是 {list(INTERVIEWER_MODES)} 之一")
        return v

    @field_validator("interviewer_type")
    @classmethod
    def _interviewer_type(cls, v: str) -> str:
        if v not in _KNOWN_INTERVIEWER_TYPES:
            raise ValueError(f"未知面试官类型，可选：{sorted(_KNOWN_INTERVIEWER_TYPES)}")
        return v


class InterviewCreate(BaseModel):
    resume_id: str
    jd_id: str | None = None
    config: InterviewConfigIn = Field(default_factory=InterviewConfigIn)


class InterviewerPublic(BaseModel):
    """面试官人格（对前端展示用）。"""

    type: str
    name: str
    title: str
    emoji: str
    accent: str
    bio: str = ""
    style: str = ""
    personality: str = ""
    focus_areas: list[str] = Field(default_factory=list)


class InterviewSummary(BaseModel):
    id: str
    status: str
    config: dict
    plan_summary: str = ""
    current_stage: str | None = None
    current_turn_index: int = 0
    turn_count: int = 0
    total_score: float | None = None
    dimensions: dict | None = None
    delivery_summary: dict = Field(default_factory=dict)
    resume_filename: str = ""
    jd_title: str | None = None
    # 当前环节的面试官（列表页展示"上次是谁面的"）
    current_interviewer: InterviewerPublic | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None


class TurnPublic(BaseModel):
    id: str
    turn_index: int
    stage: str
    competency: str | None = None
    question: str
    answer: str | None = None
    is_followup: bool = False
    followup_depth: int = 0
    parent_turn_id: str | None = None
    # 本轮面试官人格
    interviewer: InterviewerPublic | None = None
    # ---- 真实面试行为记录 ----
    hinted: bool = False
    skipped: bool = False
    marked: bool = False
    # 表达指标（视频 / 语音作答才有意义）
    delivery_metrics: dict | None = None
    recording_key: str | None = None
    has_suggested_answer: bool = False
    # 默认不返回给「面试进行页」；练习模式、报告页才附带
    evaluation: dict | None = None
    created_at: datetime | None = None


class InterviewDetail(InterviewSummary):
    plan: dict = Field(default_factory=dict)
    roster: dict = Field(default_factory=dict)
    token_usage: dict = Field(default_factory=dict)
    turns: list[TurnPublic] = Field(default_factory=list)
    # 是否允许前端展示评分（练习模式为 True）
    expose_scores: bool = False


class DeliveryMetricsIn(BaseModel):
    """前端上报的表达指标。全部可选 —— 缺了也不影响评分，只是少了客观参考。"""

    duration_ms: int = Field(default=0, ge=0, le=3_600_000)
    word_count: int = Field(default=0, ge=0, le=100_000)
    speech_rate: float = Field(default=0.0, ge=0, le=2000)
    filler_count: int = Field(default=0, ge=0, le=10_000)
    filler_ratio: float = Field(default=0.0, ge=0, le=1)
    long_pause_count: int = Field(default=0, ge=0, le=10_000)
    longest_pause_ms: int = Field(default=0, ge=0, le=3_600_000)
    transcript_source: Literal["asr", "typed", "mixed"] = "typed"


class AnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=8000)
    client_elapsed_ms: int | None = Field(default=None, ge=0)
    # 视频 / 语音作答时附带
    delivery_metrics: DeliveryMetricsIn | None = None
    # 本地录像在浏览器 IndexedDB 的 key（视频不上传服务器）
    recording_key: str | None = Field(default=None, max_length=64)


class SkipRequest(BaseModel):
    """主动跳过。必须给出原因，否则学生容易养成"不会就跳"的习惯。"""

    reason: str = Field(default="", max_length=500)
    client_elapsed_ms: int | None = Field(default=None, ge=0)


class TrackUpdateRequest(BaseModel):
    """提示 / 标记的开关（跳过走 /skip，因为它会推进面试）。"""

    marked: bool | None = None
    hinted: bool | None = None


# ======================================================================
# 报告
# ======================================================================


class ReportPublic(BaseModel):
    id: str
    session_id: str
    verdict: str
    verdict_label: str = ""
    summary: str
    dimension_scores: dict
    top_problems: list[dict]
    per_turn_feedback: list[dict]
    training_plan: list[dict]
    # 视频/语音作答的整场表达指标汇总（纯文字面试为 {"is_voice": false}）
    delivery_summary: dict = Field(default_factory=dict)
    created_at: datetime | None = None


class TrendPoint(BaseModel):
    session_id: str
    date: datetime | None = None
    jd_title: str | None = None
    interview_type: str = ""
    total_score: float | None = None
