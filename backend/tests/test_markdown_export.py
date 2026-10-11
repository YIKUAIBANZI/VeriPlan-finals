from app.markdown_export import render_decision_markdown
from app.repository import DecisionRepository
from app.schemas import BusinessBaseline
from app.workflow import WorkflowEngine
from tests.test_repository import sample_decision


def delivered_snapshot(tmp_path, *, baseline=None):
    repository = DecisionRepository(tmp_path / "db")
    payload = sample_decision()
    if baseline is not None:
        payload = payload.model_copy(update={"business_baseline": baseline})
    engine = WorkflowEngine(repository)
    decision = repository.create(payload)
    engine.run(decision.id)
    engine.confirm_clarification(decision.id)
    return engine.run(decision.id)


def test_markdown_export_contains_decision_baseline_memo_evidence_and_boundaries(tmp_path):
    snapshot = delivered_snapshot(
        tmp_path,
        baseline=BusinessBaseline(
            monthly_ticket_volume=1_000,
            repetitive_ticket_rate=60,
            average_handle_minutes=8,
            loaded_hourly_cost=40,
            expected_ai_resolution_rate=70,
            review_minutes_per_ai_ticket=1,
            monthly_tool_cost=800,
            max_acceptable_error_rate=2,
        ),
    )

    markdown = render_decision_markdown(snapshot)

    assert markdown.startswith("# VeriPlan 决策 Memo\n")
    assert "## 业务基线" in markdown
    assert "月售后工单量：1,000" in markdown
    assert "预计月净节省：¥1,160.00" in markdown
    assert "用户输入试算，不是已验证收益" in markdown
    assert "## 最终建议" in markdown
    assert "工作流状态：待人工审批" in markdown
    assert "## 行动计划" in markdown
    assert "## 证据清单" in markdown
    assert "合成演示材料" in markdown
    assert "## 人工审批" in markdown
    assert "审批只记录，不执行业务动作" in markdown


def test_markdown_export_keeps_unknown_baseline_as_collection_work(tmp_path):
    markdown = render_decision_markdown(delivered_snapshot(tmp_path))

    assert "月售后工单量：未知" in markdown
    assert "收益试算：输入不完整，未计算" in markdown
    assert "### 内部数据采集任务" in markdown
    assert "抽样最近 7 天售后工单" in markdown


def test_markdown_export_flattens_user_line_breaks_in_inline_fields(tmp_path):
    snapshot = delivered_snapshot(tmp_path).model_copy(
        update={"question": "是否试点？\n# 伪造章节"}
    )

    markdown = render_decision_markdown(snapshot)

    assert "- 决策问题：是否试点？ # 伪造章节" in markdown
    assert "\n# 伪造章节" not in markdown
