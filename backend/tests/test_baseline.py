import pytest
from pydantic import ValidationError

from app.baseline import analyze_business_baseline
from app.schemas import BusinessBaseline, DecisionCreate


def test_business_baseline_defaults_every_field_to_unknown():
    baseline = BusinessBaseline()

    assert baseline.model_dump() == {
        "monthly_ticket_volume": None,
        "repetitive_ticket_rate": None,
        "average_handle_minutes": None,
        "loaded_hourly_cost": None,
        "expected_ai_resolution_rate": None,
        "review_minutes_per_ai_ticket": None,
        "monthly_tool_cost": None,
        "max_acceptable_error_rate": None,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("monthly_ticket_volume", -1),
        ("monthly_ticket_volume", 10_000_001),
        ("repetitive_ticket_rate", 100.01),
        ("average_handle_minutes", 1_440.01),
        ("loaded_hourly_cost", 1_000_000.01),
        ("expected_ai_resolution_rate", -0.01),
        ("review_minutes_per_ai_ticket", 1_440.01),
        ("monthly_tool_cost", 10_000_000.01),
        ("max_acceptable_error_rate", 100.01),
    ],
)
def test_business_baseline_rejects_values_outside_supported_ranges(field, value):
    with pytest.raises(ValidationError):
        BusinessBaseline.model_validate({field: value})


def test_decision_create_treats_missing_baseline_as_all_unknown():
    decision = DecisionCreate.model_validate(
        {
            "question": "Should we pilot AI support before a full rollout?",
            "time_window": "14 days",
            "budget_limit": 8_000,
            "primary_goal": "Reduce repetitive support workload safely",
        }
    )

    assert decision.business_baseline == BusinessBaseline()


def test_complete_baseline_produces_reproducible_two_decimal_estimate():
    baseline = BusinessBaseline(
        monthly_ticket_volume=1_234,
        repetitive_ticket_rate=62.5,
        average_handle_minutes=8.5,
        loaded_hourly_cost=42.75,
        expected_ai_resolution_rate=71.2,
        review_minutes_per_ai_ticket=1.2,
        monthly_tool_cost=1_250,
        max_acceptable_error_rate=2.0,
    )

    analysis = analyze_business_baseline(baseline)

    assert analysis.known_field_count == 8
    assert analysis.total_field_count == 8
    assert analysis.is_calculable is True
    assert analysis.automatable_ticket_volume == 549.13
    assert analysis.monthly_hours_saved == 66.81
    assert analysis.estimated_monthly_net_savings == 1_606.16
    assert analysis.collection_tasks == []
    assert analysis.disclaimer == "用户输入试算，不是已验证收益"


def test_review_time_never_creates_negative_saved_hours():
    baseline = BusinessBaseline(
        monthly_ticket_volume=100,
        repetitive_ticket_rate=100,
        average_handle_minutes=2,
        loaded_hourly_cost=50,
        expected_ai_resolution_rate=100,
        review_minutes_per_ai_ticket=3,
        monthly_tool_cost=200,
    )

    analysis = analyze_business_baseline(baseline)

    assert analysis.monthly_hours_saved == 0
    assert analysis.estimated_monthly_net_savings == -200


def test_partial_baseline_keeps_estimate_unknown_and_deduplicates_collection_tasks():
    baseline = BusinessBaseline(
        monthly_ticket_volume=500,
        average_handle_minutes=6,
    )

    analysis = analyze_business_baseline(baseline)

    assert analysis.known_field_count == 2
    assert analysis.is_calculable is False
    assert analysis.automatable_ticket_volume is None
    assert analysis.monthly_hours_saved is None
    assert analysis.estimated_monthly_net_savings is None
    assert analysis.collection_tasks == [
        "抽样最近 7 天售后工单，记录总量与重复咨询占比。",
        "抽样至少 30 条工单并核对综合人力成本，建立当前处理成本基线。",
        "用至少 50 条历史工单做影子测试，记录 AI 独立解决率与人工复核时长。",
        "取得工具报价，并确认团队可接受的误答率与升级规则。",
    ]
