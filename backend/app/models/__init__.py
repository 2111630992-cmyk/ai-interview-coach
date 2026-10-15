"""SQLModel 表定义。

设计取舍：**不使用 SQLModel Relationship**。
异步会话下惰性加载会触发 `MissingGreenlet`，显式 `select()` 更可预测，
也避免了 N+1 与循环导入。
"""

from app.models.base import new_id, utcnow
from app.models.interview import InterviewSession, Report, Turn
from app.models.resume import JobDescription, MatchAnalysis, Resume
from app.models.user import User

__all__ = [
    "InterviewSession",
    "JobDescription",
    "MatchAnalysis",
    "Report",
    "Resume",
    "Turn",
    "User",
    "new_id",
    "utcnow",
]
