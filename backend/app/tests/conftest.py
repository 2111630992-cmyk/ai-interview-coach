"""pytest 夹具。

关键点：用**内存 SQLite + StaticPool**，避免测试互相污染，
也不去碰开发库 dev.db（ASGITransport 默认不跑 lifespan，因此不会触发 init_db）。
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import get_session
from app.main import app
from app.services.factory import set_ai_service
from app.services.mock_ai import MockAIService


@pytest_asyncio.fixture
async def db_engine():
    # StaticPool：让所有连接共享同一个内存库
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_engine) -> AsyncGenerator[AsyncClient, None]:
    async def _override_session():
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_session] = _override_session
    set_ai_service(MockAIService())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()
    set_ai_service(None)


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "tester@example.com", "password": "secret123", "nickname": "测试同学"},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ======================================================================
# 工具
# ======================================================================


def parse_sse(body: str) -> list[tuple[str, dict]]:
    """把 SSE 响应体解析成 [(event, data), ...]。"""
    events: list[tuple[str, dict]] = []
    for block in body.replace("\r\n", "\n").split("\n\n"):
        if not block.strip():
            continue
        event = "message"
        data_lines: list[str] = []
        for line in block.split("\n"):
            if line.startswith("event:"):
                event = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:") :].strip())
        if not data_lines:
            continue
        raw = "\n".join(data_lines)
        try:
            events.append((event, json.loads(raw)))
        except json.JSONDecodeError:
            events.append((event, {"_raw": raw}))
    return events


SAMPLE_RESUME_TEXT = """张三
本科 计算机科学与技术 某某大学 2019.09-2023.06 GPA 3.7
专业技能
熟练掌握 Java、Python、MySQL、Redis、Kafka
熟悉 Spring Boot、Docker、Kubernetes

项目经历
- 订单系统重构：把下单接口 P99 从 800ms 降到 120ms，QPS 提升到 3000
- 推荐服务：基于 Redis 做热点缓存，缓存命中率 96%

实习经历
- 某互联网公司 后端开发实习生 2022.07-2022.10 参与支付链路开发

获奖情况
- 国家励志奖学金
"""


SAMPLE_JD_TEXT = (
    "岗位职责：负责后端服务的设计与开发，参与高并发交易系统的架构优化。\n"
    "任职要求：\n"
    "1. 熟练掌握 Java、Spring Boot，熟悉 MySQL 索引优化与事务；\n"
    "2. 熟悉 Redis 缓存、Kafka 消息队列，了解分布式与微服务；\n"
    "3. 有良好的沟通表达与团队协作能力，具备 owner 意识。\n"
)
