"""LLM 输出 schema 的健壮性测试。

模型返回脏数据是常态（"4分"、85/100、嵌套对象、漏字段），
这些都必须被规范化而不是让整场面试崩掉。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.constants import DIMENSION_WEIGHTS
from app.schemas.llm import (
    CompetencyItem,
    Evaluation,
    InterviewPlan,
    JDParse,
    MatchOut,
    ReportOut,
    ResumeParse,
    StagePlan,
)
from app.services.llm_client import extract_json


class TestScoreNormalization:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            (4, 4.0),
            (4.5, 4.5),
            ("4分", 4.0),
            ("4.5/5", 4.5),
            (0.8, 1.0),  # 1-5 刻度下的极低分，夹到下限（而非当成 80%）
            (8, 4.0),  # 十分制 → 二分制
            (85, 4.25),  # 百分制 → 除以 20
            ("abc", 3.0),  # 无法解析 → 中性分
            (-5, 1.0),  # 越界 → 夹到 1
            (999, 5.0),
        ],
    )
    def test_scores_are_normalized_to_1_5(self, raw, expected):
        ev = Evaluation(relevance=raw, structure=3, depth=3, delivery=3, fit=3)
        assert ev.relevance == pytest.approx(expected)

    def test_nested_score_objects_are_accepted(self):
        ev = Evaluation.model_validate(
            {
                "relevance": {"score": 4},
                "structure": {"score": 3.5},
                "depth": {"score": 5},
                "delivery": {"score": 2},
                "fit": {"score": 4},
            }
        )
        assert ev.relevance == 4.0
        assert ev.depth == 5.0

    def test_missing_dimensions_default_to_neutral(self):
        ev = Evaluation.model_validate({"relevance": 4})
        assert ev.structure == 3.0
        assert ev.depth == 3.0

    def test_weighted_score_uses_declared_weights(self):
        ev = Evaluation(relevance=5, structure=5, depth=5, delivery=5, fit=5)
        assert ev.weighted_score() == pytest.approx(5.0)
        ev2 = Evaluation(relevance=1, structure=1, depth=1, delivery=1, fit=1)
        assert ev2.weighted_score() == pytest.approx(1.0)

    def test_weights_sum_to_one(self):
        assert sum(DIMENSION_WEIGHTS.values()) == pytest.approx(1.0)

    def test_to_100_mapping(self):
        assert Evaluation(relevance=1, structure=1, depth=1, delivery=1, fit=1).to_100() == 0.0
        assert Evaluation(relevance=5, structure=5, depth=5, delivery=5, fit=5).to_100() == 100.0

    def test_is_weak_derived_when_absent(self):
        weak = Evaluation(relevance=2, structure=2, depth=2, delivery=2, fit=2)
        assert weak.is_weak is True
        strong = Evaluation(relevance=4, structure=4, depth=4, delivery=4, fit=4)
        assert strong.is_weak is False


class TestPlanSchema:
    def test_missing_stages_are_filled_in(self):
        plan = InterviewPlan.model_validate(
            {
                "total_rounds": 6,
                "stages": [{"stage": "intro", "weight": 0.1}],
                "competencies": [{"name": "MySQL 索引"}],
            }
        )
        from app.constants import STAGES

        assert [s.stage for s in plan.stages] == STAGES

    def test_unknown_stage_is_rejected(self):
        with pytest.raises(ValidationError):
            StagePlan(stage="random_stage", weight=0.1)

    def test_empty_competency_name_is_rejected(self):
        with pytest.raises(ValidationError):
            CompetencyItem(name="   ")

    def test_competency_names_helper(self):
        plan = InterviewPlan.model_validate(
            {"competencies": [{"name": "A"}, {"name": "B"}]}
        )
        assert plan.competency_names() == ["A", "B"]


class TestJDWeights:
    def test_weights_normalized_to_one(self):
        jd = JDParse(hard_skills=["A", "B"], weights={"A": 3, "B": 1})
        assert sum(jd.weights.values()) == pytest.approx(1.0)
        assert jd.weights["A"] == pytest.approx(0.75)

    def test_bad_weights_are_dropped(self):
        jd = JDParse(hard_skills=["A"], weights={"A": "abc", "B": -1})
        assert jd.weights == {}

    def test_weights_from_non_dict_is_ignored(self):
        jd = JDParse(weights=["A", "B"])  # type: ignore[arg-type]
        assert jd.weights == {}


class TestMatchSchema:
    def test_score_is_clamped_and_questions_limited(self):
        m = MatchOut(match_score=180, likely_questions=[f"q{i}" for i in range(9)])
        assert m.match_score == 100
        assert len(m.likely_questions) == 5

    def test_negative_score_clamped(self):
        assert MatchOut(match_score=-20).match_score == 0


class TestReportSchema:
    def test_top_problems_limited_to_three(self):
        r = ReportOut(
            summary="x",
            top_problems=[{"title": f"t{i}"} for i in range(6)],
        )
        assert len(r.top_problems) == 3

    def test_invalid_verdict_rejected(self):
        with pytest.raises(ValidationError):
            ReportOut(verdict="maybe", summary="x")


class TestResumeParse:
    def test_all_fields_optional(self):
        r = ResumeParse()
        assert r.skills == []
        assert r.projects == []


class TestExtractJson:
    def test_plain_json(self):
        assert extract_json('{"a": 1}') == {"a": 1}

    def test_fenced_json(self):
        assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_json_with_prose_around_it(self):
        assert extract_json('好的，结果如下：\n{"a": 1}\n希望有帮助。') == {"a": 1}

    def test_trailing_comma_repaired(self):
        assert extract_json('{"a": 1, "b": [1,2,],}') == {"a": 1, "b": [1, 2]}

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            extract_json("")

    def test_no_json_raises(self):
        with pytest.raises(ValueError):
            extract_json("这里没有任何结构化数据")
