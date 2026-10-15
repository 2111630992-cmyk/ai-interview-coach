"""密码哈希与 JWT。

设计说明：
- 直接使用 `bcrypt` 而非 passlib —— passlib 1.7.4 与 bcrypt>=4.1 存在
  `AttributeError: module 'bcrypt' has no attribute '__about__'` 兼容性缺陷。
- bcrypt 只处理前 72 字节，超长密码会被静默截断。这里先做 SHA-256 + base64
  预哈希（44 字节定长），既规避截断，也避免 bcrypt 4.x 对超长输入抛错。
"""

from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.core.config import settings

_BCRYPT_ROUNDS = 12


def _prehash(password: str) -> bytes:
    """SHA-256 预哈希，输出 44 字节 base64，满足 bcrypt 的长度限制。"""
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.b64encode(digest)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prehash(password), bcrypt.gensalt(_BCRYPT_ROUNDS)).decode("ascii")


def verify_password(password: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(_prehash(password), hashed.encode("ascii"))
    except (ValueError, TypeError):
        # 哈希格式非法（例如历史遗留数据）——视为验证失败而非 500
        return False


def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)).timestamp()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


class TokenError(Exception):
    """JWT 解析失败（过期 / 签名错误 / 格式非法）。"""


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("登录已过期，请重新登录") from exc
    except jwt.PyJWTError as exc:
        raise TokenError("登录凭证无效") from exc
