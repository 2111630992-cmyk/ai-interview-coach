"""日志配置与敏感信息脱敏。

简历原文属于个人敏感数据：日志中只允许出现脱敏后的片段，
手机号 / 邮箱 / 身份证号一律打码。
"""

from __future__ import annotations

import logging
import re
import sys

from app.core.config import settings

_PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_ID_CARD_RE = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")


def redact(text: str, *, keep: int = 0) -> str:
    """脱敏文本。

    keep=0 时只返回长度信息；keep>0 时保留前 keep 个字符用于定位问题。
    """
    if not text:
        return ""
    masked = _PHONE_RE.sub("[手机号]", text)
    masked = _EMAIL_RE.sub("[邮箱]", masked)
    masked = _ID_CARD_RE.sub("[身份证]", masked)
    if keep <= 0:
        return f"<len={len(masked)}>"
    return masked[:keep] + ("…" if len(masked) > keep else "")


def setup_logging() -> None:
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)

    # 避免 reload 场景下重复挂 handler
    if any(getattr(h, "_dsh_app", False) for h in root.handlers):
        return

    handler = logging.StreamHandler(sys.stdout)
    handler._dsh_app = True  # type: ignore[attr-defined]
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root.addHandler(handler)

    # 第三方库降噪：DEBUG 级别下 aiosqlite / sqlalchemy 会淹没业务日志
    for noisy in ("httpx", "httpcore", "httpcore2", "openai", "aiosqlite", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(max(level, logging.WARNING))


logger = logging.getLogger("app")
