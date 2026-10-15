"""面试引擎单测 —— 本项目最该被测试的部分。

追问逻辑不是"提示词里的建议"，而是可断言的规则：
1. 回答里有具体数字/技术细节 → 必须追一层
2. 回答空泛 → 追具体案例
3. 同一考察点最多追 2 层
4. 剩余时间不足 → 停止追问、强制收尾
"""

from __future__ import annotations

import pytest

from app.constants import (
    BEHAVIORAL,
    CANDIDATE_ASK,
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
    PRESSURE,
    RESUME_DEEP_DIVE,
)
from app.services.interview_engine import (
    AnswerSignals,
    TurnView,
    analyze_answer,
    decide_next,
    planned_turns,
    stage_budgets,
)
from app.services.mock_ai import build_default_plan

PLAN = build_default_plan()
CONFIG = {
    "duration_min": 30,
    "pressure_mode": True,
    "interview_type": "comprehensive",
    "difficulty": "campus",
    "language": "zh",
}


def turn(
    *,
    stage: str = INTRO,
    competency: str | None = None,
    answer: str | None = "我叫张三，本科计算机专业，做过两个后端项目。",
    depth: int = 0,
    is_followup: bool = False,
    question: str = "问题",
) -> TurnView:
    return TurnView(
        question=question,
        answer=answer,
        stage=stage,
        competency=competency,
        is_followup=is_followup,
        followup_depth=depth,
    )


# ======================================================================
# 回答信号
# ======================================================================


class TestAnalyzeAnswer:
    def test_detects_numbers_and_tech(self):
        s = analyze_answer("把下单接口的 P99 从 800ms 降到 120ms，QPS 提升到 3000")
        assert s.has_number is True
        assert s.is_vague is False

    def test_detects_vague_answer(self):
        s = analyze_answer("我参与了后端开发，优化了一些接口")
        assert s.is_vague is True

    def test_empty_answer_is_vague(self):
        s = analyze_answer("")
        assert s.is_vague is True
        assert s.length == 0

    def test_short_answer_is_vague(self):
        assert analyze_answer("做过后端").is_vague is True

    def test_star_score_counts_structure(self):
        structured = (
            "当时订单超时严重，我负责优化查询链路。"
            "我先加了覆盖索引，然后把结果缓存到 Redis。"
            "最终 P99 从 800ms 降到 120ms。"
        )
        assert analyze_answer(structured).star_score >= 3

    def test_strong_claim_requires_number_and_comparison(self):
        assert analyze_answer("性能提升了 3 倍").is_strong_claim is True
        assert analyze_answer("性能提升很明显").is_strong_claim is False


# ======================================================================
# 时间与题量分配
# ======================================================================


class TestBudget:
    @pytest.mark.parametrize("duration,expected", [(15, 8), (30, 15), (45, 23)])
    def test_planned_turns_scales_with_duration(self, duration, expected):
        assert planned_turns(duration) == expected

    def test_stage_budgets_sum_equals_total(self):
        for duration in (15, 30, 45):
            budgets = stage_budgets(duration)
            assert sum(budgets.values()) == planned_turns(duration)
            assert all(v >= 1 for v in budgets.values())


# ======================================================================
# 开场
# ======================================================================


class TestOpening:
    def test_first_turn_is_opening(self):
        d = decide_next(plan=PLAN, config=CONFIG, turns=[], elapsed_min=0)
        assert d.stage == INTRO
        assert d.intent == INTENT_OPENING
        assert d.is_followup is False


# ======================================================================
# 追问规则
# ======================================================================


class TestFollowupRules:
    def test_concrete_answer_triggers_detail_followup(self):
        turns = [
            turn(stage=INTRO, competency=None),
            turn(
                stage=HARD_SKILL,
                competency="MySQL 索引与慢查询优化",
                answer="我给订单表加了联合索引，P99 从 800ms 降到 120ms，QPS 到 3000。",
            ),
        ]
        d = decide_next(plan=PLAN, config=CONFIG, turns=turns, elapsed_min=6)
        assert d.is_followup is True
        assert d.intent == INTENT_FOLLOWUP_DETAIL
        assert d.competency == "MySQL 索引与慢查询优化"
        assert d.followup_depth == 1
        assert d.stage == HARD_SKILL

    def test_vague_answer_triggers_concrete_followup(self):
        turns = [
            turn(stage=INTRO),
            turn(
                stage=HARD_SKILL,
                competency="缓存一致性",
                answer="我参与了缓存这块的开发，做了一些优化工作，性能提升比较明显。",
            ),
        ]
        d = decide_next(plan=PLAN, config=CONFIG, turns=turns, elapsed_min=8)
        assert d.is_followup is True
        assert d.intent == INTENT_FOLLOWUP_CONCRETE

    def test_followup_depth_is_capped_at_two(self):
        """同一考察点已经追了 2 层，就必须换考察点。"""
        base = turn(
            stage=HARD_SKILL,
            competency="MySQL 索引与慢查询优化",
            answer="我给订单表加了联合索引，P99 从 800ms 降到 120ms。",
        )
        turns = [turn(stage=INTRO), base]
        turns.append(
            turn(
                stage=HARD_SKILL,
                competency="MySQL 索引与慢查询优化",
                answer="因为回表次数多，我用了覆盖索引。",
                depth=1,
                is_followup=True,
            )
        )
        turns.append(
            turn(
                stage=HARD_SKILL,
                competency="MySQL 索引与慢查询优化",
                answer="统计口径是线上 7 天的平均值。",
                depth=MAX_FOLLOWUP_DEPTH,
                is_followup=True,
            )
        )
        d = decide_next(plan=PLAN, config=CONFIG, turns=turns, elapsed_min=10)
        assert d.is_followup is False
        assert d.followup_depth == 0

    def test_intro_never_gets_followup(self):
        turns = [turn(stage=INTRO, answer="我参与了后端开发，做了一些优化。")]
        d = decide_next(plan=PLAN, config=CONFIG, turns=turns, elapsed_min=2)
        assert d.is_followup is False
        assert d.stage == RESUME_DEEP_DIVE

    def test_candidate_ask_never_gets_followup(self):
        turns = [
            turn(stage=INTRO),
            turn(stage=HARD_SKILL, competency="缓存", answer="我用了 Redis，命中率 96%。"),
            turn(stage=CANDIDATE_ASK, competency=None, answer="我想了解一下团队的技术栈。"),
        ]
        d = decide_next(plan=PLAN, config=CONFIG, turns=turns, elapsed_min=25)
        assert d.is_followup is False

    def test_pressure_stage_challenges(self):
        turns = [
            turn(stage=INTRO),
            turn(stage=PRESSURE, competency="MySQL 索引与慢查询优化", answer="命中率 99%，提升 3 倍。"),
        ]
        d = decide_next(plan=PLAN, config=CONFIG, turns=turns, elapsed_min=20)
        assert d.is_followup is True
        assert d.intent == INTENT_FOLLOWUP_CHALLENGE

    def test_pressure_disabled_does_not_challenge(self):
        config = {**CONFIG, "pressure_mode": False}
        turns = [
            turn(stage=INTRO),
            turn(stage=PRESSURE, competency="MySQL 索引与慢查询优化", answer="命中率 99%，提升 3 倍。"),
        ]
        d = decide_next(plan=PLAN, config=config, turns=turns, elapsed_min=20)
        assert d.intent != INTENT_FOLLOWUP_CHALLENGE

    def test_no_followup_for_empty_answer(self):
        turns = [
            turn(stage=INTRO),
            turn(stage=HARD_SKILL, competency="缓存", answer=""),
        ]
        d = decide_next(plan=PLAN, config=CONFIG, turns=turns, elapsed_min=10)
        assert d.is_followup is False


# ======================================================================
# 时间兜底
# ======================================================================


class TestTimeGuards:
    def test_time_exhausted_wraps_up(self):
        turns = [turn(stage=INTRO), turn(stage=HARD_SKILL, competency="缓存", answer="用了 Redis。")]
        d = decide_next(plan=PLAN, config=CONFIG, turns=turns, elapsed_min=30)
        assert d.intent == INTENT_WRAPUP
        assert d.stage == CANDIDATE_ASK

    def test_low_remaining_time_stops_followup(self):
        """剩余不足 20%：即使答案里有数字也不再追问。"""
        turns = [
            turn(stage=INTRO),
            turn(
                stage=HARD_SKILL,
                competency="MySQL 索引与慢查询优化",
                answer="P99 从 800ms 降到 120ms，QPS 3000。",
            ),
        ]
        d = decide_next(plan=PLAN, config=CONFIG, turns=turns, elapsed_min=26)
        assert d.is_followup is False

    def test_low_time_skips_remaining_stages(self):
        """剩余时间不足时，即使当前环节没满也直接收尾。"""
        # intro 预算 1 题，填满后应进入 resume_deep_dive；
        # 但此时剩余时间很少，应当直奔收尾
        turns = [turn(stage=INTRO)]
        d = decide_next(plan=PLAN, config=CONFIG, turns=turns, elapsed_min=26.5)
        assert d.stage == CANDIDATE_ASK
        assert d.intent == INTENT_WRAPUP


# ======================================================================
# 环节推进
# ======================================================================


class TestStageProgression:
    def test_intro_advances_to_resume_dive(self):
        turns = [turn(stage=INTRO)]
        d = decide_next(plan=PLAN, config=CONFIG, turns=turns, elapsed_min=2)
        assert d.stage == RESUME_DEEP_DIVE
        assert d.intent == INTENT_STAGE_TRANSITION
        assert d.stage_finished is True

    def test_same_stage_switches_competency(self):
        """硬技能环节题量未满、且答案既不空泛也无细节时，应换下一个考察点。

        "不清楚" 这类回答会触发「要求给具体案例」的追问，这是设计意图，
        所以这里用一段有内容但缺乏可追问信号的回答来验证"换考察点"分支。
        """
        neutral = "我觉得关键在于先把问题定义清楚，然后逐条分析可能的影响范围。"
        turns = [
            turn(stage=INTRO),
            turn(stage=RESUME_DEEP_DIVE, competency="简历项目：订单系统重构", answer=neutral),
            turn(stage=HARD_SKILL, competency="MySQL 索引与慢查询优化", answer=neutral),
        ]
        d = decide_next(plan=PLAN, config=CONFIG, turns=turns, elapsed_min=10)
        assert d.stage == HARD_SKILL
        assert d.is_followup is False
        assert d.intent == INTENT_NEW_COMPETENCY

    def test_competency_pool_matches_stage(self):
        """环节与考察点来源必须对应：简历深挖取 resume，专业技能取 jd。"""
        jd_names = {c.name for c in PLAN.competencies if c.source == "jd"}
        resume_names = {c.name for c in PLAN.competencies if c.source == "resume"}

        # 开场之后进入「简历深挖」，考察点应来自简历
        d1 = decide_next(plan=PLAN, config=CONFIG, turns=[turn(stage=INTRO)], elapsed_min=2)
        assert d1.stage == RESUME_DEEP_DIVE
        assert d1.competency in resume_names

        # 把简历深挖环节填满，进入「专业技能」，考察点应来自 JD
        neutral = "我觉得关键在于先把问题定义清楚，然后逐条分析可能的影响范围。"
        turns = [turn(stage=INTRO)]
        while True:
            d = decide_next(plan=PLAN, config=CONFIG, turns=turns, elapsed_min=8)
            turns.append(
                turn(
                    stage=d.stage,
                    competency=d.competency,
                    answer=neutral,
                    depth=d.followup_depth,
                    is_followup=d.is_followup,
                )
            )
            if d.stage == HARD_SKILL:
                break
        assert d.competency in jd_names

    def test_probe_questions_are_attached(self):
        turns = [turn(stage=INTRO)]
        d = decide_next(plan=PLAN, config=CONFIG, turns=turns, elapsed_min=2)
        if d.competency:
            expected = next(
                (c.probe_questions for c in PLAN.competencies if c.name == d.competency), []
            )
            assert d.probe_questions == expected

    def test_full_interview_reaches_candidate_ask(self):
        """跑一场完整的模拟：从开场一路推进，最终必须进入反问收尾。"""
        turns: list[TurnView] = []
        stages_seen: list[str] = []
        elapsed = 0.0
        for _ in range(60):
            d = decide_next(plan=PLAN, config=CONFIG, turns=turns, elapsed_min=elapsed)
            stages_seen.append(d.stage)
            if d.session_finished:
                break
            turns.append(
                turn(
                    stage=d.stage,
                    competency=d.competency,
                    answer="我负责了这部分，具体做法是先加索引再上缓存，最终延迟下降明显。",
                    depth=d.followup_depth,
                    is_followup=d.is_followup,
                )
            )
            elapsed += 1.5
        assert CANDIDATE_ASK in stages_seen
        assert len(stages_seen) <= 60
        # 环节必须按顺序推进，不能乱跳
        order = [s for s in stages_seen]
        assert order.index(RESUME_DEEP_DIVE) < order.index(HARD_SKILL)
        assert order.index(HARD_SKILL) < order.index(BEHAVIORAL)
        assert order.index(BEHAVIORAL) < order.index(CANDIDATE_ASK)


class TestSignalsDataclass:
    def test_signals_is_constructible(self):
        s = AnswerSignals(
            length=10,
            has_number=False,
            has_tech=False,
            is_vague=True,
            is_strong_claim=False,
            star_score=0,
        )
        assert s.is_vague is True

    def test_new_competency_intent_used_within_stage(self):
        turns = [
            turn(stage=INTRO),
            turn(stage=RESUME_DEEP_DIVE, competency="简历项目：订单系统重构", answer="就那样吧"),
        ]
        d = decide_next(plan=PLAN, config=CONFIG, turns=turns, elapsed_min=8)
        assert d.intent in (INTENT_NEW_COMPETENCY, INTENT_FOLLOWUP_CONCRETE)
