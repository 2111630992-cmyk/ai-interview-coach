"""端到端验收脚本：对**真实运行中的服务**跑一遍完整业务链路。

与 pytest 的区别：pytest 用 ASGITransport（进程内），这里走真实 HTTP + 真实 SQLite 文件 +
真实 SSE 流，能覆盖 ASGI 传输层、CORS、流式分帧、持久化落盘等集成问题。

用法：
    1. 先启动后端：uvicorn app.main:app --port 8000
    2. python scripts/e2e_check.py [base_url]

退出码 0 表示全部检查通过。
"""

from __future__ import annotations

import io
import json
import sys
import time

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
API = f"{BASE}/api/v1"

RESUME_TEXT = """张三
本科 计算机科学与技术 某某大学 2019.09-2023.06 GPA 3.7
专业技能
熟练掌握 Java、Python、MySQL、Redis、Kafka、Spring Boot、Docker
项目经历
- 订单系统重构：把下单接口 P99 从 800ms 降到 120ms，QPS 提升到 3000
- 推荐服务：基于 Redis 做热点缓存，缓存命中率 96%
实习经历
- 某互联网公司 后端开发实习生 2022.07-2022.10 参与支付链路开发
获奖情况
- 国家励志奖学金
"""

JD_TEXT = (
    "岗位职责：负责后端服务的设计与开发，参与高并发交易系统的架构优化。\n"
    "任职要求：\n"
    "1. 熟练掌握 Java、Spring Boot，熟悉 MySQL 索引优化与事务机制；\n"
    "2. 熟悉 Redis 缓存、Kafka 消息队列，了解分布式与微服务架构；\n"
    "3. 有良好的沟通表达与团队协作能力，具备 owner 意识。\n"
)

ANSWERS = [
    (
        "我当时负责订单查询接口的优化。先用 explain 发现是全表扫描，于是建了 (user_id, status) "
        "的联合索引，并且把结果缓存到 Redis。P99 从 800ms 降到 120ms，QPS 提升到 3000。"
    ),
    (
        "缓存这块我用了 Redis，命中率 96%。不一致的时候用「先更新数据库再删缓存」的策略，"
        "并且给缓存加了随机过期时间避免雪崩。"
    ),
    "团队协作上，我和前端同学对接口字段有分歧，我主动拉了个会对齐字段定义并写成文档，最后按时上线。",
    "我参与了后端开发，做了一些优化工作，性能提升比较明显。",
    "对于不熟悉的技术，我会先看官方文档，再写个最小 demo 验证，最后才用到项目里。",
    "我一般会先定位问题范围，再逐步缩小排查，比如先看监控指标再抓链路日志。",
    "我希望加入一个技术氛围好、能快速成长的团队。",
    "我想了解一下团队的技术栈和日常的工作节奏。",
    "我没有其他问题了，谢谢面试官。",
]

RESULTS: list[tuple[bool, str]] = []


def check(ok: bool, label: str, extra: str = "") -> bool:
    RESULTS.append((ok, label))
    mark = "PASS" if ok else "FAIL"
    line = f"[{mark}] {label}"
    if extra:
        line += f" — {extra}"
    print(line, flush=True)
    return ok


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for block in body.replace("\r\n", "\n").split("\n\n"):
        if not block.strip():
            continue
        event = "message"
        data_lines: list[str] = []
        for line in block.split("\n"):
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        if not data_lines:
            continue
        raw = "\n".join(data_lines)
        try:
            events.append((event, json.loads(raw)))
        except json.JSONDecodeError:
            pass
    return events


def make_docx(text: str) -> bytes:
    from docx import Document

    document = Document()
    for line in text.splitlines():
        document.add_paragraph(line)
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()


def main() -> int:
    print(f"=== 端到端验收开始：{BASE} ===\n", flush=True)
    client = httpx.Client(timeout=120.0)

    # ---------- 0. 健康检查 ----------
    r = client.get(f"{API}/health")
    if not check(r.status_code == 200, "健康检查", r.text[:120]):
        return 1
    health = r.json()
    check(health.get("llm_mode") in ("mock", "live"), "LLM 模式已明确上报", health.get("llm_mode", ""))
    print(f"     LLM 模式：{health.get('llm_mode')}  模型：{health.get('llm_model')}\n", flush=True)

    # ---------- 1. 注册 ----------
    email = f"e2e_{int(time.time())}@example.com"
    r = client.post(f"{API}/auth/register", json={"email": email, "password": "secret123", "nickname": "端到端"})
    if not check(r.status_code == 200, "注册账号", r.text[:160]):
        return 1
    token = r.json()["access_token"]
    H = {"Authorization": f"Bearer {token}"}

    check(client.get(f"{API}/auth/me", headers=H).status_code == 200, "读取当前用户")

    # ---------- 2. 上传简历 ----------
    r = client.post(
        f"{API}/resumes",
        headers=H,
        files={
            "file": (
                "resume.docx",
                make_docx(RESUME_TEXT),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    if not check(r.status_code == 200, "上传并解析简历", r.text[:200]):
        return 1
    resume = r.json()
    skills = resume["parsed"].get("skills", [])
    check(len(skills) >= 3, "简历技能抽取", f"{len(skills)} 项：{'、'.join(skills[:6])}")

    # ---------- 3. 创建 JD ----------
    r = client.post(f"{API}/jds", headers=H, json={"title": "后端开发工程师", "company": "某某科技", "raw_text": JD_TEXT})
    if not check(r.status_code == 200, "创建岗位 JD", r.text[:200]):
        return 1
    jd = r.json()
    model = jd["competency_model"]
    check(len(model.get("hard_skills", [])) >= 3, "JD 能力模型抽取", f"{len(model.get('hard_skills', []))} 项硬技能")
    wsum = sum(model.get("weights", {}).values())
    check(abs(wsum - 1.0) < 1e-6, "JD 权重归一化", f"sum={wsum:.4f}")

    # ---------- 4. 匹配分析 + 缓存 ----------
    t0 = time.time()
    r = client.post(f"{API}/match", headers=H, json={"resume_id": resume["id"], "jd_id": jd["id"]})
    if not check(r.status_code == 200, "匹配分析", r.text[:200]):
        return 1
    elapsed_first = time.time() - t0
    match = r.json()
    check(0 <= match["match_score"] <= 100, "匹配度在 0-100 区间", str(match["match_score"]))

    t0 = time.time()
    r2 = client.post(f"{API}/match", headers=H, json={"resume_id": resume["id"], "jd_id": jd["id"]})
    elapsed_second = time.time() - t0
    check(r2.json().get("cached") is True, "二次匹配命中缓存", f"{elapsed_second*1000:.0f}ms（首次 {elapsed_first*1000:.0f}ms）")

    # ---------- 5. 创建面试 ----------
    r = client.post(
        f"{API}/interviews",
        headers=H,
        json={
            "resume_id": resume["id"],
            "jd_id": jd["id"],
            "config": {"duration_min": 15, "interview_type": "technical", "pressure_mode": True},
        },
    )
    if not check(r.status_code == 200, "创建面试并生成计划", r.text[:240]):
        return 1
    session = r.json()
    sid = session["id"]
    plan = session["plan"]
    check(len(plan.get("competencies", [])) >= 3, "面试计划含考察点", f"{len(plan['competencies'])} 个")
    check(len(plan.get("stages", [])) == 6, "面试计划含 6 个环节")
    sources = {c["source"] for c in plan["competencies"]}
    check("resume" in sources, "计划包含简历来源考察点", "、".join(sorted(sources)))

    # ---------- 6. 开始面试（真实 SSE） ----------
    r = client.post(f"{API}/interviews/{sid}/start", headers=H)
    check(r.status_code == 200, "开始面试（SSE）", r.headers.get("content-type", ""))
    check("text/event-stream" in r.headers.get("content-type", ""), "响应为 event-stream")
    events = parse_sse(r.text)
    kinds = [e for e, _ in events]
    check("question" in kinds and "done" in kinds, "首题事件完整", "、".join(sorted(set(kinds))))
    first_q = next((d for e, d in events if e == "question"), {})
    check(len(first_q.get("question", "")) > 5, "首题为真实文本", first_q.get("question", "")[:60])
    tokens = "".join(d.get("delta", "") for e, d in events if e == "token")
    check(tokens.strip() == first_q.get("question", "").strip(), "流式 token 拼接与落库问题一致")

    # ---------- 7. 多轮问答直到结束 ----------
    rounds = 0
    followups = 0
    session_finished = False
    stages_seen: set[str] = set()
    for i in range(40):
        detail = client.get(f"{API}/interviews/{sid}", headers=H).json()
        turns = detail["turns"]
        if turns and turns[-1]["answer"]:
            # 上一题已答但下一题未生成（不应发生）；用恢复接口推进
            r = client.post(f"{API}/interviews/{sid}/next", headers=H)
        else:
            r = client.post(
                f"{API}/interviews/{sid}/answer",
                headers=H,
                json={"answer": ANSWERS[i % len(ANSWERS)], "client_elapsed_ms": 45000},
            )
        if r.status_code != 200:
            check(False, f"第 {i+1} 轮提交", r.text[:200])
            break

        ev = parse_sse(r.text)
        if any(e == "error" for e, _ in ev):
            check(False, f"第 {i+1} 轮 SSE 返回错误", str(ev[-1]))
            break

        q = next((d for e, d in ev if e == "question"), None)
        done = next((d for e, d in ev if e == "done"), None)
        if q:
            rounds += 1
            stages_seen.add(q["stage"])
            if q["is_followup"]:
                followups += 1
        if done and done.get("session_finished"):
            session_finished = True
            break

    check(session_finished, "面试能自然结束", f"{rounds} 轮")
    check(rounds >= 6, "轮次数量合理", f"{rounds} 轮")
    check(followups >= 1, "确实发生了追问", f"{followups} 次追问")
    check(len(stages_seen) >= 4, "覆盖多个环节", "、".join(sorted(stages_seen)))

    # ---------- 8. 生成报告 ----------
    r = client.post(f"{API}/interviews/{sid}/finish", headers=H)
    if not check(r.status_code == 200, "生成面试报告", r.text[:240]):
        return 1
    report = r.json()

    check(report["verdict"] in ("strong_pass", "pass", "borderline", "fail"), "结论档位合法", report["verdict"])
    check(len(report["summary"]) >= 50, "报告总评有实质内容", f"{len(report['summary'])} 字")
    check(len(report["dimension_scores"]) == 5, "五维评分完整", str(sorted(report["dimension_scores"])))
    check(
        all(0 <= v <= 100 for v in report["dimension_scores"].values()),
        "五维分数在 0-100",
        str({k: round(v) for k, v in report["dimension_scores"].items()}),
    )
    check(1 <= len(report["top_problems"]) <= 3, "Top 问题数量 ≤ 3", str(len(report["top_problems"])))
    check(len(report["training_plan"]) == 7, "训练计划为 7 天", str(len(report["training_plan"])))

    banned = ("多看书", "多练习", "多刷题", "加强学习")
    vague = [d for d in report["training_plan"] if any(b in d["task"] for b in banned)]
    check(not vague, "训练计划无空话（无“多看书/多练习”）")

    with_evidence = [t for t in report["per_turn_feedback"] if t["evidence"]]
    check(len(with_evidence) > 0, "逐题点评引用了候选人原话", f"{len(with_evidence)}/{len(report['per_turn_feedback'])} 题有证据")

    rewritten = [t for t in report["per_turn_feedback"] if t["rewritten_answer"]]
    check(len(rewritten) > 0, "生成了改写示范", f"{len(rewritten)} 题")

    # ---------- 9. 幂等与权限 ----------
    r2 = client.post(f"{API}/interviews/{sid}/finish", headers=H)
    check(r2.json().get("id") == report["id"], "重复生成报告幂等")

    guest = client.post(f"{API}/auth/guest").json()
    GH = {"Authorization": f"Bearer {guest['access_token']}"}
    check(
        client.get(f"{API}/interviews/{sid}", headers=GH).status_code == 404,
        "越权访问他人面试返回 404",
    )

    # ---------- 10. 统计 ----------
    overview = client.get(f"{API}/stats/overview", headers=H).json()
    check(overview["finished_count"] == 1, "统计：已完成面试数", str(overview["finished_count"]))
    trend = client.get(f"{API}/stats/trend", headers=H).json()
    check(len(trend) == 1 and trend[0]["total_score"] is not None, "统计：分数趋势", str(trend[0]["total_score"] if trend else None))

    # ---------- 11. 第二轮迭代能力 ----------
    print("\n--- 面试官人格 / 视频面试 / 提示跳过 / 参考答案 / 暂停续做 ---\n", flush=True)
    _check_iteration_features(client, H, resume, jd)

    # ---------- 汇总 ----------
    print("\n=== 报告摘要预览 ===", flush=True)
    print(report["summary"][:400], flush=True)
    print(f"\n结论：{report['verdict_label']}", flush=True)
    if report["top_problems"]:
        print(f"首要问题：{report['top_problems'][0]['title']}", flush=True)
        print(f"  依据（你的原话）：{report['top_problems'][0]['evidence'][:100]}", flush=True)
    print("\n=== 第一天训练任务 ===", flush=True)
    print(report["training_plan"][0]["task"], flush=True)

    passed = sum(1 for ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print(f"\n=== 端到端验收：{passed}/{total} 通过 ===", flush=True)
    if passed != total:
        print("失败项：", [label for ok, label in RESULTS if not ok], flush=True)
    return 0 if passed == total else 1


def _new_session(client: httpx.Client, H: dict, resume: dict, jd: dict, config: dict) -> dict:
    r = client.post(
        f"{API}/interviews",
        headers=H,
        json={"resume_id": resume["id"], "jd_id": jd["id"], "config": config},
    )
    if r.status_code != 200:
        check(False, "创建面试会话", r.text[:200])
        return {}
    return r.json()


def _check_iteration_features(client: httpx.Client, H: dict, resume: dict, jd: dict) -> None:
    """覆盖第二轮迭代新增的全部能力。"""

    # ---------- 面试官人格 ----------
    personas = client.get(f"{API}/interviews/meta/interviewers?language=zh", headers=H)
    check(personas.status_code == 200, "面试官人格接口", f"HTTP {personas.status_code}")
    plist = personas.json()
    check(len(plist) == 6, "内置 6 位面试官", str([p["name"] for p in plist]))
    check(
        all(p["bio"] and p["style"] and p["focus_areas"] for p in plist),
        "每位面试官都有背景/风格/关注点（换人才有意义）",
    )
    en = client.get(f"{API}/interviews/meta/interviewer/hr?language=en", headers=H).json()
    check(en["name"] == "Lisa Wang", "人格支持中英双语", en["name"])

    # ---------- 多轮换人 ----------
    session = _new_session(
        client,
        H,
        resume,
        jd,
        {"duration_min": 15, "mode": "video", "interviewer_mode": "panel"},
    )
    sid = session.get("id")
    roster = session.get("roster", {})
    check(len(roster) == 6, "多轮模式：六个环节都有面试官分配", str(len(roster)))
    distinct = {v["type"] for v in roster.values()}
    check(len(distinct) >= 4, "多轮模式：至少 4 位不同面试官", "、".join(sorted(distinct)))
    check(session.get("config", {}).get("mode") == "video", "视频面试配置已生效")

    # ---------- 开始面试 + 换人提示 ----------
    r = client.post(f"{API}/interviews/{sid}/start", headers=H)
    events = parse_sse(r.text)
    q0 = next((d for e, d in events if e == "question"), None)
    check(q0 is not None and q0.get("interviewer") is not None, "首题带面试官信息", (q0 or {}).get("interviewer", {}).get("name", ""))

    # 答到进入第二个环节，验证换人
    changed = False
    for _ in range(12):
        detail = client.get(f"{API}/interviews/{sid}", headers=H).json()
        turns = detail["turns"]
        if turns and turns[-1]["answer"]:
            r = client.post(f"{API}/interviews/{sid}/next", headers=H)
        else:
            r = client.post(
                f"{API}/interviews/{sid}/answer",
                headers=H,
                json={
                    "answer": "我负责订单查询接口优化，先看慢查询日志定位全表扫描，"
                    "加了 (user_id,status) 联合索引，P99 从 800ms 降到 120ms。",
                    "client_elapsed_ms": 52000,
                },
            )
        ev = parse_sse(r.text)
        q = next((d for e, d in ev if e == "question"), None)
        if q and q["stage"] != q0["stage"]:
            changed = q.get("interviewer", {}).get("type") != q0.get("interviewer", {}).get("type")
            check(True, "进入新环节", f"{q0['stage']} → {q['stage']}，面试官 {'已更换' if changed else '未更换'}")
            break
    check(changed, "换环节时更换面试官（多轮模式核心）")

    # ---------- 视频面试：表达指标 ----------
    detail = client.get(f"{API}/interviews/{sid}", headers=H).json()
    pending = detail["turns"][-1]
    r = client.post(
        f"{API}/interviews/{sid}/answer",
        headers=H,
        json={
            "answer": "我用了 Redis 做热点缓存，命中率 96%，把 P99 从 800ms 降到 120ms。",
            "client_elapsed_ms": 61000,
            "delivery_metrics": {
                "duration_ms": 61000,
                "word_count": 210,
                "speech_rate": 206.6,
                "filler_count": 12,
                "filler_ratio": 0.071,
                "long_pause_count": 2,
                "longest_pause_ms": 3400,
                "transcript_source": "asr",
            },
            "recording_key": f"{sid}:{pending['turn_index']}:e2e",
        },
    )
    check(r.status_code == 200, "提交带表达指标的回答", f"HTTP {r.status_code}")

    detail = client.get(f"{API}/interviews/{sid}", headers=H).json()
    recorded = [t for t in detail["turns"] if t["delivery_metrics"]]
    check(len(recorded) == 1, "表达指标已落库", str(len(recorded)))
    if recorded:
        dm = recorded[0]["delivery_metrics"]
        check(dm["speech_rate"] == 206.6, "语速原样保存", str(dm["speech_rate"]))
        check(dm["transcript_source"] == "asr", "标注为语音作答", dm["transcript_source"])
        check(recorded[0]["recording_key"] is not None, "录像 key 已记录（视频本身留本地）")

    bad = client.post(
        f"{API}/interviews/{sid}/answer",
        headers=H,
        json={"answer": "这是足够长的回答内容用于测试", "delivery_metrics": {"speech_rate": -5}},
    )
    check(bad.status_code in (409, 422), "非法表达指标被拒绝", f"HTTP {bad.status_code}")

    # ---------- 提示 ----------
    detail = client.get(f"{API}/interviews/{sid}", headers=H).json()
    current = detail["turns"][-1]
    hint = client.post(f"{API}/interviews/{sid}/turns/{current['id']}/hint", headers=H)
    check(hint.status_code == 200, "请求回答结构提示", f"HTTP {hint.status_code}")
    hb = hint.json()
    check(bool(hb.get("hint")), "提示有内容", (hb.get("hint") or "")[:50])
    check(
        any(k in (hb.get("hint") or "") for k in ("组织", "结构", "STAR", "按「")),
        "提示给的是回答结构而不是答案",
    )
    again = client.post(f"{API}/interviews/{sid}/turns/{current['id']}/hint", headers=H)
    check(again.json().get("already_used") is True, "重复请求提示不重复生成")
    after = client.get(f"{API}/interviews/{sid}", headers=H).json()["turns"][-1]
    check(after["hinted"] is True, "用过提示被永久记录（诚实机制）")

    # ---------- 标记 ----------
    mk = client.post(
        f"{API}/interviews/{sid}/turns/{current['id']}/mark", headers=H, json={"marked": True}
    )
    check(mk.json().get("marked") is True, "标记待复习")
    un = client.post(
        f"{API}/interviews/{sid}/turns/{current['id']}/mark", headers=H, json={"marked": False}
    )
    check(un.json().get("marked") is False, "取消标记")

    # ---------- 参考答案 ----------
    # 注意：参考答案只对**已作答且已评分**的题目有意义，
    # 对还没回答的那道题请求应该被拒绝（下面单独验证）。
    pending_turn = client.get(f"{API}/interviews/{sid}", headers=H).json()["turns"][-1]
    too_early = client.post(
        f"{API}/interviews/{sid}/turns/{pending_turn['id']}/suggested-answer", headers=H
    )
    check(too_early.status_code == 409, "未作答的题不能要参考答案", f"HTTP {too_early.status_code}")

    answered = [
        t for t in client.get(f"{API}/interviews/{sid}", headers=H).json()["turns"] if t["answer"]
    ][-1]
    sa = client.post(f"{API}/interviews/{sid}/turns/{answered['id']}/suggested-answer", headers=H)
    check(sa.status_code == 200, "生成参考答案", f"HTTP {sa.status_code}")
    payload = sa.json().get("suggested_answer", {})
    check(bool(payload.get("outline")) and bool(payload.get("reference_answer")), "参考答案含结构与正文")
    check(
        bool(payload.get("placeholders")),
        "缺事实时给占位符而不是编造",
        "、".join(payload.get("placeholders", [])[:2]),
    )
    sa2 = client.post(f"{API}/interviews/{sid}/turns/{answered['id']}/suggested-answer", headers=H)
    check(
        sa2.json().get("suggested_answer") == payload,
        "参考答案幂等缓存（同一题只花一次模型调用）",
    )

    # ---------- 跳过 ----------
    detail = client.get(f"{API}/interviews/{sid}", headers=H).json()
    if not detail["turns"][-1]["answer"]:
        pass
    else:
        client.post(f"{API}/interviews/{sid}/next", headers=H)
    sk = client.post(
        f"{API}/interviews/{sid}/skip",
        headers=H,
        json={"reason": "完全没接触过分布式事务", "client_elapsed_ms": 15000},
    )
    check(sk.status_code == 200, "跳过当前题（不中断面试）", f"HTTP {sk.status_code}")
    ev = parse_sse(sk.text)
    check("question" in [e for e, _ in ev], "跳过后立刻给出下一题")
    detail = client.get(f"{API}/interviews/{sid}", headers=H).json()
    skipped = [t for t in detail["turns"] if t["skipped"]]
    check(len(skipped) == 1, "跳过状态已记录", str(len(skipped)))

    # ---------- 暂停 / 继续 ----------
    p = client.post(f"{API}/interviews/{sid}/pause", headers=H)
    check(p.json().get("status") == "paused", "暂停面试")
    blocked = client.post(
        f"{API}/interviews/{sid}/answer", headers=H, json={"answer": "暂停期间不该能答题的内容"}
    )
    check(blocked.status_code == 409, "暂停期间拒绝答题", f"HTTP {blocked.status_code}")
    time.sleep(1.2)
    rp = client.post(f"{API}/interviews/{sid}/resume", headers=H)
    check(rp.json().get("status") == "running", "继续面试")
    check(
        rp.json().get("paused_seconds", 0) >= 1,
        "暂停时长被扣除（不计入面试时长）",
        f"{rp.json().get('paused_seconds')} 秒",
    )

    # ---------- 报告包含新增信息 ----------
    report = client.post(f"{API}/interviews/{sid}/finish", headers=H).json()
    check(report.get("verdict") in ("strong_pass", "pass", "borderline", "fail"), "生成报告")
    check(
        report.get("delivery_summary", {}).get("is_voice") is True,
        "报告含语音表达指标汇总",
        str(report.get("delivery_summary", {}).get("avg_speech_rate")),
    )
    per_turn = report.get("per_turn_feedback", [])
    check(
        all(t.get("interviewer_name") for t in per_turn),
        "逐题点评标注了面试官",
        "、".join(sorted({t.get("interviewer_name") for t in per_turn})),
    )
    risk_turns = [t for t in per_turn if t.get("risk_points")]
    check(len(risk_turns) > 0, "逐题点评包含「下一步会被追问什么」", f"{len(risk_turns)} 题")
    detail = client.get(f"{API}/interviews/{sid}", headers=H).json()
    honesty = detail["config"].get("_honesty", {})
    check(honesty.get("hint_count") == 1, "报告记录提示使用次数", str(honesty.get("hint_count")))
    check(honesty.get("skip_count") == 1, "报告记录跳过次数", str(honesty.get("skip_count")))
    skipped_fb = [t for t in per_turn if t.get("skipped")]
    check(
        len(skipped_fb) == 1 and skipped_fb[0]["weighted_score"] == 1.0,
        "跳过的那题在报告里计 0 分",
        str(skipped_fb[0]["weighted_score"] if skipped_fb else None),
    )

    # ---------- 练习模式 vs 模拟模式 ----------
    practice = _new_session(
        client, H, resume, jd, {"duration_min": 15, "feedback_mode": "practice", "mode": "text"}
    )
    check(practice.get("expose_scores") is True, "练习模式暴露分数")
    psid = practice["id"]
    client.post(f"{API}/interviews/{psid}/start", headers=H)
    r = client.post(
        f"{API}/interviews/{psid}/answer",
        headers=H,
        json={"answer": "我用了 Redis 做缓存，命中率 96%，P99 从 800ms 降到 120ms。"},
    )
    check("eval" in [e for e, _ in parse_sse(r.text)], "练习模式下发单题评分事件")

    sim = _new_session(
        client, H, resume, jd, {"duration_min": 15, "feedback_mode": "simulation", "mode": "text"}
    )
    check(sim.get("expose_scores") is False, "模拟模式隐藏分数")
    ssid = sim["id"]
    client.post(f"{API}/interviews/{ssid}/start", headers=H)
    r = client.post(
        f"{API}/interviews/{ssid}/answer",
        headers=H,
        json={"answer": "我用了 Redis 做缓存，命中率 96%，P99 从 800ms 降到 120ms。"},
    )
    check("eval" not in [e for e, _ in parse_sse(r.text)], "模拟模式不下发评分（保持沉浸感）")


if __name__ == "__main__":
    sys.exit(main())
