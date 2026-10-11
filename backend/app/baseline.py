"""Deterministic business-baseline analysis without provider assumptions."""

from app.schemas import BaselineAnalysis, BusinessBaseline


_CALCULATION_FIELDS = (
    "monthly_ticket_volume",
    "repetitive_ticket_rate",
    "average_handle_minutes",
    "loaded_hourly_cost",
    "expected_ai_resolution_rate",
    "review_minutes_per_ai_ticket",
    "monthly_tool_cost",
)

_COLLECTION_GROUPS = (
    (
        ("monthly_ticket_volume", "repetitive_ticket_rate"),
        "抽样最近 7 天售后工单，记录总量与重复咨询占比。",
    ),
    (
        ("average_handle_minutes", "loaded_hourly_cost"),
        "抽样至少 30 条工单并核对综合人力成本，建立当前处理成本基线。",
    ),
    (
        ("expected_ai_resolution_rate", "review_minutes_per_ai_ticket"),
        "用至少 50 条历史工单做影子测试，记录 AI 独立解决率与人工复核时长。",
    ),
    (
        ("monthly_tool_cost", "max_acceptable_error_rate"),
        "取得工具报价，并确认团队可接受的误答率与升级规则。",
    ),
)


def analyze_business_baseline(baseline: BusinessBaseline) -> BaselineAnalysis:
    """Return reproducible estimates only when every required input is known."""

    values = baseline.model_dump()
    collection_tasks = [
        task
        for fields, task in _COLLECTION_GROUPS
        if any(values[field] is None for field in fields)
    ]
    is_calculable = all(values[field] is not None for field in _CALCULATION_FIELDS)

    estimate: dict[str, float | None] = {
        "automatable_ticket_volume": None,
        "monthly_hours_saved": None,
        "estimated_monthly_net_savings": None,
    }
    if is_calculable:
        automated = (
            baseline.monthly_ticket_volume
            * baseline.repetitive_ticket_rate
            / 100
            * baseline.expected_ai_resolution_rate
            / 100
        )
        saved_hours = (
            automated
            * max(
                baseline.average_handle_minutes
                - baseline.review_minutes_per_ai_ticket,
                0,
            )
            / 60
        )
        net_savings = saved_hours * baseline.loaded_hourly_cost - baseline.monthly_tool_cost
        estimate = {
            "automatable_ticket_volume": round(automated, 2),
            "monthly_hours_saved": round(saved_hours, 2),
            "estimated_monthly_net_savings": round(net_savings, 2),
        }

    return BaselineAnalysis(
        known_field_count=sum(value is not None for value in values.values()),
        is_calculable=is_calculable,
        collection_tasks=collection_tasks,
        **estimate,
    )
