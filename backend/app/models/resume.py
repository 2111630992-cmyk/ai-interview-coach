"""简历、岗位 JD、匹配分析。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Integer, String, Text
from sqlmodel import Field, SQLModel

from app.models.base import new_id, utcnow


class Resume(SQLModel, table=True):
    __tablename__ = "resumes"

    id: str = Field(default_factory=new_id, sa_column=Column(String(32), primary_key=True))
    user_id: str = Field(sa_column=Column(String(32), index=True, nullable=False))
    filename: str = Field(sa_column=Column(String(255), nullable=False))
    raw_text: str = Field(default="", sa_column=Column(Text, nullable=False))
    # 结构化结果：{education, skills, projects, internships, awards, highlights}
    parsed: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    parse_warning: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(DateTime(timezone=True), nullable=False)
    )


class JobDescription(SQLModel, table=True):
    __tablename__ = "job_descriptions"

    id: str = Field(default_factory=new_id, sa_column=Column(String(32), primary_key=True))
    user_id: str = Field(sa_column=Column(String(32), index=True, nullable=False))
    title: str = Field(sa_column=Column(String(200), nullable=False))
    company: str | None = Field(default=None, sa_column=Column(String(200), nullable=True))
    raw_text: str = Field(default="", sa_column=Column(Text, nullable=False))
    # 岗位能力模型：{hard_skills:[], soft_skills:[], domains:[], weights:{}, summary}
    competency_model: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(DateTime(timezone=True), nullable=False)
    )


class MatchAnalysis(SQLModel, table=True):
    __tablename__ = "match_analyses"

    id: str = Field(default_factory=new_id, sa_column=Column(String(32), primary_key=True))
    user_id: str = Field(sa_column=Column(String(32), index=True, nullable=False))
    resume_id: str = Field(sa_column=Column(String(32), index=True, nullable=False))
    jd_id: str = Field(sa_column=Column(String(32), index=True, nullable=False))
    match_score: int = Field(default=0, sa_column=Column(Integer, nullable=False))
    strengths: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    risks: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    likely_questions: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    summary: str = Field(default="", sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(DateTime(timezone=True), nullable=False)
    )
