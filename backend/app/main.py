"""FastAPI 应用入口。

统一错误响应体：{"code": "...", "message": "...", "detail": {...}}
包括请求校验失败（422）也走同一套格式，前端只需处理一种错误结构。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.db import dispose_db, init_db
from app.core.errors import AppError
from app.core.logging import logger, setup_logging

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- 启动前检查：配置错误要立刻说清楚，而不是运行时神秘失败 ----
    if settings.is_production and settings.SECRET_KEY == "change-me-to-a-long-random-string":
        raise RuntimeError(
            "生产环境必须设置 SECRET_KEY（可通过 "
            "python -c \"import secrets;print(secrets.token_urlsafe(48))\" 生成）"
        )

    if settings.is_mock_llm:
        logger.warning("LLM 处于 Mock 模式（未配置 LLM_API_KEY），全流程可用但分数由规则引擎给出")
    else:
        logger.info("LLM 已启用：%s @ %s", settings.LLM_MODEL, settings.LLM_BASE_URL)

    await init_db()
    logger.info("%s v%s 启动完成（%s）", settings.APP_NAME, __version__, settings.APP_ENV)

    yield

    await dispose_db()
    logger.info("已关闭数据库连接")


app = FastAPI(
    title=settings.APP_NAME,
    version=__version__,
    description=(
        "秋招 AI 面试陪练平台后端。\n\n"
        "核心能力：JD 驱动的能力模型、自适应多轮追问、可解释的五维评分、面试报告与训练计划。"
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


# ======================================================================
# 统一异常处理
# ======================================================================


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.to_body())


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    """把 FastAPI 默认的 422 结构改造成统一格式。

    注意：自定义校验器抛出的 ValueError 会被放进 errors()[i]["ctx"]["error"]，
    它是 Python 对象、不可 JSON 序列化，直接透传会让错误响应本身崩成 500。
    这里做一次净化。
    """
    errors = _sanitize_errors(exc.errors())
    first = errors[0] if errors else {}
    field = ".".join(str(p) for p in first.get("loc", []) if p not in ("body", "query", "path"))
    message = first.get("msg", "请求参数不合法")
    return JSONResponse(
        status_code=422,
        content={
            "code": "INVALID_INPUT",
            "message": f"{field}：{message}" if field else message,
            "detail": {"errors": errors[:5]},
        },
    )


def _sanitize_errors(errors: list[dict]) -> list[dict]:
    """只保留可 JSON 序列化的字段，并去掉 Pydantic 加在消息前的 "Value error, "。"""
    cleaned: list[dict] = []
    for err in errors:
        msg = str(err.get("msg", ""))
        for prefix in ("Value error, ", "Assertion failed, "):
            msg = msg.removeprefix(prefix)
        cleaned.append(
            {
                "loc": [str(p) for p in err.get("loc", [])],
                "msg": msg,
                "type": str(err.get("type", "")),
                "input": _safe_repr(err.get("input")),
            }
        )
    return cleaned


def _safe_repr(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_safe_repr(v) for v in value][:10]
    if isinstance(value, dict):
        return {str(k): _safe_repr(v) for k, v in list(value.items())[:10]}
    return repr(value)


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    logging.getLogger("app").exception("未处理异常 %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "code": "INTERNAL",
            "message": "服务器内部错误，请稍后重试",
            "detail": {} if settings.is_production else {"type": type(exc).__name__},
        },
    )


# ======================================================================
# 健康检查与路由
# ======================================================================


@app.get("/api/v1/health", tags=["系统"], summary="健康检查")
async def health() -> dict:
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": __version__,
        "env": settings.APP_ENV,
        "llm_mode": "mock" if settings.is_mock_llm else "live",
        "llm_model": None if settings.is_mock_llm else settings.LLM_MODEL,
    }


app.include_router(api_router)
