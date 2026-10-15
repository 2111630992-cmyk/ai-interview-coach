"""视频面试 / 面试官人格 / 提示跳过标记 / 参考答案 / 暂停续做 的测试。

这些是第二轮迭代新增的能力，覆盖：
- 面试官人格库与多轮换人分配
- 视频面试的表达指标落库与汇总（以及"纯文字时不编造语速"）
- 请求提示（只增不减的诚实机制）、标记、跳过
- 参考答案（幂等缓存 + 占位符纪律）
- 暂停期间不计入面试时长、暂停时不能答题
- 练习模式 vs 模拟模式的评分可见性
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.constants import STAGES
from app.interviewers import INTERVIEWER_TYPES, get_interviewer, list_interviewers
from app.services.interview_service import summarize_delivery
from app.tests.conftest import SAMPLE_JD_TEXT, parse_sse

API = "/api/v1"


# ======================================================================
# 面试官人格库
# ======================================================================


class TestInterviewerPersonas:
    def test_six_personas_in_both_languages(self):
        assert len(INTERVIEWER_TYPES) == 6
        assert len(list_interviewers("zh")) == 6
        assert len(list_interviewers("en")) == 6

    def test_personas_are_distinct_and_named(self):
        zh = list_interviewers("zh")
        names = {p.name for p in zh}
        assert len(names) == 6
        # 每个人格都要有真实的背景与风格，否则"换人"没有意义
        for p in zh:
            assert p.name and p.title and p.bio and p.style and p.personality
            assert len(p.focus_areas) >= 3

    def test_locale_fallback(self):
        assert get_interviewer("hr", "en").name == "Lisa Wang"
        assert get_interviewer("hr", "zh").name == "李雯"
        # 未知类型退回该语言第一位，不抛异常
        assert get_interviewer("nope", "zh") is not None

    def test_prompt_block_contains_identity(self):
        block = get_interviewer("stress", "zh").prompt_block()
        assert "赵岩" in block and "压力" in block

    async def test_meta_endpoints(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get(f"{API}/interviews/meta/interviewers?language=zh")
        assert resp.status_code == 200
        assert len(resp.json()) == 6

        one = await client.get(f"{API}/interviews/meta/interviewer/technical?language=en")
        assert one.status_code == 200
        assert one.json()["name"] == "Mike Zhang"

    async def test_panel_mode_assigns_one_persona_per_stage(
        self, client: AsyncClient, auth_headers: dict
    ):
        """多轮模式：六个环节各由不同面试官负责，这是「真实校招流程」的模拟。"""
        resume = await _upload_resume(client, auth_headers)
        jd = await _create_jd(client, auth_headers)
        created = (
            await client.post(
                f"{API}/interviews",
                headers=auth_headers,
                json={
                    "resume_id": resume["id"],
                    "jd_id": jd["id"],
                    "config": {"duration_min": 15, "interviewer_mode": "panel"},
                },
            )
        ).json()

        roster = created["roster"]
        assert set(roster.keys()) == set(STAGES)
        types = [roster[s]["type"] for s in STAGES]
        # 至少 4 个不同的人，否则"多轮"名不副实
        assert len(set(types)) >= 4

    async def test_single_mode_uses_one_persona(
        self, client: AsyncClient, auth_headers: dict
    ):
        resume = await _upload_resume(client, auth_headers)
        jd = await _create_jd(client, auth_headers)
        created = (
            await client.post(
                f"{API}/interviews",
                headers=auth_headers,
                json={
                    "resume_id": resume["id"],
                    "jd_id": jd["id"],
                    "config": {
                        "duration_min": 15,
                        "interviewer_mode": "single",
                        "interviewer_type": "project",
                    },
                },
            )
        ).json()
        types = {created["roster"][s]["type"] for s in STAGES}
        assert types == {"project"}
        assert created["roster"]["intro"]["name"]  # 名字也带上了

    async def test_turn_carries_interviewer(
        self, client: AsyncClient, auth_headers: dict
    ):
        resume = await _upload_resume(client, auth_headers)
        jd = await _create_jd(client, auth_headers)
        created = (
            await client.post(
                f"{API}/interviews",
                headers=auth_headers,
                json={"resume_id": resume["id"], "jd_id": jd["id"], "config": {"duration_min": 15}},
            )
        ).json()
        await client.post(f"{API}/interviews/{created['id']}/start", headers=auth_headers)

        detail = (await client.get(f"{API}/interviews/{created['id']}", headers=auth_headers)).json()
        first = detail["turns"][0]
        assert first["interviewer"] is not None
        assert first["interviewer"]["name"] == detail["roster"][first["stage"]]["name"]


# ======================================================================
# 视频面试：表达指标
# ======================================================================


class TestDeliveryMetrics:
    def test_voiceless_summary_is_flagged(self):
        """纯文字面试不能报出"语速 0 字/分钟"这种误导性数据。"""

        class T:
            delivery_metrics = None

        assert summarize_delivery([T()]) == {"is_voice": False}

    def test_voice_summary_aggregates(self):
        class T:
            def __init__(self, **kw):
                self.delivery_metrics = kw

        turns = [
            T(
                transcript_source="asr",
                duration_ms=60_000,
                speech_rate=200,
                filler_ratio=0.02,
                filler_count=4,
                long_pause_count=1,
                longest_pause_ms=3000,
            ),
            T(
                transcript_source="asr",
                duration_ms=40_000,
                speech_rate=300,
                filler_ratio=0.04,
                filler_count=6,
                long_pause_count=3,
                longest_pause_ms=5000,
            ),
        ]
        s = summarize_delivery(turns)
        assert s["is_voice"] is True
        assert s["answered_voice_turns"] == 2
        assert s["total_speaking_ms"] == 100_000
        assert s["avg_speech_rate"] == 250.0
        assert s["total_filler_count"] == 10
        assert s["total_long_pauses"] == 4
        assert s["longest_pause_ms"] == 5000

    async def test_metrics_persist_and_reach_report(
        self, client: AsyncClient, auth_headers: dict
    ):
        resume = await _upload_resume(client, auth_headers)
        jd = await _create_jd(client, auth_headers)
        created = (
            await client.post(
                f"{API}/interviews",
                headers=auth_headers,
                json={
                    "resume_id": resume["id"],
                    "jd_id": jd["id"],
                    "config": {"duration_min": 15, "mode": "video"},
                },
            )
        ).json()
        sid = created["id"]
        assert created["config"]["mode"] == "video"

        await client.post(f"{API}/interviews/{sid}/start", headers=auth_headers)
        resp = await client.post(
            f"{API}/interviews/{sid}/answer",
            headers=auth_headers,
            json={
                "answer": "我给订单表加了联合索引，P99 从 800ms 降到 120ms。",
                "client_elapsed_ms": 58_000,
                "delivery_metrics": {
                    "duration_ms": 58_000,
                    "word_count": 190,
                    "speech_rate": 196.5,
                    "filler_count": 9,
                    "filler_ratio": 0.047,
                    "long_pause_count": 2,
                    "longest_pause_ms": 3200,
                    "transcript_source": "asr",
                },
                "recording_key": "rec-turn-1",
            },
        )
        assert resp.status_code == 200, resp.text

        detail = (await client.get(f"{API}/interviews/{sid}", headers=auth_headers)).json()
        turn = detail["turns"][0]
        assert turn["delivery_metrics"]["speech_rate"] == 196.5
        assert turn["delivery_metrics"]["transcript_source"] == "asr"
        # 录像 key 落库，视频本身留在浏览器本地
        assert turn["recording_key"] == "rec-turn-1"

        # 上报非法指标应被拒（负语速没意义）
        bad = await client.post(
            f"{API}/interviews/{sid}/answer",
            headers=auth_headers,
            json={
                "answer": "x" * 20,
                "delivery_metrics": {"speech_rate": -10},
            },
        )
        assert bad.status_code in (409, 422)

    async def test_report_includes_delivery_summary(
        self, client: AsyncClient, auth_headers: dict
    ):
        resume = await _upload_resume(client, auth_headers)
        jd = await _create_jd(client, auth_headers)
        created = (
            await client.post(
                f"{API}/interviews",
                headers=auth_headers,
                json={
                    "resume_id": resume["id"],
                    "jd_id": jd["id"],
                    "config": {"duration_min": 15, "mode": "video"},
                },
            )
        ).json()
        sid = created["id"]
        await client.post(f"{API}/interviews/{sid}/start", headers=auth_headers)
        await client.post(
            f"{API}/interviews/{sid}/answer",
            headers=auth_headers,
            json={
                "answer": "我负责了订单查询接口的优化，先用 explain 定位到全表扫描，"
                "然后建了联合索引，P99 从 800ms 降到 120ms。",
                "delivery_metrics": {
                    "duration_ms": 45_000,
                    "word_count": 150,
                    "speech_rate": 200,
                    "filler_count": 3,
                    "filler_ratio": 0.02,
                    "long_pause_count": 0,
                    "longest_pause_ms": 0,
                    "transcript_source": "asr",
                },
            },
        )
        report = (
            await client.post(f"{API}/interviews/{sid}/finish", headers=auth_headers)
        ).json()
        assert report["verdict"]

        detail = (await client.get(f"{API}/interviews/{sid}", headers=auth_headers)).json()
        assert detail["delivery_summary"]["is_voice"] is True
        assert detail["delivery_summary"]["answered_voice_turns"] == 1

        per_turn = report["per_turn_feedback"][0]
        assert per_turn["delivery_metrics"]["speech_rate"] == 200
        assert per_turn["interviewer_name"]


# ======================================================================
# 提示 / 标记 / 跳过
# ======================================================================


class TestHintsAndTracking:
    async def _started(self, client: AsyncClient, headers: dict) -> tuple[str, str]:
        resume = await _upload_resume(client, headers)
        jd = await _create_jd(client, headers)
        created = (
            await client.post(
                f"{API}/interviews",
                headers=headers,
                json={"resume_id": resume["id"], "jd_id": jd["id"], "config": {"duration_min": 15}},
            )
        ).json()
        sid = created["id"]
        await client.post(f"{API}/interviews/{sid}/start", headers=headers)
        detail = (await client.get(f"{API}/interviews/{sid}", headers=headers)).json()
        return sid, detail["turns"][0]["id"]

    async def test_hint_gives_structure_not_answer(
        self, client: AsyncClient, auth_headers: dict
    ):
        sid, turn_id = await self._started(client, auth_headers)
        resp = await client.post(
            f"{API}/interviews/{sid}/turns/{turn_id}/hint", headers=auth_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["hint"]
        assert body["already_used"] is False

        # 提示是「回答结构」，不是答案 —— 不应该包含具体技术答案
        assert any(k in body["hint"] for k in ("组织", "结构", "STAR", "按「"))

        # 同一个 turn 再点一次不重复生成
        again = await client.post(
            f"{API}/interviews/{sid}/turns/{turn_id}/hint", headers=auth_headers
        )
        assert again.json()["already_used"] is True
        assert again.json()["hint"] is None

        # 用过提示必须被记录
        detail = (await client.get(f"{API}/interviews/{sid}", headers=auth_headers)).json()
        assert detail["turns"][0]["hinted"] is True

    async def test_mark_toggle(self, client: AsyncClient, auth_headers: dict):
        sid, turn_id = await self._started(client, auth_headers)
        on = await client.post(
            f"{API}/interviews/{sid}/turns/{turn_id}/mark",
            headers=auth_headers,
            json={"marked": True},
        )
        assert on.json()["marked"] is True
        off = await client.post(
            f"{API}/interviews/{sid}/turns/{turn_id}/mark",
            headers=auth_headers,
            json={"marked": False},
        )
        assert off.json()["marked"] is False

    async def test_hint_can_be_disabled(self, client: AsyncClient, auth_headers: dict):
        resume = await _upload_resume(client, auth_headers)
        jd = await _create_jd(client, auth_headers)
        created = (
            await client.post(
                f"{API}/interviews",
                headers=auth_headers,
                json={
                    "resume_id": resume["id"],
                    "jd_id": jd["id"],
                    "config": {"duration_min": 15, "allow_hint": False},
                },
            )
        ).json()
        sid = created["id"]
        await client.post(f"{API}/interviews/{sid}/start", headers=auth_headers)
        detail = (await client.get(f"{API}/interviews/{sid}", headers=auth_headers)).json()
        turn_id = detail["turns"][0]["id"]
        resp = await client.post(
            f"{API}/interviews/{sid}/turns/{turn_id}/hint", headers=auth_headers
        )
        assert resp.status_code == 409

    async def test_skip_records_zero_score_and_advances(
        self, client: AsyncClient, auth_headers: dict
    ):
        """跳过必须能推进面试，并且记为 0 分而不是让整场卡死。"""
        sid, _ = await self._started(client, auth_headers)
        resp = await client.post(
            f"{API}/interviews/{sid}/skip",
            headers=auth_headers,
            json={"reason": "这个技术我没接触过", "client_elapsed_ms": 20_000},
        )
        assert resp.status_code == 200, resp.text
        events = parse_sse(resp.text)
        assert "question" in [e for e, _ in events]
        assert "error" not in [e for e, _ in events]

        detail = (await client.get(f"{API}/interviews/{sid}", headers=auth_headers)).json()
        skipped = detail["turns"][0]
        assert skipped["skipped"] is True
        assert "跳过" in skipped["answer"]

    async def test_skip_can_be_disabled(self, client: AsyncClient, auth_headers: dict):
        resume = await _upload_resume(client, auth_headers)
        jd = await _create_jd(client, auth_headers)
        created = (
            await client.post(
                f"{API}/interviews",
                headers=auth_headers,
                json={
                    "resume_id": resume["id"],
                    "jd_id": jd["id"],
                    "config": {"duration_min": 15, "allow_skip": False},
                },
            )
        ).json()
        sid = created["id"]
        await client.post(f"{API}/interviews/{sid}/start", headers=auth_headers)
        resp = await client.post(f"{API}/interviews/{sid}/skip", headers=auth_headers, json={})
        assert resp.status_code == 409

    async def test_hint_and_skip_counts_appear_in_report(
        self, client: AsyncClient, auth_headers: dict
    ):
        sid, turn_id = await self._started(client, auth_headers)
        await client.post(f"{API}/interviews/{sid}/turns/{turn_id}/hint", headers=auth_headers)
        await client.post(
            f"{API}/interviews/{sid}/turns/{turn_id}/mark",
            headers=auth_headers,
            json={"marked": True},
        )
        await client.post(f"{API}/interviews/{sid}/skip", headers=auth_headers, json={})
        report = (
            await client.post(f"{API}/interviews/{sid}/finish", headers=auth_headers)
        ).json()
        assert report["verdict"]

        detail = (await client.get(f"{API}/interviews/{sid}", headers=auth_headers)).json()
        honesty = detail["config"]["_honesty"]
        assert honesty["hint_count"] == 1
        assert honesty["marked_count"] == 1

        # 跳过的那题在逐题点评里必须体现
        skipped_feedback = [t for t in report["per_turn_feedback"] if t["skipped"]]
        assert len(skipped_feedback) == 1
        assert skipped_feedback[0]["weighted_score"] == 1.0


# ======================================================================
# 参考答案
# ======================================================================


class TestSuggestedAnswer:
    async def _answered(self, client: AsyncClient, headers: dict, *, answer: str) -> tuple[str, str]:
        resume = await _upload_resume(client, headers)
        jd = await _create_jd(client, headers)
        created = (
            await client.post(
                f"{API}/interviews",
                headers=headers,
                json={"resume_id": resume["id"], "jd_id": jd["id"], "config": {"duration_min": 15}},
            )
        ).json()
        sid = created["id"]
        await client.post(f"{API}/interviews/{sid}/start", headers=headers)
        await client.post(
            f"{API}/interviews/{sid}/answer", headers=headers, json={"answer": answer}
        )
        detail = (await client.get(f"{API}/interviews/{sid}", headers=headers)).json()
        return sid, detail["turns"][0]["id"]

    async def test_generates_with_placeholders_instead_of_fabricating(
        self, client: AsyncClient, auth_headers: dict
    ):
        """核心约束：宁可给占位符，也不许编造数据。"""
        sid, turn_id = await self._answered(
            client, auth_headers, answer="我参与了订单系统的开发，做了一些优化工作。"
        )
        resp = await client.post(
            f"{API}/interviews/{sid}/turns/{turn_id}/suggested-answer", headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        payload = resp.json()["suggested_answer"]
        assert payload["outline"] and payload["reference_answer"]
        assert payload["placeholders"], "缺少事实时必须给出占位符而不是编造"
        assert any("[" in p for p in payload["placeholders"])

    async def test_is_cached_and_idempotent(self, client: AsyncClient, auth_headers: dict):
        sid, turn_id = await self._answered(
            client, auth_headers, answer="我用了 Redis，命中率 96%。"
        )
        first = await client.post(
            f"{API}/interviews/{sid}/turns/{turn_id}/suggested-answer", headers=auth_headers
        )
        second = await client.post(
            f"{API}/interviews/{sid}/turns/{turn_id}/suggested-answer", headers=auth_headers
        )
        assert first.status_code == second.status_code == 200
        # 缓存：第二次返回完全一致，不再花模型调用
        assert first.json()["suggested_answer"] == second.json()["suggested_answer"]

        detail = (await client.get(f"{API}/interviews/{sid}", headers=auth_headers)).json()
        assert detail["turns"][0]["has_suggested_answer"] is True

    async def test_rejected_before_answer(self, client: AsyncClient, auth_headers: dict):
        resume = await _upload_resume(client, auth_headers)
        jd = await _create_jd(client, auth_headers)
        created = (
            await client.post(
                f"{API}/interviews",
                headers=auth_headers,
                json={"resume_id": resume["id"], "jd_id": jd["id"], "config": {"duration_min": 15}},
            )
        ).json()
        sid = created["id"]
        await client.post(f"{API}/interviews/{sid}/start", headers=auth_headers)
        detail = (await client.get(f"{API}/interviews/{sid}", headers=auth_headers)).json()
        turn_id = detail["turns"][0]["id"]
        resp = await client.post(
            f"{API}/interviews/{sid}/turns/{turn_id}/suggested-answer", headers=auth_headers
        )
        assert resp.status_code == 409


# ======================================================================
# 暂停 / 继续
# ======================================================================


class TestPauseResume:
    async def test_pause_blocks_answering_and_resume_restores(
        self, client: AsyncClient, auth_headers: dict
    ):
        resume = await _upload_resume(client, auth_headers)
        jd = await _create_jd(client, auth_headers)
        created = (
            await client.post(
                f"{API}/interviews",
                headers=auth_headers,
                json={"resume_id": resume["id"], "jd_id": jd["id"], "config": {"duration_min": 15}},
            )
        ).json()
        sid = created["id"]
        await client.post(f"{API}/interviews/{sid}/start", headers=auth_headers)

        paused = await client.post(f"{API}/interviews/{sid}/pause", headers=auth_headers)
        assert paused.status_code == 200
        assert paused.json()["status"] == "paused"

        blocked = await client.post(
            f"{API}/interviews/{sid}/answer", headers=auth_headers, json={"answer": "继续答题内容"}
        )
        assert blocked.status_code == 409
        assert "暂停" in blocked.json()["message"]

        resumed = await client.post(f"{API}/interviews/{sid}/resume", headers=auth_headers)
        assert resumed.status_code == 200
        assert resumed.json()["status"] == "running"
        assert resumed.json()["paused_seconds"] >= 0

        ok = await client.post(
            f"{API}/interviews/{sid}/answer",
            headers=auth_headers,
            json={"answer": "我用了 Redis 做缓存，命中率 96%，P99 从 800ms 降到 120ms。"},
        )
        assert ok.status_code == 200

    async def test_pause_is_idempotent(self, client: AsyncClient, auth_headers: dict):
        resume = await _upload_resume(client, auth_headers)
        jd = await _create_jd(client, auth_headers)
        created = (
            await client.post(
                f"{API}/interviews",
                headers=auth_headers,
                json={"resume_id": resume["id"], "jd_id": jd["id"], "config": {"duration_min": 15}},
            )
        ).json()
        sid = created["id"]
        await client.post(f"{API}/interviews/{sid}/pause", headers=auth_headers)
        again = await client.post(f"{API}/interviews/{sid}/pause", headers=auth_headers)
        assert again.status_code == 200

    async def test_finish_from_paused(self, client: AsyncClient, auth_headers: dict):
        """暂停中也要能生成报告，否则学生会被卡住。"""
        resume = await _upload_resume(client, auth_headers)
        jd = await _create_jd(client, auth_headers)
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
            json={"answer": "我用了 Redis 做缓存，命中率 96%。"},
        )
        await client.post(f"{API}/interviews/{sid}/pause", headers=auth_headers)
        report = await client.post(f"{API}/interviews/{sid}/finish", headers=auth_headers)
        assert report.status_code == 200


# ======================================================================
# 工具
# ======================================================================


async def _upload_resume(client: AsyncClient, headers: dict) -> dict:
    from app.tests.conftest import SAMPLE_RESUME_TEXT
    from app.tests.test_api_flow import make_docx

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


async def _create_jd(client: AsyncClient, headers: dict) -> dict:
    resp = await client.post(
        f"{API}/jds",
        headers=headers,
        json={"title": "后端开发工程师", "company": "某某科技", "raw_text": SAMPLE_JD_TEXT},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.parametrize("stage", STAGES)
def test_hint_exists_for_every_stage(stage: str):
    """每个环节都必须有提示文案，否则学生在某个环节点提示会拿到空字符串。"""
    from app.services.interview_service import hint_for_stage

    hint = hint_for_stage(stage)
    assert len(hint) >= 20
