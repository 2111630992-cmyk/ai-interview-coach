"""面试引擎：确定性决策层（本项目最核心、最值得单测的部分）。

## 为什么把「决策」从 LLM 里拿出来

如果让模型一边生成问题一边决定要不要追问，会同时出现三个问题：
1. 追问无上限 —— 模型会连续追五六层，把 30 分钟面试耗在第一个项目上；
2. 环节失控 —— 模型不会主动推进到行为面、压力面；
3. 不可测试 —— 你无法为"追问逻辑"写断言。

所以这里把决策做成**纯函数**：输入（计划、配置、已有轮次、已用时间）→ 输出
「这一轮该干什么」。LLM 只负责把这件事说成一句自然的面试官话术。

`decide_next` 是无副作用的纯函数，pytest 直接喂数据断言即可。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.constants import (
    BEHAVIORAL,
    CANDIDATE_ASK,
    FOLLOWUP_TIME_GUARD,
    HARD_SKILL,
    INTENT_FOLLOWUP_CHALLENGE,
    INTENT_FOLLOWUP_CONCRETE,
    INTENT_FOLLOWUP_DETAIL,
    INTENT_NEW_COMPETENCY,
    INTENT_OPENING,
    INTENT_STAGE_TRANSITION,
    INTENT_WRAPUP,
    INTRO,
    MAX_FOLLOWUP_DEPTH,
    NUMBER_RE,
    PRESSURE,
    RESUME_DEEP_DIVE,
    STAGE_META,
    STAGES,
    TECH_TOKEN_RE,
    VAGUE_MARKERS,
    WRAPUP_TIME_GUARD,
)
from app.schemas.llm import CompetencyItem, InterviewPlan

# ======================================================================
# 输入视图
# ======================================================================


@dataclass
class TurnView:
    """决策所需的最小轮次信息。

    故意不依赖 ORM 模型，方便单测直接构造。
    """

    question: str = ""
    answer: str | None = None
    stage: str = INTRO
    competency: str | None = None
    is_followup: bool = False
    followup_depth: int = 0


@dataclass
class TurnDecision:
    """本轮该做什么。"""

    stage: str
    competency: str | None
    is_followup: bool
    followup_depth: int
    intent: str
    stage_finished: bool = False
    session_finished: bool = False
    probe_questions: list[str] = field(default_factory=list)
    reason: str = ""  # 决策依据，写日志与测试断言用

    @property
    def intent_is_followup(self) -> bool:
        return self.intent in (
            INTENT_FOLLOWUP_DETAIL,
            INTENT_FOLLOWUP_CONCRETE,
            INTENT_FOLLOWUP_CHALLENGE,
        )


# ======================================================================
# 回答信号分析
# ======================================================================


@dataclass
class AnswerSignals:
    length: int
    has_number: bool
    has_tech: bool
    is_vague: bool
    is_strong_claim: bool
    star_score: int


# STAR 关键词：用于粗略判断结构完整度（喂给评分提示词当参考，不直接当分数）
_STAR_SITUATION = ("当时", "背景", "项目里", "我们组", "需求是", "起因")
_STAR_TASK = ("我负责", "我的任务", "目标", "我要做", "我承担")
_STAR_ACTION = ("我先", "然后我", "具体做法", "实现了", "通过", "我的方案", "我设计")
_STAR_RESULT = ("最终", "结果", "提升了", "下降了", "减少了", "从", "增长", "节省", "上线后")


def analyze_answer(answer: str | None) -> AnswerSignals:
    """从回答里提取可判定信号。纯字符串规则，无模型调用。"""
    text = (answer or "").strip()
    if not text:
        return AnswerSignals(
            length=0,
            has_number=False,
            has_tech=False,
            is_vague=True,
            is_strong_claim=False,
            star_score=0,
        )

    has_number = bool(NUMBER_RE.search(text))
    # 英文技术词要求长度 >= 3，避免把 "a" "I" "is" 当成技术名词
    tech_hits = [m.group() for m in TECH_TOKEN_RE.finditer(text) if len(m.group()) >= 3]
    has_tech = bool(tech_hits)

    vague_hits = [m for m in VAGUE_MARKERS if m in text]
    # 空泛判定：出现套话，且既没有数字也没有可追问的技术细节，或整体过短。
    # 括号是必需的 —— and / or 混用时不加括号极易看错优先级。
    is_vague = (bool(vague_hits) and not (has_number and has_tech)) or len(text) < 30

    strong_claim = has_number and any(
        kw in text for kw in ("提升", "优化", "降低", "减少", "增长", "翻倍", "倍", "%", "％")
    )

    star = 0
    for kws in (_STAR_SITUATION, _STAR_TASK, _STAR_ACTION, _STAR_RESULT):
        if any(k in text for k in kws):
            star += 1

    return AnswerSignals(
        length=len(text),
        has_number=has_number,
        has_tech=has_tech,
        is_vague=is_vague,
        is_strong_claim=strong_claim,
        star_score=star,
    )


# ======================================================================
# 环节与考察点调度
# ======================================================================


def _round_half_up(value: float) -> int:
    """四舍五入（Python 内置 round 是银行家舍入，round(4.5)=4，用在题量分配上很反直觉）。"""
    return int(value + 0.5) if value >= 0 else -int(-value + 0.5)


def planned_turns(duration_min: int) -> int:
    """按总时长估算整场问题的数量。

    经验值：校招面试平均每题 2 分钟左右。15 分钟 → 8 题，45 分钟 → 23 题。
    """
    return max(8, min(30, _round_half_up(duration_min / 2)))


def stage_budgets(duration_min: int) -> dict[str, int]:
    """按环节权重把总题数分配下去，保证每个环节至少 1 题、且加总等于总题数。"""
    total = planned_turns(duration_min)
    budgets: dict[str, int] = {}
    allocated = 0
    for stage in STAGES:
        n = max(1, _round_half_up(STAGE_META[stage]["weight"] * total))
        budgets[stage] = n
        allocated += n

    # 把舍入误差收敛掉：多退少补在权重最大的环节上
    diff = total - allocated
    if diff:
        fixed = max(budgets, key=lambda s: budgets[s])
        budgets[fixed] = max(1, budgets[fixed] + diff)
    return budgets


def _turns_per_stage(turns: list[TurnView]) -> dict[str, int]:
    counts: dict[str, int] = {s: 0 for s in STAGES}
    for t in turns:
        counts[t.stage] = counts.get(t.stage, 0) + 1
    return counts


def _stage_for_competency_source(stage: str) -> str | None:
    """环节 ↔ 考察点来源的对应关系。"""
    if stage == RESUME_DEEP_DIVE:
        return "resume"
    if stage == HARD_SKILL:
        return "jd"
    if stage == BEHAVIORAL:
        return "general"
    return None


def stage_pool(stage: str, plan: InterviewPlan) -> list[CompetencyItem]:
    """某个环节可以使用的考察点池。

    **考察点池按环节隔离**：简历深挖只问简历相关的能力点，专业技能只问 JD 要求的。
    早期版本在池子用尽时会回退到「全局未考过的考察点」，结果简历环节把 JD 的
    考察点提前消耗掉，进入专业技能环节时反而无题可问。这里改为池内复用，不跨池借用。
    """
    if stage in (INTRO, CANDIDATE_ASK):
        return []
    preferred = _stage_for_competency_source(stage)
    pool = [c for c in plan.competencies if c.source == preferred] if preferred else []
    if not pool:
        # 该来源一个考察点都没有（例如简历为空），退化为全量池，避免环节空转
        pool = list(plan.competencies)
    return pool


def _asked_main(turns: list[TurnView]) -> set[str]:
    return {t.competency for t in turns if t.competency and not t.is_followup}


def pick_competency(
    *, stage: str, plan: InterviewPlan, turns: list[TurnView]
) -> CompetencyItem | None:
    """为本环节挑一个考察点。

    - 优先挑本环节池里**还没被主问题问过**的
    - 都用过了就复用池内被问得最少的那个（换个角度继续挖，这是真实面试的常态）
    - 压力环节刻意回收已问过的考察点，用来质疑其数据与结论
    """
    asked = _asked_main(turns)

    if stage in (INTRO, CANDIDATE_ASK):
        return None

    if stage == PRESSURE:
        candidates = [c for c in plan.competencies if c.name in asked] or list(
            plan.competencies
        )
        if not candidates:
            return None
        return min(candidates, key=lambda c: sum(1 for t in turns if t.competency == c.name))

    pool = stage_pool(stage, plan)
    if not pool:
        return None

    for c in pool:
        if c.name not in asked:
            return c

    # 池内全都问过：复用问得最少的，不跨池借用
    return min(
        pool,
        key=lambda c: (sum(1 for t in turns if t.competency == c.name), c.name),
    )


def _pool_exhausted(stage: str, plan: InterviewPlan, turns: list[TurnView]) -> bool:
    pool = stage_pool(stage, plan)
    if not pool:
        return True
    asked = _asked_main(turns)
    return all(c.name in asked for c in pool)


def _advance_stage(current: str) -> str | None:
    try:
        idx = STAGES.index(current)
    except ValueError:
        return STAGES[0]
    return STAGES[idx + 1] if idx + 1 < len(STAGES) else None


# ======================================================================
# 主决策函数
# ======================================================================


def decide_next(
    *,
    plan: InterviewPlan,
    config: dict,
    turns: list[TurnView],
    elapsed_min: float,
) -> TurnDecision:
    """决定下一轮面试官该做什么。

     完全确定性：同样的输入必然得到同样的输出（可单测、可重放）。

    决策优先级：
      1. 时间兜底   —— 剩 5% 直接收尾；剩 20% 停止追问
      2. 追问       —— 有可追问的信号且未超过层数上限
      3. 推进环节   —— 本环节题数已满
      4. 换考察点   —— 同环节内换下一个能力点
    """
    duration_min = max(1, int(config.get("duration_min", 30)))
    pressure_mode = bool(config.get("pressure_mode", True))
    remaining_ratio = 1.0 - (elapsed_min / duration_min)
    budgets = stage_budgets(duration_min)
    per_stage = _turns_per_stage(turns)

    # ---------- 0. 开场 ----------
    if not turns:
        return TurnDecision(
            stage=INTRO,
            competency=None,
            is_followup=False,
            followup_depth=0,
            intent=INTENT_OPENING,
            probe_questions=[],
            reason="首轮：开场",
        )

    last = turns[-1]
    signals = analyze_answer(last.answer)

    # ---------- 1. 时间兜底 ----------
    if remaining_ratio <= WRAPUP_TIME_GUARD:
        if last.stage != CANDIDATE_ASK:
            return TurnDecision(
                stage=CANDIDATE_ASK,
                competency=None,
                is_followup=False,
                followup_depth=0,
                intent=INTENT_WRAPUP,
                stage_finished=True,
                probe_questions=[],
                reason=f"剩余时间 {remaining_ratio:.0%} ≤ {WRAPUP_TIME_GUARD:.0%}，直接收尾",
            )
        return TurnDecision(
            stage=CANDIDATE_ASK,
            competency=None,
            is_followup=False,
            followup_depth=0,
            intent=INTENT_WRAPUP,
            session_finished=True,
            reason="时间耗尽且已进入反问环节，结束面试",
        )

    time_for_followup = remaining_ratio > FOLLOWUP_TIME_GUARD

    # ---------- 2. 是否追问 ----------
    can_followup = (
        time_for_followup
        and last.stage not in (INTRO, CANDIDATE_ASK)
        and bool(last.competency)
        and last.followup_depth < MAX_FOLLOWUP_DEPTH
        and bool((last.answer or "").strip())
    )

    if can_followup:
        intent = _followup_intent(
            signals=signals, stage=last.stage, pressure_mode=pressure_mode
        )
        if intent:
            probe = _probes_for(plan, last.competency)
            return TurnDecision(
                stage=last.stage,
                competency=last.competency,
                is_followup=True,
                followup_depth=last.followup_depth + 1,
                intent=intent,
                probe_questions=probe,
                reason=(
                    f"追问第 {last.followup_depth + 1} 层："
                    f"数字={signals.has_number} 技术词={signals.has_tech} 空泛={signals.is_vague}"
                ),
            )

    # ---------- 3/4. 环节推进 or 换考察点 ----------
    budget = budgets.get(last.stage, 1)
    turns_in_stage = per_stage.get(last.stage, 0)
    # 环节的考察点池已经问完，而且已经问过至少一半题量 → 提前结束该环节。
    # 否则会出现"同一个考察点连问 5 遍"的尴尬情况。
    min_before_early_exit = max(1, (budget + 1) // 2)
    stage_done = turns_in_stage >= budget or (
        _pool_exhausted(last.stage, plan, turns)
        and turns_in_stage >= min_before_early_exit
    )

    if stage_done:
        next_stage = _advance_stage(last.stage)
        if next_stage is None:
            # 已到最后一个环节
            if last.stage != CANDIDATE_ASK:
                return TurnDecision(
                    stage=CANDIDATE_ASK,
                    competency=None,
                    is_followup=False,
                    followup_depth=0,
                    intent=INTENT_WRAPUP,
                    stage_finished=True,
                    reason="所有环节已完成，进入反问收尾",
                )
            return TurnDecision(
                stage=CANDIDATE_ASK,
                competency=None,
                is_followup=False,
                followup_depth=0,
                intent=INTENT_WRAPUP,
                session_finished=True,
                reason="面试全部完成",
            )

        # 时间不够就跳过硬技能/压力环节，直奔收尾
        if remaining_ratio <= FOLLOWUP_TIME_GUARD and next_stage != CANDIDATE_ASK:
            return TurnDecision(
                stage=CANDIDATE_ASK,
                competency=None,
                is_followup=False,
                followup_depth=0,
                intent=INTENT_WRAPUP,
                stage_finished=True,
                reason=f"剩余时间不足（{remaining_ratio:.0%}），跳过 {STAGE_META[next_stage]['label']} 直接收尾",
            )

        competency = pick_competency(stage=next_stage, plan=plan, turns=turns)
        return TurnDecision(
            stage=next_stage,
            competency=competency.name if competency else None,
            is_followup=False,
            followup_depth=0,
            intent=(
                INTENT_WRAPUP
                if next_stage == CANDIDATE_ASK
                else INTENT_STAGE_TRANSITION
            ),
            stage_finished=True,
            probe_questions=list(competency.probe_questions) if competency else [],
            reason=(
                f"{STAGE_META[last.stage]['label']} 结束（{turns_in_stage}/{budget} 题，"
                f"考察点池{'已用完' if _pool_exhausted(last.stage, plan, turns) else '未用完'}），"
                f"进入 {STAGE_META[next_stage]['label']}"
            ),
        )

    # 同环节内换考察点
    competency = pick_competency(stage=last.stage, plan=plan, turns=turns)
    return TurnDecision(
        stage=last.stage,
        competency=competency.name if competency else last.competency,
        is_followup=False,
        followup_depth=0,
        intent=INTENT_NEW_COMPETENCY,
        probe_questions=list(competency.probe_questions) if competency else [],
        reason="未触发追问条件，同环节内切换考察点",
    )


def _followup_intent(*, signals: AnswerSignals, stage: str, pressure_mode: bool) -> str | None:
    """三条追问规则。

    1. 有具体数字/技术细节 → 追来源与做法
    2. 空泛套话         → 追具体案例
    3. 压力环节或强主张  → 温和质疑边界条件

    都不满足则返回 None，表示「这题问得差不多了，换考察点」。
    """
    if stage == PRESSURE and pressure_mode:
        return INTENT_FOLLOWUP_CHALLENGE
    if signals.is_vague:
        return INTENT_FOLLOWUP_CONCRETE
    if signals.has_number or signals.has_tech:
        if pressure_mode and signals.is_strong_claim and stage in (HARD_SKILL, RESUME_DEEP_DIVE):
            return INTENT_FOLLOWUP_CHALLENGE
        return INTENT_FOLLOWUP_DETAIL
    return None


def _probes_for(plan: InterviewPlan, competency: str | None) -> list[str]:
    if not competency:
        return []
    for c in plan.competencies:
        if c.name == competency:
            return list(c.probe_questions)
    return []
