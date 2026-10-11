"""Canonical Markdown rendering for a persisted decision snapshot."""

from typing import Any

from app.schemas import DecisionSnapshot


_BASELINE_LABELS = (
    ("monthly_ticket_volume", "月售后工单量", "integer"),
    ("repetitive_ticket_rate", "重复咨询占比", "percent"),
    ("average_handle_minutes", "平均处理时长", "minutes"),
    ("loaded_hourly_cost", "综合人力时薪", "money"),
    ("expected_ai_resolution_rate", "预计 AI 独立解决率", "percent"),
    ("review_minutes_per_ai_ticket", "AI 工单人工复核时长", "minutes"),
    ("monthly_tool_cost", "预计月工具成本", "money"),
    ("max_acceptable_error_rate", "可接受最大误答率", "percent"),
)

_RECOMMENDATIONS = {
    "pilot_before_rollout": "先受限试点，再决定是否扩量",
    "do_not_pilot": "不建议试点",
    "defer": "暂缓决策",
}

_REVIEW_STATUS = {
    "awaiting_review": "待人工审批",
    "accepted": "已接受",
    "revised": "需修改",
    "deferred": "已暂缓",
}

_WORKFLOW_STATUS = {
    "draft": "待开始",
    "clarifying": "正在澄清",
    "awaiting_confirmation": "待确认条件",
    "planning": "研究规划中",
    "researching": "正在取证",
    "analyzing": "多方分析中",
    "challenging": "反方质询中",
    "delivering": "正在交付",
    "awaiting_review": "待人工审批",
    "accepted": "已采纳",
    "revised": "已记录修改意见",
    "deferred": "已暂缓",
    "failed": "执行中断",
    "retrying": "正在重试",
}


def _inline(value: Any) -> str:
    text = " ".join(str(value).split())
    return text.replace("[", r"\[").replace("]", r"\]")


def _number(value: float) -> str:
    return f"{value:g}"


def _baseline_value(value: float | int | None, kind: str) -> str:
    if value is None:
        return "未知"
    if kind == "integer":
        return f"{int(value):,}"
    if kind == "percent":
        return f"{_number(float(value))}%"
    if kind == "minutes":
        return f"{_number(float(value))} 分钟"
    return f"¥{float(value):,.2f}"


def _append_statements(lines: list[str], heading: str, values: list[dict]) -> None:
    if not values:
        return
    lines.extend([f"### {heading}", ""])
    for item in values:
        evidence_ids = item.get("evidence_ids", [])
        suffix = f"（证据：{', '.join(map(str, evidence_ids))}）" if evidence_ids else ""
        lines.append(f"- {_inline(item.get('text', ''))}{suffix}")
    lines.append("")


def render_decision_markdown(snapshot: DecisionSnapshot) -> str:
    """Render a complete, portable report without changing workflow state."""

    if snapshot.memo is None:
        raise ValueError("Decision report is not ready")

    mode_label = "Demo 模式（仅含合成演示材料）" if snapshot.mode == "demo" else "Live 模式（来源摘要仍需人工核验）"
    memo = snapshot.memo
    baseline = snapshot.business_baseline.model_dump()
    analysis = snapshot.baseline_analysis
    lines = [
        "# VeriPlan 决策 Memo",
        "",
        f"> {_inline(mode_label)}。本报告是决策支持记录，不会自动执行业务动作。",
        "",
        "## 决策概览",
        "",
        f"- 决策问题：{_inline(snapshot.question)}",
        f"- 时间窗口：{_inline(snapshot.time_window)}",
        f"- 预算上限：¥{snapshot.budget_limit:,}",
        f"- 首要目标：{_inline(snapshot.primary_goal)}",
        f"- 工作流状态：{_WORKFLOW_STATUS[snapshot.status.value]}",
        "",
        "## 业务基线",
        "",
    ]
    lines.extend(
        f"- {label}：{_baseline_value(baseline[field], kind)}"
        for field, label, kind in _BASELINE_LABELS
    )
    lines.append("")
    if analysis.is_calculable:
        lines.extend(
            [
                "### 确定性试算",
                "",
                f"- 预计自动解决工单量：{analysis.automatable_ticket_volume:,.2f}",
                f"- 预计月节省工时：{analysis.monthly_hours_saved:,.2f} 小时",
                f"- 预计月净节省：¥{analysis.estimated_monthly_net_savings:,.2f}",
                f"- 免责声明：**{_inline(analysis.disclaimer)}**",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "- 收益试算：输入不完整，未计算",
                f"- 免责声明：**{_inline(analysis.disclaimer)}**",
                "",
            ]
        )
    if analysis.collection_tasks:
        lines.extend(["### 内部数据采集任务", ""])
        lines.extend(f"- {_inline(task)}" for task in analysis.collection_tasks)
        lines.append("")

    recommendation = _RECOMMENDATIONS.get(
        memo.get("recommendation", ""), memo.get("recommendation", "未提供")
    )
    lines.extend(
        [
            "## 最终建议",
            "",
            f"- 建议：{_inline(recommendation)}",
            f"- 决策支持度：{memo.get('support_score', '未提供')}/100",
            f"- 摘要：{_inline(memo.get('summary', '未提供'))}",
            f"- 评分说明：{_inline(memo.get('score_explanation', '未提供'))}",
            "",
        ]
    )
    _append_statements(lines, "来源事实", memo.get("facts", []))
    _append_statements(lines, "推断", memo.get("inferences", []))

    objections = memo.get("objections", [])
    if objections:
        lines.extend(["### 反方意见", ""])
        lines.extend(f"- {_inline(item)}" for item in objections)
        lines.append("")

    lines.extend(["## 行动计划", ""])
    for index, action in enumerate(memo.get("action_plan", []), start=1):
        lines.extend(
            [
                f"### {index}. {_inline(action.get('days', ''))}",
                "",
                f"- 行动：{_inline(action.get('action', ''))}",
                f"- 负责人：{_inline(action.get('owner', ''))}",
                f"- 指标：{_inline(action.get('metric', ''))}",
                f"- 停止条件：{_inline(action.get('stop_condition', ''))}",
                f"- 预算上限：¥{int(action.get('budget_limit', 0)):,}",
                "",
            ]
        )

    lines.extend(["## 研究缺口", ""])
    gaps = memo.get("research_gaps", [])
    lines.extend(f"- {_inline(item)}" for item in gaps)
    if not gaps:
        lines.append("- 当前工作流未记录未解决研究缺口。")
    lines.extend(["", "## 证据清单", ""])
    for card in snapshot.evidence:
        provenance = "合成演示材料" if card.is_demo else "联网来源摘要，待人工核验"
        lines.append(
            f"- [{_inline(card.title)}]({card.source_url}) — {_inline(card.summary)}（{provenance}；证据 ID：{card.id}）"
        )
    if not snapshot.evidence:
        lines.append("- 无可用证据。")

    review_status = _REVIEW_STATUS.get(snapshot.status.value, snapshot.status.value)
    lines.extend(
        [
            "",
            "## 人工审批",
            "",
            f"- 状态：{_inline(review_status)}",
            f"- 审批备注：{_inline(snapshot.review_note) if snapshot.review_note else '无'}",
            "- 边界：审批只记录，不执行业务动作；退款、发信、改价或发布仍需人在外部系统执行。",
            "",
        ]
    )
    return "\n".join(lines)
