"""FastAPI 依赖：数据库会话、当前用户。"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import get_session
from app.core.errors import UnauthorizedError
from app.core.security import TokenError, decode_access_token
from app.models import User

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def _user_from_header(
    session: AsyncSession, authorization: str | None
) -> User | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise UnauthorizedError("Authorization 头格式应为 `Bearer <token>`")
    try:
        payload = decode_access_token(token)
    except TokenError as exc:
        raise UnauthorizedError(str(exc)) from exc

    subject = payload.get("sub")
    if not subject:
        raise UnauthorizedError("登录凭证缺少用户标识")

    user = (await session.exec(select(User).where(User.id == subject))).first()
    if user is None:
        raise UnauthorizedError("用户不存在或已被删除")
    return user


async def get_current_user(
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    """强制登录。"""
    user = await _user_from_header(session, authorization)
    if user is None:
        raise UnauthorizedError()
    return user


async def get_optional_user(
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> User | None:
    """可选登录（用于游客可访问的只读接口）。"""
    return await _user_from_header(session, authorization)


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]
