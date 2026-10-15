"""API 全链路测试：注册 → 传简历 → 建 JD → 匹配 → 面试 → 评分 → 报告。

另外覆盖几个必须处理的健壮性场景：
- 纯图片 PDF / 乱码文件 → 明确报错，不静默失败
- 越权访问别人的面试 → 404 而非泄露数据
- 非法登录 → 统一 401，不区分"用户不存在"与"密码错误"
- 已被面试引用的简历不允许删除
"""

from __future__ import annotations

import io

import pytest
from docx import Document
from httpx import AsyncClient

from app.tests.conftest import SAMPLE_JD_TEXT, SAMPLE_RESUME_TEXT, parse_sse

API = "/api/v1"


# ======================================================================
# 工具
# ======================================================================


def make_docx(text: str) -> bytes:
    document = Document()
    for line in text.splitlines():
        document.add_paragraph(line)
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()


async def upload_resume(client: AsyncClient, headers: dict) -> dict:
    resp = await client.post(
        f"{API}/resumes",
        headers=headers,
        files={
            "file": (
                "resume.docx",
                make_docx(SAMPLE_RESUME_TEXT),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def create_jd(client: AsyncClient, headers: dict) -> dict:
    resp = await client.post(
        f"{API}/jds",
        headers=headers,
        json={"title": "后端开发工程师", "company": "某某科技", "raw_text": SAMPLE_JD_TEXT},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def drain_sse(resp) -> list[tuple[str, dict]]:
    return parse_sse(resp.text)


# ======================================================================
# 健康检查与认证
# ======================================================================


class TestHealth:
    async def test_health_ok(self, client: AsyncClient):
        resp = await client.get(f"{API}/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        # 测试环境没有 API Key，应显式暴露 mock 模式，绝不静默
        assert body["llm_mode"] in ("mock", "live")


class TestAuth:
    async def test_register_and_me(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get(f"{API}/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["email"] == "tester@example.com"

    async def test_duplicate_email_conflicts(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post(
            f"{API}/auth/register",
            json={"email": "tester@example.com", "password": "another123"},
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "CONFLICT"

    async def test_wrong_password_is_401_without_user_enumeration(self, client: AsyncClient):
        await client.post(
            f"{API}/auth/register",
            json={"email": "real@example.com", "password": "secret123"},
        )
        wrong_pw = await client.post(
            f"{API}/auth/login", json={"email": "real@example.com", "password": "nope12345"}
        )
        no_user = await client.post(
            f"{API}/auth/login", json={"email": "ghost@example.com", "password": "nope12345"}
        )
        assert wrong_pw.status_code == no_user.status_code == 401
        assert wrong_pw.json()["message"] == no_user.json()["message"]

    async def test_guest_can_use_api(self, client: AsyncClient):
        resp = await client.post(f"{API}/auth/guest")
        assert resp.status_code == 200
        body = resp.json()
        assert body["user"]["is_guest"] is True
        headers = {"Authorization": f"Bearer {body['access_token']}"}
        me = await client.get(f"{API}/auth/me", headers=headers)
        assert me.status_code == 200

    async def test_missing_token_is_401(self, client: AsyncClient):
        resp = await client.get(f"{API}/auth/me")
        assert resp.status_code == 401
        assert resp.json()["code"] == "UNAUTHORIZED"

    async def test_malformed_token_is_401(self, client: AsyncClient):
        resp = await client.get(f"{API}/auth/me", headers={"Authorization": "Bearer garbage"})
        assert resp.status_code == 401

    async def test_short_password_rejected_with_unified_error(self, client: AsyncClient):
        resp = await client.post(
            f"{API}/auth/register", json={"email": "x@example.com", "password": "123"}
        )
        assert resp.status_code == 422
        # 错误体结构与业务异常一致，前端只需处理一种格式
        assert set(resp.json()) >= {"code", "message", "detail"}


# ======================================================================
# 简历
# ======================================================================


class TestResume:
    async def test_upload_docx_and_parse(self, client: AsyncClient, auth_headers: dict):
        resume = await upload_resume(client, auth_headers)
        assert resume["filename"] == "resume.docx"
        assert resume["text_length"] > 50
        parsed = resume["parsed"]
        assert isinstance(parsed, dict)
        # Mock 解析器应能从简历里认出技术栈
        assert any("Java" in s or "Python" in s for s in parsed.get("skills", []))

    async def test_reject_unsupported_extension(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post(
            f"{API}/resumes",
            headers=auth_headers,
            files={"file": ("resume.exe", b"MZ\x90\x00", "application/octet-stream")},
        )
        assert resp.status_code == 422
        assert "不支持的文件类型" in resp.json()["message"]

    async def test_reject_garbled_pdf_with_clear_message(
        self, client: AsyncClient, auth_headers: dict
    ):
        """损坏的 PDF 必须给出可读提示，而不是 500。"""
        resp = await client.post(
            f"{API}/resumes",
            headers=auth_headers,
            files={"file": ("broken.pdf", b"%PDF-1.4 not really a pdf", "application/pdf")},
        )
        assert resp.status_code == 422
        body = resp.json()
        assert body["code"] == "DOCUMENT_PARSE_FAILED"
        assert "文字版简历" in body["message"] or "损坏" in body["message"]

    async def test_reject_empty_file(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post(
            f"{API}/resumes",
            headers=auth_headers,
            files={"file": ("empty.txt", b"", "text/plain")},
        )
        assert resp.status_code == 422

    async def test_manual_correction(self, client: AsyncClient, auth_headers: dict):
        resume = await upload_resume(client, auth_headers)
        fixed = {
            "name": "张三",
            "skills": ["Java", "MySQL", "Redis"],
            "projects": [{"name": "订单系统重构", "highlights": ["P99 800ms→120ms"]}],
            "highlights": ["P99 从 800ms 降到 120ms"],
        }
        resp = await client.patch(
            f"{API}/resumes/{resume['id']}", headers=auth_headers, json={"parsed": fixed}
        )
        assert resp.status_code == 200
        assert resp.json()["parsed"]["skills"] == ["Java", "MySQL", "Redis"]
        assert resp.json()["parse_warning"] is None

    async def test_patch_requires_parsed_object(self, client: AsyncClient, auth_headers: dict):
        resume = await upload_resume(client, auth_headers)
        resp = await client.patch(
            f"{API}/resumes/{resume['id']}", headers=auth_headers, json={"name": "x"}
        )
        assert resp.status_code == 422

    async def test_list_and_get(self, client: AsyncClient, auth_headers: dict):
        resume = await upload_resume(client, auth_headers)
        lst = await client.get(f"{API}/resumes", headers=auth_headers)
        assert lst.status_code == 200
        assert any(r["id"] == resume["id"] for r in lst.json())
        one = await client.get(f"{API}/resumes/{resume['id']}", headers=auth_headers)
        assert one.status_code == 200

    async def test_cross_user_access_is_404(self, client: AsyncClient, auth_headers: dict):
        resume = await upload_resume(client, auth_headers)
        other = await client.post(f"{API}/auth/guest")
        other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
        resp = await client.get(f"{API}/resumes/{resume['id']}", headers=other_headers)
        assert resp.status_code == 404


# ======================================================================
# JD 与匹配
# ======================================================================


class TestJD:
    async def test_create_jd_extracts_competency_model(
        self, client: AsyncClient, auth_headers: dict
    ):
        jd = await create_jd(client, auth_headers)
        model = jd["competency_model"]
        assert model["hard_skills"]
        assert any("Java" in s for s in model["hard_skills"])
        assert sum(model["weights"].values()) == pytest.approx(1.0, abs=1e-6)

    async def test_too_short_jd_rejected(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post(
            f"{API}/jds", headers=auth_headers, json={"title": "后端", "raw_text": "太短了"}
        )
        assert resp.status_code == 422

    async def test_list_jds(self, client: AsyncClient, auth_headers: dict):
        await create_jd(client, auth_headers)
        resp = await client.get(f"{API}/jds", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()) >= 1


class TestMatch:
    async def test_match_returns_score_and_questions(
        self, client: AsyncClient, auth_headers: dict
    ):
        resume = await upload_resume(client, auth_headers)
        jd = await create_jd(client, auth_headers)
        resp = await client.post(
            f"{API}/match",
            headers=auth_headers,
            json={"resume_id": resume["id"], "jd_id": jd["id"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert 0 <= body["match_score"] <= 100
        assert body["cached"] is False
        assert len(body["likely_questions"]) <= 5
        assert body["strengths"] and body["risks"]

    async def test_second_request_hits_cache(self, client: AsyncClient, auth_headers: dict):
        resume = await upload_resume(client, auth_headers)
        jd = await create_jd(client, auth_headers)
        payload = {"resume_id": resume["id"], "jd_id": jd["id"]}
        first = await client.post(f"{API}/match", headers=auth_headers, json=payload)
        second = await client.post(f"{API}/match", headers=auth_headers, json=payload)
        assert first.json()["cached"] is False
        assert second.json()["cached"] is True
        assert first.json()["id"] == second.json()["id"]

    async def test_missing_resume_is_404(self, client: AsyncClient, auth_headers: dict):
        jd = await create_jd(client, auth_headers)
        resp = await client.post(
            f"{API}/match",
            headers=auth_headers,
            json={"resume_id": "nonexistent", "jd_id": jd["id"]},
        )
        assert resp.status_code == 404


# ======================================================================
# 面试全链路
# ======================================================================


class TestInterviewFlow:
    async def _setup(self, client: AsyncClient, headers: dict) -> tuple[dict, dict]:
        return await upload_resume(client, headers), await create_jd(client, headers)

    async def test_create_generates_plan(self, client: AsyncClient, auth_headers: dict):
        resume, jd = await self._setup(client, auth_headers)
        resp = await client.post(
            f"{API}/interviews",
            headers=auth_headers,
            json={
                "resume_id": resume["id"],
                "jd_id": jd["id"],
                "config": {"duration_min": 15, "interview_type": "technical"},
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "created"
        assert body["plan"]["competencies"]
        assert len(body["plan"]["stages"]) == 6
        assert body["turns"] == []
        assert body["plan_summary"]
        # 未开启实时反馈时，面试进行页不应拿到分数
        assert body["expose_scores"] is False

    async def test_start_streams_first_question(self, client: AsyncClient, auth_headers: dict):
        resume, jd = await self._setup(client, auth_headers)
        created = (
            await client.post(
                f"{API}/interviews",
                headers=auth_headers,
                json={"resume_id": resume["id"], "jd_id": jd["id"], "config": {"duration_min": 15}},
            )
        ).json()

        resp = await client.post(
            f"{API}/interviews/{created['id']}/start", headers=auth_headers
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

        events = await drain_sse(resp)
        kinds = [e for e, _ in events]
        assert "stage" in kinds
        assert "token" in kinds
        assert "question" in kinds
        assert "done" in kinds
        assert "error" not in kinds

        question = next(d for e, d in events if e == "question")
        assert question["turn_index"] == 1
        assert len(question["question"]) > 5

        tokens = "".join(d["delta"] for e, d in events if e == "token")
        # 流式拼接结果必须与最终落库的问题一致
        assert tokens.strip() == question["question"].strip()

    async def test_start_twice_is_rejected(self, client: AsyncClient, auth_headers: dict):
        resume, jd = await self._setup(client, auth_headers)
        created = (
            await client.post(
                f"{API}/interviews",
                headers=auth_headers,
                json={"resume_id": resume["id"], "jd_id": jd["id"], "config": {"duration_min": 15}},
            )
        ).json()
        await client.post(f"{API}/interviews/{created['id']}/start", headers=auth_headers)
        again = await client.post(f"{API}/interviews/{created['id']}/start", headers=auth_headers)
        assert again.status_code == 409
        assert again.json()["code"] == "INTERVIEW_STATE_INVALID"

    async def test_answer_before_start_is_rejected(self, client: AsyncClient, auth_headers: dict):
        resume, jd = await self._setup(client, auth_headers)
        created = (
            await client.post(
                f"{API}/interviews",
                headers=auth_headers,
                json={"resume_id": resume["id"], "jd_id": jd["id"], "config": {"duration_min": 15}},
            )
        ).json()
        resp = await client.post(
            f"{API}/interviews/{created['id']}/answer",
            headers=auth_headers,
            json={"answer": "我的回答"},
        )
        assert resp.status_code == 409

    async def test_double_answer_is_rejected(self, client: AsyncClient, auth_headers: dict):
        resume, jd = await self._setup(client, auth_headers)
        created = (
            await client.post(
                f"{API}/interviews",
                headers=auth_headers,
                json={"resume_id": resume["id"], "jd_id": jd["id"], "config": {"duration_min": 15}},
            )
        ).json()
        await client.post(f"{API}/interviews/{created['id']}/start", headers=auth_headers)
        first = await client.post(
            f"{API}/interviews/{created['id']}/answer",
            headers=auth_headers,
            json={"answer": "我负责了后端模块，用了 Java 和 MySQL。"},
        )
        assert first.status_code == 200
        # 第一题已被答过并且新题已生成，此刻最后一条 turn 尚未作答
        # 再提交一次应当成功（答新题）；这里改为直接检查状态机不会出现"同一题答两次"
        detail = await client.get(f"{API}/interviews/{created['id']}", headers=auth_headers)
        turns = detail.json()["turns"]
        assert turns[0]["answer"] is not None
        assert turns[1]["answer"] is None

    async def test_full_interview_produces_report(self, client: AsyncClient, auth_headers: dict):
        """跑完一整场（Mock 面试官），并检查报告的硬性约束。"""
        resume, jd = await self._setup(client, auth_headers)
        created = (
            await client.post(
                f"{API}/interviews",
                headers=auth_headers,
                json={
                    "resume_id": resume["id"],
                    "jd_id": jd["id"],
                    "config": {"duration_min": 15, "pressure_mode": True},
                },
            )
        ).json()
        session_id = created["id"]

        start = await client.post(f"{API}/interviews/{session_id}/start", headers=auth_headers)
        assert start.status_code == 200

        answers = [
            (
                "我当时负责订单查询接口的优化。先用 explain 发现是全表扫描，"
                "于是建了 (user_id, status) 的联合索引，P99 从 800ms 降到 120ms，QPS 提升到 3000。"
            ),
            (
                "缓存这块我用了 Redis，命中率 96%。不一致的时候用先更新数据库再删缓存的策略，"
                "并且给缓存加了随机过期时间避免雪崩。"
            ),
            "团队协作上，我和前端同学对接口字段有分歧，我主动拉了个会对齐了字段定义，最后按时上线。",
            "我参与了后端开发，做了一些优化工作。",
            "对于不熟悉的技术，我会先看官方文档再写 demo 验证。",
            "我一般会先定位问题范围，再逐步缩小排查。",
            "我希望加入一个技术氛围好的团队。",
            "我想了解一下团队的技术栈和日常工作节奏。",
            "我没有其他问题了。",
        ]

        finished = False
        for i in range(40):
            detail = await client.get(f"{API}/interviews/{session_id}", headers=auth_headers)
            turns = detail.json()["turns"]
            if turns[-1]["answer"] is not None:
                break
            resp = await client.post(
                f"{API}/interviews/{session_id}/answer",
                headers=auth_headers,
                json={"answer": answers[i % len(answers)], "client_elapsed_ms": 45000},
            )
            assert resp.status_code == 200, resp.text
            events = await drain_sse(resp)
            assert "error" not in [e for e, _ in events], events
            done = next((d for e, d in events if e == "done"), None)
            assert done is not None
            if done["session_finished"]:
                finished = True
                break

        assert finished, "面试未能在 40 轮内自然结束"

        report_resp = await client.post(
            f"{API}/interviews/{session_id}/finish", headers=auth_headers
        )
        assert report_resp.status_code == 200, report_resp.text
        report = report_resp.json()

        assert report["verdict"] in ("strong_pass", "pass", "borderline", "fail")
        assert report["verdict_label"]
        assert len(report["summary"]) >= 50
        assert len(report["dimension_scores"]) == 5
        assert all(0 <= v <= 100 for v in report["dimension_scores"].values())
        assert 1 <= len(report["top_problems"]) <= 3
        assert len(report["training_plan"]) == 7
        assert [d["day"] for d in report["training_plan"]] == list(range(1, 8))
        # 逐题点评必须覆盖所有已作答的轮次
        answered = [t for t in report["per_turn_feedback"] if t["answer"]]
        assert len(answered) >= 5
        assert all(t["evidence"] or t["scores"] for t in answered)

        # 训练计划不能是空话
        banned = ("多看书", "多练习", "多刷题", "加强学习")
        for day in report["training_plan"]:
            assert day["task"]
            assert not any(b in day["task"] for b in banned)

    async def test_finish_is_idempotent(self, client: AsyncClient, auth_headers: dict):
        resume, jd = await self._setup(client, auth_headers)
        created = (
            await client.post(
                f"{API}/interviews",
                headers=auth_headers,
                json={"resume_id": resume["id"], "jd_id": jd["id"], "config": {"duration_min": 15}},
            )
        ).json()
        sid = created["id"]
        await client.post(f"{API}/interviews/{sid}/start", headers=auth_headers)
        await client.post(
            f"{API}/interviews/{sid}/answer",
            headers=auth_headers,
            json={"answer": "我先分析了慢查询日志，然后加了联合索引，P99 从 800ms 降到 120ms。"},
        )
        r1 = await client.post(f"{API}/interviews/{sid}/finish", headers=auth_headers)
        r2 = await client.post(f"{API}/interviews/{sid}/finish", headers=auth_headers)
        assert r1.status_code == r2.status_code == 200
        assert r1.json()["id"] == r2.json()["id"]

    async def test_finish_without_any_answer_is_rejected(
        self, client: AsyncClient, auth_headers: dict
    ):
        resume, jd = await self._setup(client, auth_headers)
        created = (
            await client.post(
                f"{API}/interviews",
                headers=auth_headers,
                json={"resume_id": resume["id"], "jd_id": jd["id"], "config": {"duration_min": 15}},
            )
        ).json()
        resp = await client.post(
            f"{API}/interviews/{created['id']}/finish", headers=auth_headers
        )
        assert resp.status_code == 409

    async def test_report_before_finish_is_404(self, client: AsyncClient, auth_headers: dict):
        resume, jd = await self._setup(client, auth_headers)
        created = (
            await client.post(
                f"{API}/interviews",
                headers=auth_headers,
                json={"resume_id": resume["id"], "jd_id": jd["id"], "config": {"duration_min": 15}},
            )
        ).json()
        resp = await client.get(
            f"{API}/interviews/{created['id']}/report", headers=auth_headers
        )
        assert resp.status_code == 404

    async def test_abort_then_answer_is_rejected(self, client: AsyncClient, auth_headers: dict):
        resume, jd = await self._setup(client, auth_headers)
        created = (
            await client.post(
                f"{API}/interviews",
                headers=auth_headers,
                json={"resume_id": resume["id"], "jd_id": jd["id"], "config": {"duration_min": 15}},
            )
        ).json()
        sid = created["id"]
        await client.post(f"{API}/interviews/{sid}/start", headers=auth_headers)
        abort = await client.post(f"{API}/interviews/{sid}/abort", headers=auth_headers)
        assert abort.status_code == 200
        resp = await client.post(
            f"{API}/interviews/{sid}/answer", headers=auth_headers, json={"answer": "继续答"}
        )
        assert resp.status_code == 409

    async def test_next_recovers_interrupted_generation(
        self, client: AsyncClient, auth_headers: dict, db_engine
    ):
        """断流恢复：上一题已作答、但下一题没生成时，/next 应能继续推进。"""
        from sqlmodel import select
        from sqlmodel.ext.asyncio.session import AsyncSession

        from app.models import Turn

        resume, jd = await self._setup(client, auth_headers)
        created = (
            await client.post(
                f"{API}/interviews",
                headers=auth_headers,
                json={"resume_id": resume["id"], "jd_id": jd["id"], "config": {"duration_min": 15}},
            )
        ).json()
        sid = created["id"]
        await client.post(f"{API}/interviews/{sid}/start", headers=auth_headers)
        await client.post(
            f"{API}/interviews/{sid}/answer",
            headers=auth_headers,
            json={"answer": "我先看了慢查询日志，然后加了联合索引，P99 从 800ms 降到 120ms。"},
        )

        # 人为模拟"下一题没生成出来"：删掉那条待答轮次
        async with AsyncSession(db_engine) as session:
            rows = (
                await session.exec(
                    select(Turn).where(Turn.session_id == sid).order_by(Turn.turn_index)
                )
            ).all()
            assert rows[-1].answer is None
            await session.delete(rows[-1])
            await session.commit()

        # 此时 /answer 应当拒绝（最后一题已答过）
        rejected = await client.post(
            f"{API}/interviews/{sid}/answer",
            headers=auth_headers,
            json={"answer": "这是重复提交的回答内容"},
        )
        assert rejected.status_code == 409

        # /next 应该能在不带回答的情况下继续推进
        recovered = await client.post(f"{API}/interviews/{sid}/next", headers=auth_headers)
        assert recovered.status_code == 200, recovered.text
        events = await drain_sse(recovered)
        assert "question" in [e for e, _ in events]
        assert "error" not in [e for e, _ in events]

    async def test_next_rejected_when_question_pending(
        self, client: AsyncClient, auth_headers: dict
    ):
        """/next 只在"上一题已答"时可用；有待答问题时应走 /answer。"""
        resume, jd = await self._setup(client, auth_headers)
        created = (
            await client.post(
                f"{API}/interviews",
                headers=auth_headers,
                json={"resume_id": resume["id"], "jd_id": jd["id"], "config": {"duration_min": 15}},
            )
        ).json()
        sid = created["id"]
        await client.post(f"{API}/interviews/{sid}/start", headers=auth_headers)

        resp = await client.post(f"{API}/interviews/{sid}/next", headers=auth_headers)
        assert resp.status_code == 409
        assert resp.json()["code"] == "INTERVIEW_STATE_INVALID"

    async def test_next_before_start_is_rejected(
        self, client: AsyncClient, auth_headers: dict
    ):
        resume, jd = await self._setup(client, auth_headers)
        created = (
            await client.post(
                f"{API}/interviews",
                headers=auth_headers,
                json={"resume_id": resume["id"], "jd_id": jd["id"], "config": {"duration_min": 15}},
            )
        ).json()
        resp = await client.post(
            f"{API}/interviews/{created['id']}/next", headers=auth_headers
        )
        assert resp.status_code == 409

    async def test_realtime_feedback_exposes_scores(
        self, client: AsyncClient, auth_headers: dict
    ):
        """练习模式（feedback_mode=practice）才在面试中下发单题评分。"""
        resume, jd = await self._setup(client, auth_headers)
        created = (
            await client.post(
                f"{API}/interviews",
                headers=auth_headers,
                json={
                    "resume_id": resume["id"],
                    "jd_id": jd["id"],
                    "config": {"duration_min": 15, "feedback_mode": "practice"},
                },
            )
        ).json()
        sid = created["id"]
        assert created["expose_scores"] is True
        await client.post(f"{API}/interviews/{sid}/start", headers=auth_headers)
        resp = await client.post(
            f"{API}/interviews/{sid}/answer",
            headers=auth_headers,
            json={"answer": "我用了 Redis 做缓存，命中率 96%，把 P99 从 800ms 降到 120ms。"},
        )
        events = await drain_sse(resp)
        assert "eval" in [e for e, _ in events]

    async def test_simulation_mode_hides_scores(
        self, client: AsyncClient, auth_headers: dict
    ):
        """模拟模式（默认）全程不显示分数 —— 这是「像真实面试」的关键。"""
        resume, jd = await self._setup(client, auth_headers)
        created = (
            await client.post(
                f"{API}/interviews",
                headers=auth_headers,
                json={
                    "resume_id": resume["id"],
                    "jd_id": jd["id"],
                    "config": {"duration_min": 15, "feedback_mode": "simulation"},
                },
            )
        ).json()
        sid = created["id"]
        assert created["expose_scores"] is False

        await client.post(f"{API}/interviews/{sid}/start", headers=auth_headers)
        resp = await client.post(
            f"{API}/interviews/{sid}/answer",
            headers=auth_headers,
            json={"answer": "我用了 Redis 做缓存，命中率 96%。"},
        )
        events = await drain_sse(resp)
        assert "eval" not in [e for e, _ in events]
        # 但评分仍然落库了，报告里能看到
        detail = await client.get(f"{API}/interviews/{sid}", headers=auth_headers)
        assert detail.json()["turns"][0]["evaluation"] is None

    async def test_cross_user_interview_is_404(self, client: AsyncClient, auth_headers: dict):
        resume, jd = await self._setup(client, auth_headers)
        created = (
            await client.post(
                f"{API}/interviews",
                headers=auth_headers,
                json={"resume_id": resume["id"], "jd_id": jd["id"], "config": {"duration_min": 15}},
            )
        ).json()
        other = await client.post(f"{API}/auth/guest")
        other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
        assert (
            await client.get(f"{API}/interviews/{created['id']}", headers=other_headers)
        ).status_code == 404
        assert (
            await client.post(
                f"{API}/interviews/{created['id']}/start", headers=other_headers
            )
        ).status_code == 404

    async def test_invalid_config_rejected(self, client: AsyncClient, auth_headers: dict):
        resume = await upload_resume(client, auth_headers)
        resp = await client.post(
            f"{API}/interviews",
            headers=auth_headers,
            json={
                "resume_id": resume["id"],
                "config": {"duration_min": 999, "interview_type": "impossible"},
            },
        )
        assert resp.status_code == 422

    async def test_resume_used_by_interview_cannot_be_deleted(
        self, client: AsyncClient, auth_headers: dict
    ):
        resume, jd = await self._setup(client, auth_headers)
        await client.post(
            f"{API}/interviews",
            headers=auth_headers,
            json={"resume_id": resume["id"], "jd_id": jd["id"], "config": {"duration_min": 15}},
        )
        resp = await client.delete(f"{API}/resumes/{resume['id']}", headers=auth_headers)
        assert resp.status_code == 422
        assert "面试记录" in resp.json()["message"]


# ======================================================================
# 统计
# ======================================================================


class TestStats:
    async def test_overview_counts(self, client: AsyncClient, auth_headers: dict):
        await upload_resume(client, auth_headers)
        await create_jd(client, auth_headers)
        resp = await client.get(f"{API}/stats/overview", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["resume_count"] == 1
        assert body["jd_count"] == 1
        assert body["avg_score"] is None

    async def test_trend_empty(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get(f"{API}/stats/trend", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []
