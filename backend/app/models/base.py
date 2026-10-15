"""模型公共工具。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone


def new_id() -> str:
    """32 位十六进制 UUID。用字符串主键，SQLite / PostgreSQL 行为一致。"""
    return uuid.uuid4().hex


def utcnow() -> datetime:
    """带时区的当前 UTC 时间。"""
    return datetime.now(timezone.utc)
