"""Mock AI 服务：确定性规则引擎。

存在意义有两个，都很实际：
1. **没有 API Key 也能完整演示与测试** —— 招聘方/老师拿到仓库就能跑。
2. **真实模型故障时的兜底** —— 不会出现"面试进行到一半全白屏"。

它不是一个"返回假数据的占位符"：它会真正解析简历、按 JD 抽能力点、按规则追问、
按 rubric 打分、按薄弱维度生成 7 天计划。只是所有判断都由可读的规则给出，而不是模型。

注意：**Mock 的分数不代表真实模型效果**，README 已明确标注。
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from app.constants import (
    DIMENSION_LABELS,
    INTENT_FOLLOWUP_CHALLENGE,
    INTENT_FOLLOWUP_CONCRETE,
    INTENT_FOLLOWUP_DETAIL,
    INTENT_OPENING,
    INTENT_STAGE_TRANSITION,
    INTENT_WRAPUP,
    INTERVIEW_TYPES,
    STAGE_META,
    STAGES,
)
from app.schemas.llm import (
    CompetencyItem,
    EducationItem,
    Evaluation,
    InternshipItem,
    InterviewPlan,
    JDParse,
    MatchOut,
    Problem,
    ProjectItem,
    ReportOut,
    ResumeParse,
    StagePlan,
    SuggestedAnswer,
    TopProblem,
    TrainingDay,
)
from app.services.ai_types import (
    EvaluateContext,
    QuestionContext,
    ReportContext,
    SuggestedAnswerContext,
)
from app.services.interview_engine import analyze_answer

# ======================================================================
# 词表
# ======================================================================

TECH_VOCAB: list[str] = [
    # 语言
    "Java", "Python", "Go", "Golang", "C++", "C#", "JavaScript", "TypeScript", "Rust", "Kotlin", "Swift", "PHP", "Scala",
    # 后端 / 框架
    "Spring Boot", "Spring", "MyBatis", "Django", "Flask", "FastAPI", "Express", "Node.js", "Netty", "Dubbo", "gRPC",
    # 数据库
    "MySQL", "PostgreSQL", "Redis", "MongoDB", "Elasticsearch", "Oracle", "SQLite", "HBase", "ClickHouse", "TiDB",
    # 中间件
    "Kafka", "RabbitMQ", "RocketMQ", "Nginx", "Zookeeper", "Nacos", "etcd",
    # 云原生 / 运维
    "Docker", "Kubernetes", "K8s", "Jenkins", "Prometheus", "Grafana", "Linux", "Shell", "CI/CD", "Git",
    # 前端
    "React", "Vue", "Vue.js", "Angular", "Webpack", "Vite", "Tailwind", "Next.js", "HTML", "CSS", "Sass",
    # 数据 / AI
    "PyTorch", "TensorFlow", "Pandas", "NumPy", "Spark", "Hadoop", "Flink", "Hive", "SQL", "LLM", "RAG", "Transformer", "BERT", "LangChain",
    # 计算机基础
    "数据结构", "算法", "操作系统", "计算机网络", "设计模式", "分布式", "微服务", "高并发", "JVM", "GC", "多线程", "索引", "事务", "缓存", "消息队列",
]

SOFT_SKILLS: list[str] = [
    "沟通表达", "团队协作", "跨部门推动", "项目管理", "owner 意识", "抗压能力", "快速学习", "问题拆解", "文档写作", "技术分享",
]

_SECTION_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("education", ("教育背景", "教育经历", "学历", "教育")),
    ("skills", ("专业技能", "技能清单", "技术栈", "技能", "掌握技能")),
    ("projects", ("项目经历", "项目经验", "项目")),
    ("internships", ("实习经历", "工作经历", "实习", "工作经验")),
    ("awards", ("获奖情况", "荣誉", "奖项", "获奖", "证书")),
]

_BULLET_RE = re.compile(r"^\s*(?:[-•·*●○]|\d+[.、)])\s*")
_DATE_RE = re.compile(r"(20\d{2})[.\-/年]?\s*(?:0?[1-9]|1[0-2])?")


def _is_header(line: str) -> str | None:
    """判断一行是不是小节标题。"""
    stripped = line.strip().strip("：:【】[]# ")
    if not stripped or len(stripped) > 12:
        return None
    for section, kws in _SECTION_KEYWORDS:
        if any(stripped == kw or stripped.startswith(kw) for kw in kws):
            return section
    return None


def _sentences(text: str) -> list[str]:
    parts = re.split(r"[。！？!?；;\n]", text)
    return [p.strip() for p in parts if len(p.strip()) >= 8]


def _approx_tokens(chars: int) -> int:
    """粗略 token 估算：中英混排约 1.6 字符 1 token。"""
    return max(1, int(chars / 1.6)) if chars else 0


# ======================================================================
# Mock 服务
# ======================================================================


class MockAIService:
    """确定性 Mock。接口与 AIService 完全一致。"""

    is_mock = True

    def __init__(self) -> None:
        self._prompt_chars = 0
        self._completion_chars = 0
        self._calls = 0

    # ------------------------------------------------------------------
    def _record(self, prompt: str, completion: str) -> None:
        self._prompt_chars += len(prompt)
        self._completion_chars += len(completion)
        self._calls += 1

    def usage_snapshot(self) -> dict:
        prompt = _approx_tokens(self._prompt_chars)
        completion = _approx_tokens(self._completion_chars)
        return {
            "is_mock": True,
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": prompt + completion,
            "calls": self._calls,
            "by_task": {},
        }

    # ------------------------------------------------------------------
    # 简历解析
    # ------------------------------------------------------------------
    async def parse_resume(self, raw_text: str) -> ResumeParse:
        self._record(raw_text, "")
        text = raw_text or ""
        lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]

        buckets: dict[str, list[str]] = {k: [] for k, _ in _SECTION_KEYWORDS}
        current: str | None = None
        for line in lines:
            header = _is_header(line)
            if header:
                current = header
                continue
            if current:
                buckets[current].append(_BULLET_RE.sub("", line))

        # ---- 技能：全文扫描词表 ----
        lowered = text.lower()
        skills: list[str] = []
        for kw in TECH_VOCAB:
            if kw.lower() in lowered and kw not in skills:
                skills.append(kw)

        # ---- 教育 ----
        education: list[EducationItem] = []
        for line in buckets["education"][:3]:
            m = _DATE_RE.search(line)
            education.append(
                EducationItem(
                    school=line[:40],
                    major=next((k for k in ("计算机", "软件", "电子", "通信", "自动化", "数学", "人工智能", "数据") if k in line), ""),
                    degree="本科" if "本科" in line else ("硕士" if "硕士" in line else ""),
                    period=m.group(0) if m else "",
                    gpa=(re.search(r"(?:GPA|绩点)[:：]?\s*([\d.]+)", line).group(1) if re.search(r"(?:GPA|绩点)[:：]?\s*([\d.]+)", line) else ""),
                )
            )
        if not education and any(k in text for k in ("大学", "学院", "本科")):
            first = next((ln for ln in lines if any(k in ln for k in ("大学", "学院", "本科"))), "")
            education.append(EducationItem(school=first[:40], degree="本科"))

        # ---- 项目 ----
        projects: list[ProjectItem] = []
        for line in buckets["projects"][:6]:
            if len(line) < 6:
                continue
            tech = [kw for kw in TECH_VOCAB if kw.lower() in line.lower()]
            projects.append(
                ProjectItem(
                    name=line[:36],
                    role="开发" if "开发" in line else "",
                    description=line[:200],
                    tech=tech,
                    highlights=[s for s in _sentences(line) if re.search(r"\d", s)][:3],
                )
            )

        # ---- 实习 ----
        internships: list[InternshipItem] = []
        for line in buckets["internships"][:5]:
            if len(line) < 6:
                continue
            internships.append(
                InternshipItem(
                    company=line[:30],
                    description=line[:200],
                    achievements=[s for s in _sentences(line) if re.search(r"\d", s)][:3],
                )
            )

        # ---- 亮点：优先带数字的行 ----
        numeric_lines = [ln for ln in lines if re.search(r"\d", ln) and 10 <= len(ln) <= 120]
        highlights = [_BULLET_RE.sub("", ln)[:120] for ln in numeric_lines[:6]]

        return ResumeParse(
            name=lines[0][:20] if lines else "",
            education=education,
            skills=skills,
            projects=projects,
            internships=internships,
            awards=[a[:80] for a in buckets["awards"][:5]],
            highlights=highlights,
        )

    # ------------------------------------------------------------------
    # JD 分析
    # ------------------------------------------------------------------
    async def analyze_jd(self, title: str, company: str | None, raw_text: str) -> JDParse:
        self._record(raw_text, "")
        lowered = (raw_text or "").lower()
        hard = [kw for kw in TECH_VOCAB if kw.lower() in lowered]
        if not hard:
            hard = [kw for kw in TECH_VOCAB[:1]]
        soft = [kw for kw in SOFT_SKILLS if kw in (raw_text or "")] or SOFT_SKILLS[:3]

        domains: list[str] = []
        for kw in ("高并发", "分布式", "微服务", "大数据", "推荐", "风控", "支付", "电商", "音视频", "云原生", "中间件"):
            if kw in (raw_text or ""):
                domains.append(kw)

        # 权重：JD 中出现次数越多权重越高，归一化到 1
        counts = {kw: max(1, lowered.count(kw.lower())) for kw in hard[:8]}
        total = sum(counts.values()) or 1
        weights = {k: round(v / total, 4) for k, v in counts.items()}

        summary = f"{company or '该公司'}的{title}岗位，重点考察 " + "、".join(hard[:3]) + " 等能力。"

        return JDParse(
            hard_skills=hard[:10],
            soft_skills=soft[:5],
            domains=domains[:5],
            weights=weights,
            summary=summary,
        )

    # ------------------------------------------------------------------
    # 匹配分析
    # ------------------------------------------------------------------
    async def match(
        self,
        *,
        resume_parsed: dict,
        jd_model: dict,
        job_title: str,
        company: str | None,
    ) -> MatchOut:
        self._record(str(resume_parsed) + str(jd_model), "")
        resume_skills = {s.lower() for s in (resume_parsed.get("skills") or [])}
        hard = list(jd_model.get("hard_skills") or [])
        matched = [s for s in hard if s.lower() in resume_skills]
        missing = [s for s in hard if s.lower() not in resume_skills]

        # 覆盖面 0-1 → 30-90 分，再按有无相关实习/项目加分
        cover = len(matched) / len(hard) if hard else 0.5
        score = 30 + cover * 55
        projects = resume_parsed.get("projects") or []
        internships = resume_parsed.get("internships") or []
        if internships:
            score += 8
        if projects:
            score += 5
        score = int(max(20, min(92, round(score))))

        strengths: list[str] = []
        if matched:
            strengths.append(f"简历中明确出现了岗位要求的 {'、'.join(matched[:4])}，技术栈对得上。")
        if internships:
            strengths.append("有实习经历，面试官会认为你熟悉真实工程流程，这是应届生里的加分项。")
        if projects:
            strengths.append(f"有 {len(projects)} 段项目经历，具备可被深挖的技术细节。")
        numeric = resume_parsed.get("highlights") or []
        if numeric:
            strengths.append("简历中存在量化描述，说明你有意识地记录结果，便于面试时展开。")
        if not strengths:
            strengths.append("教育背景与该岗位同属计算机相关方向，具备基础可塑性。")

        risks: list[str] = []
        if missing:
            risks.append(f"岗位要求的 {'、'.join(missing[:4])} 在简历中未体现，面试官大概率会直接问。")
        if not internships:
            risks.append("缺少实习经历，面试官会更加依赖项目深挖来判断你的工程能力。")
        if not numeric:
            risks.append("简历几乎全是定性描述，面试官容易怀疑成果真实性。")
        if len(projects) <= 1:
            risks.append("项目数量偏少，深挖空间有限，建议准备更多可展开的细节。")
        risks.append("简历上的技术名词若答不出原理与取舍，会被判定为“只是用过”，务必逐项准备。")

        q_pool = list(missing) + matched
        likely = [f"你简历里提到 {s}，能讲讲它的原理和你实际怎么用的吗？" for s in q_pool[:3]]
        if projects:
            likely.append(f"「{str(projects[0].get('name', '项目'))[:24]}」这个项目里你具体负责哪部分？遇到最大的困难是什么？")
        if internships:
            likely.append("实习期间你独立交付过什么？如果重做一次你会怎么改？")
        while len(likely) < 5:
            likely.append(f"为什么选择应聘{job_title}这个方向？你为它做了哪些准备？")

        return MatchOut(
            match_score=score,
            strengths=strengths[:5],
            risks=risks[:5],
            likely_questions=likely[:5],
            summary=(
                f"综合匹配度 {score} 分。技术栈覆盖了岗位要求的 {len(matched)}/{len(hard) or 1} 项，"
                f"{'有实习经历支撑' if internships else '缺少实习经历'}。"
                f"当前最需要补的是 {'、'.join(missing[:3]) if missing else '项目细节的量化表达'}；"
                "面试前建议把简历里每个技术名词都准备一套「原理 + 我怎么用 + 为什么这么选」的说法。"
            ),
        )

    # ------------------------------------------------------------------
    # 面试计划
    # ------------------------------------------------------------------
    async def make_plan(
        self,
        *,
        resume_parsed: dict,
        jd_model: dict | None,
        job_title: str,
        company: str | None,
        config: dict,
    ) -> InterviewPlan:
        self._record(str(resume_parsed) + str(jd_model), "")
        competencies: list[CompetencyItem] = []
        weights = (jd_model or {}).get("weights") or {}
        hard = list((jd_model or {}).get("hard_skills") or [])

        # JD 硬技能 → jd 类考察点（按权重降序，取前 4）
        hard_sorted = sorted(hard, key=lambda s: -float(weights.get(s, 0.05)))
        for skill in hard_sorted[:4]:
            competencies.append(
                CompetencyItem(
                    name=skill,
                    source="jd",
                    weight=round(float(weights.get(skill, 0.1)), 3),
                    probe_questions=[
                        f"你在实际项目里怎么用 {skill} 的？举一个具体场景。",
                        f"用 {skill} 时你做过哪些权衡？为什么不选另一套方案？",
                        f"如果 {skill} 出问题，你怎么定位？有具体的排查例子吗？",
                    ],
                )
            )

        # 简历项目 → resume 类考察点（至少 2 个）
        projects = resume_parsed.get("projects") or []
        for proj in projects[:3]:
            name = str(proj.get("name") or "").strip()[:40] or "你的项目"
            competencies.append(
                CompetencyItem(
                    name=f"简历项目：{name}",
                    source="resume",
                    weight=0.12,
                    probe_questions=[
                        f"「{name}」这个项目里你独立负责哪一部分？具体写了什么？",
                        "这个项目最难的技术点是什么？你当时怎么解决的？",
                        "如果让你重新做一遍，你会改哪里？为什么？",
                    ],
                )
            )

        if not projects:
            competencies.append(
                CompetencyItem(
                    name="简历项目经历",
                    source="resume",
                    weight=0.15,
                    probe_questions=[
                        "挑一个你投入最多的项目，讲讲你具体做了什么。",
                        "这个项目上线后效果如何？有数据吗？",
                    ],
                )
            )

        # 软素质 → general 类
        for soft in (SOFT_SKILLS[:3]):
            competencies.append(
                CompetencyItem(
                    name=soft,
                    source="general",
                    weight=0.06,
                    probe_questions=[
                        "讲一次你在团队里主动推动事情的经历，当时的分歧是什么？",
                        "那次合作里你做了什么别人没做的事？结果怎样？",
                    ],
                )
            )

        # 权重归一化
        total_w = sum(c.weight for c in competencies) or 1.0
        for c in competencies:
            c.weight = round(c.weight / total_w, 3)

        stages = [
            StagePlan(stage=s, weight=STAGE_META[s]["weight"], goal=STAGE_META[s]["goal"])
            for s in STAGES
        ]

        return InterviewPlan(
            total_rounds=6,
            stages=stages,
            competencies=competencies[:8],
            constraints=[
                "同一考察点最多追问 2 层",
                f"总时长控制在 {config.get('duration_min', 30)} 分钟 ±10%",
                "不问与岗位无关的私人信息",
            ],
            opening_line=f"你好，我是{company or '我们公司'}{INTERVIEW_TYPES.get(config.get('interview_type', 'comprehensive'), '面试')}的面试官，今天由我来和你聊一聊{job_title}这个岗位。",
        )

    # ------------------------------------------------------------------
    # 面试官措辞（流式）
    # ------------------------------------------------------------------
    def _compose_question(self, ctx: QuestionContext) -> str:
        last_answer = ""
        if ctx.turns and getattr(ctx.turns[-1], "answer", None):
            last_answer = _sentences(ctx.turns[-1].answer or "")
            last_answer = last_answer[0][:40] if last_answer else (ctx.turns[-1].answer or "")[:40]

        probe = ctx.probe_questions[0] if ctx.probe_questions else ""
        competency = ctx.competency or ""

        if ctx.intent == INTENT_OPENING:
            return (
                f"你好，我是{ctx.company or '我们公司'}的面试官，今天由我来和你聊一聊{ctx.job_title}这个岗位。"
                "我们大概聊 " + str(ctx.duration_min) + " 分钟。"
                "先请你用 1 分钟做个自我介绍，重点讲和你应聘岗位最相关的那段经历。"
            )

        if ctx.intent == INTENT_FOLLOWUP_DETAIL:
            return (
                f"你刚提到「{last_answer}」，我想再具体一点："
                "这个部分你是怎么实现或怎么测出来的？当时对比的基线是什么？"
            )

        if ctx.intent == INTENT_FOLLOWUP_CONCRETE:
            return (
                "这个描述还是比较概括，我想听具体的。"
                "能不能举一个实际例子：当时遇到的具体问题是什么，你具体做了哪些改动，最后结果如何？"
            )

        if ctx.intent == INTENT_FOLLOWUP_CHALLENGE:
            return (
                f"你刚说「{last_answer}」。我想确认一下，这个结论在什么条件下会不成立？"
                "边界情况你们当时是怎么处理的？"
            )

        if ctx.intent == INTENT_STAGE_TRANSITION:
            label = STAGE_META.get(ctx.stage, {}).get("label", "下一部分")
            head = f"这部分我们先聊到这里，接下来聊{label}。"
            if competency:
                head += f"我想重点了解一下你的{competency}。"
            return head + (probe or "结合你的经历，讲讲你在这方面最有代表性的一次实践。")

        if ctx.intent == INTENT_WRAPUP:
            return "时间差不多了，我这边的问题问完了。最后，你有什么想问我的吗？"

        # INTENT_NEW_COMPETENCY 及默认
        if competency:
            head = f"那我们换个方向，聊聊{competency}。"
            return head + (probe or "你在实际项目里是怎么用的？请举一个具体场景。")

        return probe or "再讲讲你在这方面的其他经历，比如你做过的最有技术含量的一件事。"

    async def stream_question(self, ctx: QuestionContext) -> AsyncIterator[str]:
        text = self._compose_question(ctx)
        self._record(str(ctx.intent) + str(ctx.competency), text)
        # 模拟流式：按 3-5 字一段吐出，保留打字机观感
        step = 4
        for i in range(0, len(text), step):
            yield text[i : i + step]
            await asyncio.sleep(0.012)

    # ------------------------------------------------------------------
    # 单题评分
    # ------------------------------------------------------------------
    async def evaluate(self, ctx: EvaluateContext) -> Evaluation:
        self._record(ctx.question, ctx.answer)
        answer = ctx.answer or ""
        signals = analyze_answer(answer)
        sents = _sentences(answer)

        not_answer = any(k in answer for k in ("不知道", "不清楚", "没做过", "没了解", "忘了"))
        too_short = len(answer) < 30

        # 相关性
        if too_short or not_answer:
            relevance = 1.5 if too_short else 2.0
        elif signals.has_tech:
            relevance = 4.5
        else:
            relevance = 3.5

        # 结构
        structure = {0: 2.0, 1: 2.5, 2: 3.0, 3: 3.5, 4: 4.5}.get(signals.star_score, 3.0)
        if too_short:
            structure = min(structure, 2.0)

        # 深度
        if signals.has_number and signals.has_tech:
            depth = 4.5
        elif signals.has_tech:
            depth = 3.5
        elif signals.has_number:
            depth = 3.0
        else:
            depth = 2.0 if not too_short else 1.5
        if not_answer:
            depth = 1.5

        # 表达
        n = len(answer)
        if n < 30:
            delivery = 1.5
        elif n <= 600:
            delivery = 4.5
        elif n <= 1000:
            delivery = 3.5
        else:
            delivery = 2.5
        if answer.count("然后") + answer.count("就是") > 8:
            delivery = max(1.5, delivery - 1.0)

        # 视频/语音作答：以**实测指标**为准，而不是凭文本长度猜
        dm = ctx.delivery_metrics or {}
        voice_delivery_note: list[str] = []
        if dm.get("transcript_source") in ("asr", "mixed"):
            rate = float(dm.get("speech_rate") or 0)
            filler_ratio = float(dm.get("filler_ratio") or 0)
            long_pauses = int(dm.get("long_pause_count") or 0)

            if rate and rate < 180:
                delivery = min(delivery, 3.5)
                voice_delivery_note.append(f"语速偏慢（{rate:.0f} 字/分钟），听起来像在背稿或边想边说。")
            elif rate > 320:
                delivery = min(delivery, 3.5)
                voice_delivery_note.append(f"语速偏快（{rate:.0f} 字/分钟），面试官会觉得你在赶时间。")
            if filler_ratio > 0.06:
                delivery = min(delivery, 3.0)
                voice_delivery_note.append(
                    f"口头禅占比 {filler_ratio * 100:.1f}%，明显影响听感（建议压到 2% 以下）。"
                )
            if long_pauses > 3:
                delivery = min(delivery, 3.0)
                voice_delivery_note.append(f"出现 {long_pauses} 次超过 2.5 秒的停顿，卡壳比较明显。")
            if not voice_delivery_note:
                voice_delivery_note.append(
                    f"语速 {rate:.0f} 字/分钟、口头禅占比 {filler_ratio * 100:.1f}%，口播节奏是正常的。"
                )

        # 主动跳过：五维全 1，并明确说明后果
        if ctx.skipped:
            return Evaluation(
                relevance=1.0,
                structure=1.0,
                depth=1.0,
                delivery=1.0,
                fit=1.0,
                evidence=["（候选人主动跳过，未作答）"],
                strengths=[],
                problems=[
                    Problem(
                        issue="遇到不会的问题直接放弃",
                        why="真实面试中跳过等于这一项直接归零，面试官会怀疑你的知识边界比简历写的窄。",
                        fix="即使不会，也要说出你已知的部分 + 你的分析方向 + 你会怎么去查证，这样至少能拿到过程分。",
                    )
                ],
                risk_points=["面试官会追问：这个技术你在项目里到底用没用过？"],
                rewritten_answer=(
                    "示范结构：先承认「这块我没有直接做过」，紧接着说明「但我了解它的基本原理是 X」，"
                    "再给出「如果让我上手，我会先从 Y 入手验证」，最后补一个你确实做过的相邻经验作为佐证。"
                ),
                is_weak=True,
            )

        # 匹配度
        jd_terms = (ctx.jd_model or {}).get("hard_skills") or []
        fit_hits = sum(1 for t in jd_terms if t.lower() in answer.lower())
        fit = 4.0 if fit_hits >= 2 else (3.5 if fit_hits == 1 else 3.0)
        if too_short:
            fit = 2.0

        evidence = [s[:80] for s in sents[:3]] or [answer[:80]]
        strengths: list[str] = []
        problems: list[Problem] = []

        if signals.has_number:
            strengths.append("给出了量化数据，比纯定性描述更有说服力。")
        if signals.star_score >= 3:
            strengths.append("回答有背景-做法-结果的结构，面试官容易跟上。")
        if signals.has_tech:
            strengths.append("出现了具体技术名词，说明有实际动手经验。")
        if not strengths:
            strengths.append("回答方向没有跑偏，态度积极，有进一步展开的基础。")

        if signals.is_vague:
            problems.append(
                Problem(
                    issue="回答偏概括，缺少具体事实",
                    why="面试官无法判断这些工作是你做的还是团队做的，也无法评估技术难度。",
                    fix="先给结论，再补一个具体场景：用了什么技术、改了什么、数据从多少变到多少。",
                )
            )
        if not signals.has_number:
            problems.append(
                Problem(
                    issue="全程没有量化结果",
                    why="没有数字的成果在面试官眼里等于没有成果，容易被判定为“参与而非主导”。",
                    fix="准备每个项目的 1-2 个关键数字（QPS、耗时、覆盖率、人数、金额），并说清统计口径。",
                )
            )
        if signals.star_score < 3:
            problems.append(
                Problem(
                    issue="缺少完整的情境与结果",
                    why="听不出你面对的具体问题，也听不出你的个人贡献。",
                    fix="用 STAR 组织：背景一句话 → 你的任务 → 你做的 2-3 个动作 → 可衡量的结果。",
                )
            )
        if not_answer:
            problems.append(
                Problem(
                    issue="直接承认不了解",
                    why="空白回答会直接拉低该考察点分数。",
                    fix="即使不熟，也说出你知道的部分 + 你的推测方向 + 你会怎么去查证。",
                )
            )

        if voice_delivery_note:
            for note in voice_delivery_note:
                if note.startswith(("语速偏", "口头禅", "出现")):
                    problems.append(
                        Problem(
                            issue="语音表达需要改进",
                            why=note,
                            fix="录音回听自己这一段，把长句拆短、把「然后/就是」换成停顿。",
                        )
                    )
                    break

        # 前瞻：面试官下一步会拿什么来质疑
        risk_points: list[str] = []
        if not signals.has_number:
            risk_points.append("你提到成果但没给数字，面试官接下来一定会问「具体提升了多少」。")
        if signals.has_number:
            risk_points.append("你给了数字，面试官接下来会追问统计口径与对比基线。")
        if signals.is_vague:
            risk_points.append("回答里没有你的具体动作，面试官会问「这到底是你做的还是团队做的」。")
        if signals.has_tech and signals.star_score < 3:
            risk_points.append("你提到了技术名词但没有取舍理由，面试官会问「为什么不用另一个方案」。")
        if not risk_points:
            risk_points.append("这个回答比较完整，面试官可能转向更高难度的问题来探你的边界。")

        # 改写示范：基于他真实内容重排结构，不新增事实
        core = "；".join(sents[:3]) if sents else answer[:120]
        rewritten = (
            "【背景与任务】"
            + (sents[0][:60] if sents else "（你提到的场景）")
            + "。\n【我的做法】"
            + (sents[1][:80] if len(sents) > 1 else core[:80])
            + "。\n【结果与反思】"
            + (sents[-1][:80] if len(sents) > 2 else "（补上你实际拿到的结果数字）")
            + "。\n改写要点：把「我参与了」换成「我负责 X，具体做了 A、B、C」，并为每个结论补上一个数字或对比基线。"
        )

        evaluation = Evaluation(
            relevance=relevance,
            structure=structure,
            depth=depth,
            delivery=delivery,
            fit=fit,
            evidence=evidence,
            strengths=strengths[:3],
            problems=problems[:4],
            risk_points=risk_points[:3],
            rewritten_answer=rewritten,
        )
        evaluation.is_weak = evaluation.weighted_score() < 3.0
        return evaluation

    # ------------------------------------------------------------------
    # 参考答案（按需生成）
    # ------------------------------------------------------------------
    async def make_suggested_answer(self, ctx: SuggestedAnswerContext) -> SuggestedAnswer:
        self._record(ctx.question, ctx.answer)
        sents = _sentences(ctx.answer or "")

        # 占位符纪律：Mock 也不许编数字。缺什么就暴露什么。
        has_number = bool(re.search(r"\d", ctx.answer or ""))
        has_metric = any(k in (ctx.answer or "") for k in ("提升了", "下降到", "QPS", "耗时", "%", "％"))

        placeholders: list[str] = []
        if not has_metric:
            placeholders.append("[补充你的具体指标，如 QPS / 耗时 / 覆盖率]")
        if not has_number:
            placeholders.append("[补充对比基线：改之前是多少]")
        if "我负责" not in (ctx.answer or "") and "我做" not in (ctx.answer or ""):
            placeholders.append("[补充你在该项目中的具体职责]")

        outline = [
            "一句话交代背景：这是什么场景、要解决什么问题。",
            "说清你的具体职责：哪一部分是你独立完成的。",
            "讲 2-3 个你实际做的动作，每个动作带上技术选型理由。",
            "给出可衡量的结果，并说明统计口径与对比基线。",
            "补一句反思：如果重做一次你会改哪里。",
        ]

        key_points = [
            f"紧扣面试官关心的方向：{'、'.join(ctx.interviewer_focus) or '岗位核心能力'}",
            "每个结论后面跟一个数字或对比基线",
            "明确区分「我做的」和「团队做的」",
        ]
        if ctx.resume_highlights:
            key_points.append(f"可引用的简历事实：{ctx.resume_highlights[0][:60]}")

        improvements = [
            "把「我参与了」改成「我负责 X，具体做了 A、B、C」。",
            "给每个定性结论补一个数字或对比基线。",
            "回答末尾加一句取舍或反思，这是 4 分和 5 分的差别。",
        ]

        core = "；".join(sents[:3]) if sents else "（你刚才提到的内容）"
        reference = (
            f"关于这个问题，我的经历是这样的：{sents[0][:50] if sents else '（背景）'}。"
            f"其中我负责的部分是 {placeholders[0] if placeholders else '（你独立完成的部分）'}。"
            f"具体做法上，{core[:120]}。"
            f"结果是 {placeholders[1] if len(placeholders) > 1 else '[补充具体结果数字与对比基线]'}。"
            "现在回头看，如果重做一次，我会在方案选择上更早做压测，避免上线后才发现瓶颈。"
        )

        return SuggestedAnswer(
            outline=outline,
            key_points=key_points,
            improvements=improvements,
            reference_answer=reference,
            placeholders=placeholders,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    # ------------------------------------------------------------------
    # 报告
    # ------------------------------------------------------------------
    async def make_report(self, ctx: ReportContext) -> ReportOut:
        self._record(str(ctx.turns), "")
        dims = ctx.dimension_scores
        total = ctx.total_score

        # 找出最弱的两个维度
        weakest = sorted(dims.items(), key=lambda kv: kv[1]) if dims else []
        weak_names = [DIMENSION_LABELS.get(k, k) for k, _ in weakest[:2]]

        # 汇总所有单题问题，按出现频次排序
        issue_counter: dict[str, dict] = {}
        for t in ctx.turns:
            ev = t.get("evaluation") or {}
            for p in ev.get("problems") or []:
                issue = (p.get("issue") or "").strip()
                if not issue:
                    continue
                entry = issue_counter.setdefault(
                    issue, {"count": 0, "why": p.get("why", ""), "fix": p.get("fix", ""), "evidence": []}
                )
                entry["count"] += 1
                if ev.get("evidence"):
                    entry["evidence"].append(ev["evidence"][0])

        ranked = sorted(issue_counter.items(), key=lambda kv: -kv[1]["count"])
        top_problems: list[TopProblem] = []
        for issue, meta in ranked[:3]:
            top_problems.append(
                TopProblem(
                    title=issue[:14],
                    evidence=(meta["evidence"][0] if meta["evidence"] else "（本场未留下可引用原话）"),
                    why_bad=meta["why"] or "会让面试官难以判断你的真实贡献与技术深度。",
                    how_to_fix=meta["fix"] or "用「结论先行 + 具体数字 + 我的动作」重写这段回答。",
                    demo_answer=(
                        f"针对「{issue}」，示范结构：先说清楚你面对的具体问题（1 句），"
                        "再说你个人的 2-3 个动作（含技术选型理由），最后给一个可衡量的结果数字。"
                    ),
                )
            )

        if not top_problems:
            top_problems.append(
                TopProblem(
                    title="从合格到出彩",
                    evidence="（本场未出现明显失误）",
                    why_bad="回答没有硬伤，但也缺少让面试官记住你的“钩子”。",
                    how_to_fix="为每个项目准备一个反直觉的取舍故事：当时为什么放弃更常见的方案。",
                    demo_answer="结构：常规方案是 X，但我们因为某个具体约束放弃了 X 改用 Y，代价是 Z，最终收益是 W。",
                )
            )

        # 7 天计划：按最弱维度分配
        plan = self._build_training_plan(weak_names, top_problems, ctx)

        # 结论文案
        if total >= 80:
            verdict = "strong_pass"
            head = "整体表现明显高于校招平均水平，可以直接进真实面试。"
        elif total >= 65:
            verdict = "pass"
            head = "整体达到了可以通过的门槛，主要问题是细节深度不够稳定。"
        elif total >= 50:
            verdict = "borderline"
            head = "目前处于边缘水平：方向对，但不少回答停在表面，面试官很难下决心给过。"
        else:
            verdict = "fail"
            head = "以目前状态参加真实面试风险很高，主要瓶颈在表达结构与成果量化。"

        strengths_txt = "；".join(weak_names) if weak_names else "无明显短板"
        summary = (
            f"{head}\n\n"
            f"依据：本场加权总分 {total:.0f}/100，五维得分为 "
            + "、".join(f"{DIMENSION_LABELS.get(k, k)} {v:.0f}" for k, v in dims.items())
            + f"。相对薄弱的是{strengths_txt}，具体表现为上述 {len(top_problems)} 个问题。\n\n"
            "这场面试是有价值的：它暴露的问题在真实面试前就能改。"
            "按下面 7 天的计划执行，重点不是刷更多题，而是把已有的经历讲出深度和数据。"
        )

        return ReportOut(
            verdict=verdict,
            summary=summary,
            top_problems=top_problems,
            training_plan=plan,
        )

    @staticmethod
    def _build_training_plan(
        weak_names: list[str], top_problems: list[TopProblem], ctx: ReportContext
    ) -> list[TrainingDay]:
        focus = weak_names[0] if weak_names else "专业深度"
        problem_title = top_problems[0].title if top_problems else "回答缺少细节"
        tasks: list[tuple[str, str, str]] = [
            (
                "把简历上每个技术名词列成表，逐项写出「原理一句话 + 我在哪用过 + 为什么选它」，共 10 项",
                "消除“只是用过”的观感，任何名词都能接住第一层追问",
                "技术基础",
            ),
            (
                f"挑本场暴露的「{problem_title}」问题，用 STAR 重写 3 个回答，每个控制在 90 秒口播长度",
                "把散乱的叙述改成有情境-动作-结果的结构",
                "结构逻辑",
            ),
            (
                "为每个项目补 2 个关键数字（QPS / 耗时 / 覆盖率 / 人数），并写下统计口径与对比基线",
                "让成果可被验证，避免被追问时说不清来源",
                "成果量化",
            ),
            (
                "整理 5 个高频八股题（数据库索引、缓存一致性、并发控制等），每题写 3 句答案并录音回听",
                "提高技术回答的熟练度与表达流畅度",
                "专业深度",
            ),
            (
                f"针对「{focus}」做一次 15 分钟专项模拟面试，只练这一个维度",
                "在最短时间内集中暴露该维度的残余问题",
                focus,
            ),
            (
                "写一份 200 字「为什么选这个岗位」的回答，落到具体产品/技术方向上，不用“平台好、发展快”这类词",
                "把求职动机讲得可信，这是 HR 面最容易失分的地方",
                "岗位匹配",
            ),
            (
                "完整模拟一场 30 分钟面试，结束后对照本场报告复看，确认上轮问题是否复现",
                "验证改进是否真的生效，形成闭环",
                "综合演练",
            ),
        ]
        return [
            TrainingDay(day=i + 1, task=t, goal=g, link_competency=c)
            for i, (t, g, c) in enumerate(tasks)
        ]


# 便于测试直接构造
def build_default_plan(job_title: str = "后端开发工程师") -> InterviewPlan:
    return InterviewPlan(
        total_rounds=6,
        stages=[StagePlan(stage=s, weight=STAGE_META[s]["weight"], goal=STAGE_META[s]["goal"]) for s in STAGES],
        competencies=[
            CompetencyItem(name="MySQL 索引与慢查询优化", source="jd", weight=0.2, probe_questions=["你项目里那条慢查询的 QPS 是多少？"]),
            CompetencyItem(name="缓存一致性", source="jd", weight=0.2, probe_questions=["缓存和数据库不一致时你怎么处理？"]),
            CompetencyItem(name="简历项目：订单系统重构", source="resume", weight=0.2, probe_questions=["你独立负责哪部分？"]),
            CompetencyItem(name="团队协作", source="general", weight=0.2, probe_questions=["讲一次你推动分歧解决的经历。"]),
        ],
        constraints=["同一考察点最多追问 2 层"],
        opening_line=f"你好，我是面试官，今天聊聊{job_title}这个岗位。",
    )


__all__ = ["TECH_VOCAB", "MockAIService", "build_default_plan"]
