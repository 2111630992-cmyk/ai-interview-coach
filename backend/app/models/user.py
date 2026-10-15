"""用户模型。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, String
from sqlmodel import Field, SQLModel

from app.models.base import new_id, utcnow


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: str = Field(default_factory=new_id, sa_column=Column(String(32), primary_key=True))
    email: str = Field(sa_column=Column(String(255), unique=True, index=True, nullable=False))
    hashed_password: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))
    nickname: str = Field(default="同学", sa_column=Column(String(64), nullable=False))
    is_guest: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, default=False))
    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(DateTime(timezone=True), nullable=False)
    )

    def public(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "nickname": self.nickname,
            "is_guest": self.is_guest,
            "created_at": self.created_at,
        }
