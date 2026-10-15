"""AI 服务工厂。

单例：复用底层 HTTP 连接池。测试可通过 `set_ai_service` 注入替身。
"""

from __future__ import annotations

import logging

from app.core.config import settings
from app.services.ai_types import AIServiceProtocol
from app.services.llm_client import LLMTransport

logger = logging.getLogger("app.ai")

_service: AIServiceProtocol | None = None


def _build() -> AIServiceProtocol:
    if settings.is_mock_llm:
        from app.services.mock_ai import MockAIService

        logger.warning(
            "=" * 78
            + "\n未检测到 LLM_API_KEY，已启用【内置 Mock 面试官】。\n"
            "全流程（简历解析 / 面试追问 / 评分 / 报告）均可跑通，但分数由规则引擎给出，\n"
            "不代表真实模型效果。配置 LLM_API_KEY 后重启即可切换到真实模型。\n"
            + "=" * 78
        )
        return MockAIService()

    from app.services.ai_service import AIService

    logger.info("使用真实 LLM：%s @ %s", settings.LLM_MODEL, settings.LLM_BASE_URL)
    return AIService(LLMTransport(settings))


def get_ai_service() -> AIServiceProtocol:
    global _service
    if _service is None:
        _service = _build()
    return _service


def set_ai_service(service: AIServiceProtocol | None) -> None:
    """测试注入用。传 None 表示下次重新按配置构建。"""
    global _service
    _service = service


def reset_ai_service() -> None:
    set_ai_service(None)
