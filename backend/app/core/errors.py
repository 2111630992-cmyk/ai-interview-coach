"""统一异常体系。

所有对外错误响应体统一为：
    {"code": "...", "message": "...", "detail": {...}}
由 main.py 注册的异常处理器保证一致性。
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """业务异常基类。"""

    status_code: int = 400
    code: str = "APP_ERROR"
    message: str = "请求处理失败"

    def __init__(
        self,
        message: str | None = None,
        *,
        detail: dict[str, Any] | None = None,
        code: str | None = None,
        status_code: int | None = None,
    ) -> None:
        self.message = message or self.message
        self.detail = detail or {}
        self.code = code or self.code
        self.status_code = status_code or self.status_code
        super().__init__(self.message)

    def to_body(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "detail": self.detail}


class UnauthorizedError(AppError):
    status_code = 401
    code = "UNAUTHORIZED"
    message = "请先登录"


class ForbiddenError(AppError):
    status_code = 403
    code = "FORBIDDEN"
    message = "没有权限访问该资源"


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"
    message = "资源不存在"


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"
    message = "资源已存在"


class InvalidInputError(AppError):
    status_code = 422
    code = "INVALID_INPUT"
    message = "输入内容不合法"


class DocumentParseError(AppError):
    """文件无法解析出文字（例如纯图片 PDF）。"""

    status_code = 422
    code = "DOCUMENT_PARSE_FAILED"
    message = "文件解析失败"


class LLMError(AppError):
    """上游模型调用失败（超时 / 限流 / 返回体非法）。"""

    status_code = 502
    code = "LLM_ERROR"
    message = "AI 服务暂时不可用，请稍后重试"


class InterviewStateError(AppError):
    """面试状态机拒绝该操作。"""

    status_code = 409
    code = "INTERVIEW_STATE_INVALID"
    message = "当前面试状态不允许该操作"
