"""API 依赖。

`get_ai` 做成 FastAPI 依赖，测试可用 `app.dependency_overrides` 注入替身。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.services.ai_types import AIServiceProtocol
from app.services.factory import get_ai_service


def get_ai() -> AIServiceProtocol:
    return get_ai_service()


AIDep = Annotated[AIServiceProtocol, Depends(get_ai)]
