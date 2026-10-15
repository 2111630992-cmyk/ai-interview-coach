"""LLM 传输层（OpenAI 兼容协议）。

只负责「怎么把话送到模型、怎么把 JSON 拿回来」，不含任何业务语义。
业务语义在 ai_service.py / mock_ai.py。

关键能力：
- 超时 + 指数退避重试
- 强 schema 校验 + **校验失败自动修复重试**（把 Pydantic 错误回传给模型）
- 流式输出（SSE 用）
- token 用量累计（成本可观测）
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, TypeVar

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)
from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.core.errors import LLMError

logger = logging.getLogger("app.llm")

T = TypeVar("T", bound=BaseModel)

# 这些错误值得重试
_RETRYABLE = (APITimeoutError, APIConnectionError, RateLimitError)

_FENCE_RE = re.compile(r"^```[a-zA-Z0-9_-]*\s*|\s*```$", re.MULTILINE)


@dataclass
class Usage:
    """累计 token 用量与调用次数。"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    calls: int = 0
    by_task: dict[str, int] = field(default_factory=dict)

    def add(self, task: str, prompt: int, completion: int, total: int) -> None:
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.total_tokens += total
        self.calls += 1
        self.by_task[task] = self.by_task.get(task, 0) + total

    def as_dict(self) -> dict[str, Any]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "calls": self.calls,
            "by_task": dict(self.by_task),
        }


def extract_json(text: str) -> Any:
    """从模型输出里挖出 JSON 对象。

    模型经常加 ```json 围栏、前后寒暄、或尾部多余逗号，这里逐级降级处理。
    """
    if not text:
        raise ValueError("模型返回为空")

    cleaned = _FENCE_RE.sub("", text).strip()
    for candidate in (cleaned, text.strip()):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end > start:
        snippet = cleaned[start : end + 1]
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            # 去掉对象/数组里的尾随逗号
            fixed = re.sub(r",\s*([}\]])", r"\1", snippet)
            return json.loads(fixed)

    raise ValueError("模型输出中未找到 JSON 对象")


class LLMTransport:
    """OpenAI 兼容传输层。"""

    def __init__(self, cfg: Settings) -> None:
        self.cfg = cfg
        self.usage = Usage()
        self._client = AsyncOpenAI(
            api_key=cfg.LLM_API_KEY or "not-needed",
            base_url=cfg.LLM_BASE_URL,
            timeout=cfg.LLM_TIMEOUT_SECONDS,
            max_retries=0,  # 重试由本层自己控制，便于统计与日志
        )

    # ------------------------------------------------------------------
    # 底层调用
    # ------------------------------------------------------------------
    async def _chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        model: str,
        task: str,
        json_mode: bool,
        max_tokens: int | None = None,
    ) -> str:
        last_error: Exception | None = None
        attempts = self.cfg.LLM_MAX_RETRIES + 1

        for attempt in range(1, attempts + 1):
            try:
                kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                }
                if max_tokens:
                    kwargs["max_tokens"] = max_tokens
                if json_mode:
                    kwargs["response_format"] = {"type": "json_object"}

                resp = await self._client.chat.completions.create(**kwargs)

                if resp.usage:
                    self.usage.add(
                        task,
                        resp.usage.prompt_tokens or 0,
                        resp.usage.completion_tokens or 0,
                        resp.usage.total_tokens or 0,
                    )
                content = resp.choices[0].message.content or ""
                if not content.strip():
                    raise ValueError("模型返回空内容")
                return content

            except _RETRYABLE as exc:
                last_error = exc
                wait = min(2 ** (attempt - 1), 8)
                logger.warning(
                    "LLM 调用失败(task=%s, 第%d/%d次): %s，%.1fs 后重试",
                    task,
                    attempt,
                    attempts,
                    type(exc).__name__,
                    wait,
                )
                if attempt < attempts:
                    await asyncio.sleep(wait)
            except APIStatusError as exc:
                last_error = exc
                # 400 通常是不支持 response_format，降级重试一次
                if exc.status_code == 400 and json_mode:
                    logger.warning("上游不支持 json_object，降级为纯文本模式(task=%s)", task)
                    json_mode = False
                    continue
                # 5xx / 429 重试
                if exc.status_code >= 500 or exc.status_code == 429:
                    wait = min(2 ** (attempt - 1), 8)
                    if attempt < attempts:
                        await asyncio.sleep(wait)
                    continue
                break
            except Exception as exc:
                last_error = exc
                break

        logger.error("LLM 调用最终失败(task=%s): %s", task, last_error)
        raise LLMError(
            "AI 服务暂时不可用，请稍后重试",
            detail={"task": task, "reason": type(last_error).__name__ if last_error else "unknown"},
        )

    # ------------------------------------------------------------------
    # 对外：结构化输出
    # ------------------------------------------------------------------
    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        task: str,
        temperature: float = 0.2,
        model: str | None = None,
        max_repairs: int = 1,
    ) -> T:
        model = model or self.cfg.LLM_MODEL
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        content = await self._chat(
            messages,
            temperature=temperature,
            model=model,
            task=task,
            json_mode=True,
        )

        for repair in range(max_repairs + 1):
            try:
                return schema.model_validate(extract_json(content))
            except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                if repair >= max_repairs:
                    logger.error("LLM 结构化输出校验失败(task=%s): %s", task, exc)
                    raise LLMError(
                        "AI 返回格式异常，请重试",
                        detail={"task": task, "stage": "validate"},
                    ) from exc

                logger.warning("结构化输出校验失败，发起修复重试(task=%s, 第%d次)", task, repair + 1)
                messages.extend(
                    [
                        {"role": "assistant", "content": content},
                        {
                            "role": "user",
                            "content": (
                                "你上一次的输出无法通过 JSON Schema 校验，错误如下：\n"
                                f"{str(exc)[:1500]}\n\n"
                                "请只返回修正后的**完整 JSON 对象**，不要任何解释、不要 markdown 围栏。"
                            ),
                        },
                    ]
                )
                content = await self._chat(
                    messages,
                    temperature=0.1,
                    model=model,
                    task=f"{task}:repair",
                    json_mode=True,
                )

        raise LLMError("AI 返回格式异常，请重试")  # pragma: no cover

    # ------------------------------------------------------------------
    # 对外：流式文本
    # ------------------------------------------------------------------
    async def stream_text(
        self,
        *,
        system: str,
        user: str,
        task: str,
        temperature: float = 0.7,
        model: str | None = None,
    ) -> AsyncIterator[str]:
        model = model or self.cfg.LLM_MODEL
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        try:
            stream = await self._client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                stream=True,
            )
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                piece = getattr(delta, "content", None)
                if piece:
                    yield piece
        except _RETRYABLE as exc:
            logger.error("LLM 流式调用失败(task=%s): %s", task, exc)
            raise LLMError("AI 服务连接中断，请重试", detail={"task": task}) from exc
        except APIStatusError as exc:
            logger.error("LLM 流式调用失败(task=%s): HTTP %s", task, exc.status_code)
            raise LLMError("AI 服务返回错误，请重试", detail={"task": task}) from exc
