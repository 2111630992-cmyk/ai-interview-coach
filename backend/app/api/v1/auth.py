"""认证：注册 / 登录 / 游客 / 当前用户。"""

from __future__ import annotations

from fastapi import APIRouter
from sqlmodel import select

from app.core.deps import CurrentUser, SessionDep
from app.core.errors import ConflictError, UnauthorizedError
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.schemas.api import LoginRequest, RegisterRequest, TokenResponse, UserPublic

router = APIRouter(prefix="/auth", tags=["认证"])


def _token_response(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.id, extra={"email": user.email}),
        user=UserPublic(**user.public()),
    )


@router.post("/register", response_model=TokenResponse, summary="注册")
async def register(payload: RegisterRequest, db: SessionDep) -> TokenResponse:
    email = payload.email.lower().strip()
    exists = (await db.exec(select(User).where(User.email == email))).first()
    if exists is not None:
        raise ConflictError("该邮箱已注册，请直接登录")

    user = User(
        email=email,
        hashed_password=hash_password(payload.password),
        nickname=payload.nickname.strip() or "同学",
        is_guest=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return _token_response(user)


@router.post("/login", response_model=TokenResponse, summary="登录")
async def login(payload: LoginRequest, db: SessionDep) -> TokenResponse:
    email = payload.email.lower().strip()
    user = (await db.exec(select(User).where(User.email == email))).first()
    # 不区分"用户不存在"与"密码错误"，避免账号枚举
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise UnauthorizedError("邮箱或密码不正确")
    return _token_response(user)


@router.post("/guest", response_model=TokenResponse, summary="游客体验")
async def guest(db: SessionDep) -> TokenResponse:
    """创建一个匿名账号，让用户不必注册就能试一场。"""
    import uuid

    user = User(
        email=f"guest_{uuid.uuid4().hex[:12]}@guest.local",
        hashed_password=None,
        nickname="游客同学",
        is_guest=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return _token_response(user)


@router.get("/me", response_model=UserPublic, summary="当前用户")
async def me(user: CurrentUser) -> UserPublic:
    return UserPublic(**user.public())
