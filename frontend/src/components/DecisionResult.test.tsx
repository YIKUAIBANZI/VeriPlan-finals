import { splitDecision, outcomeDecision, legacyDecision } from "../fixtures/decisions";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ComponentProps } from "react";

import type { Decision } from "../types";
import { DecisionResult } from "./DecisionResult";

const decision: Decision = {
  id: "decision-1",
  question: "我们是否应该试点 AI 售后客服？",
  time_window: "14 天",
  budget_limit: 8000,
  primary_goal: "降低重复咨询",
  business_baseline: {
    monthly_ticket_volume: null,
    repetitive_ticket_rate: null,
    average_handle_minutes: null,
    loaded_hourly_cost: null,
    expected_ai_resolution_rate: null,
    review_minutes_per_ai_ticket: null,
    monthly_tool_cost: null,
    max_acceptable_error_rate: null,
  },
  baseline_analysis: {
    known_field_count: 0,
    total_field_count: 8,
    is_calculable: false,
    automatable_ticket_volume: null,
    monthly_hours_saved: null,
    estimated_monthly_net_savings: null,
    collection_tasks: [],
    disclaimer: "用户输入试算，不是已验证收益",
  },
  mode: "live",
  status: "awaiting_review",
  research_queries: [],
  evidence: [
    {
      id: "related",
      title: "Related source",
      summary: "A related source statement.",
      source_url: "https://example.com/related",
      stance: "supports",
      reliability: "high",
      is_demo: false,
    },
    {
      id: "unrelated",
      title: "Unrelated source",
      summary: "An unrelated source statement.",
      source_url: "https://example.com/unrelated",
      stance: "context",
      reliability: "medium",
      is_demo: false,
    },
    {
      id: "contradictory",
      title: "Contradictory source",
      summary: "A contradictory source statement.",
      source_url: "https://example.com/contradictory",
      stance: "opposes",
      reliability: "high",
      is_demo: false,
    },
  ],
  events: [],
  outputs: {},
  memo: {
    summary: "先做受限试点",
    support_score: 70,
    score_explanation: "来源仍需人工核对。",
    facts: [
      { text: "Related claim", evidence_ids: ["related"] },
      { text: "Unrelated claim", evidence_ids: ["unrelated"] },
      { text: "Contradictory claim", evidence_ids: ["contradictory"] },
    ],
    inferences: [{ text: "Agent inference", evidence_ids: [] }],
    action_plan: [
      {
        days: "1–3",
        action: "采集基线",
        owner: "运营负责人",
        metric: "完成样本记录",
        stop_condition: "无合法样本则停止",
        budget_limit: 1200,
      },
    ],
    research_gaps: ["仍需核对真实工单基线"],
  },
  review_note: null,
};

afterEach(cleanup);

function renderResult(
  props: Partial<ComponentProps<typeof DecisionResult>> = {},
) {
  return render(
    <DecisionResult
      decision={decision}
      busy={false}
      onReview={vi.fn()}
      onExportMarkdown={vi.fn()}
      onPrint={vi.fn()}
      {...props}
    />,
  );
}

describe("DecisionResult trust boundaries", () => {
  it("labels cited statements as pending human verification for every stance", () => {
    renderResult();

    expect(
      screen.getByRole("heading", { name: /来源陈述（待人工核验）/ }),
    ).toBeVisible();
    expect(screen.getAllByRole("link", { name: "查看引用来源" })).toHaveLength(3);
    expect(screen.getByText(/引用只建立可回看关系/)).toBeVisible();
    expect(screen.getByText("仍需核对真实工单基线")).toBeVisible();
    expect(screen.queryByText(/已核验支持/)).not.toBeInTheDocument();
  });

  it("shows the stored window and each action budget", () => {
    renderResult();

    expect(screen.getByRole("heading", { name: "验证行动计划" })).toBeVisible();
    expect(screen.getByText("单项预算 ¥1,200")).toBeVisible();
    expect(screen.getByText(/14 天/)).toBeVisible();
  });

  it("warns when a legacy record did not use the supported window", () => {
    renderResult({ decision: { ...decision, time_window: "3 days" } });

    expect(screen.getByText(/历史周期未对应当前可选范围/)).toBeVisible();
  });

  it("replaces approval controls with a read-only reason", () => {
    renderResult({ readOnlyReason: "历史任务来自另一运行模式，当前只读。" });

    expect(screen.getByText(/历史任务来自另一运行模式/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "采纳建议" })).not.toBeInTheDocument();
  });

  it("offers markdown download and browser print for a completed memo", () => {
    const onExportMarkdown = vi.fn();
    const onPrint = vi.fn();
    renderResult({ onExportMarkdown, onPrint });

    screen.getByRole("button", { name: "下载 Markdown" }).click();
    screen.getByRole("button", { name: "打印 / 存为 PDF" }).click();

    expect(onExportMarkdown).toHaveBeenCalledOnce();
    expect(onPrint).toHaveBeenCalledOnce();
  });
});

it("labels objections before approval and counts only saved adopted labels after approval", () => {
  const onLabel = vi.fn();
  const { rerender } = renderResult({ decision: splitDecision, onLabel });
  fireEvent.change(screen.getByLabelText("O1 风险标注"), { target: { value: "adopted" } });
  expect(onLabel).toHaveBeenCalledWith({ O1: "adopted" });
  expect(screen.queryByText("1 条改变了方案")).not.toBeInTheDocument();
  rerender(<DecisionResult decision={outcomeDecision} busy={false} onReview={vi.fn()} onLabel={onLabel} onExportMarkdown={vi.fn()} onPrint={vi.fn()} />);
  expect(screen.getByText("1 条改变了方案")).toBeVisible();
  expect(screen.getByLabelText("O1 风险标注")).toHaveValue("adopted");
});

it("prevents labels and review writes while saving or reading a cross-mode record", () => {
  const { rerender } = renderResult({ decision: splitDecision, busy: true, onLabel: vi.fn() });
  expect(screen.getByLabelText("O1 风险标注")).toBeDisabled();
  expect(screen.getByRole("button", { name: "采纳建议" })).toBeDisabled();
  rerender(<DecisionResult decision={splitDecision} busy={false} readOnlyReason="当前只读" onReview={vi.fn()} onLabel={vi.fn()} onExportMarkdown={vi.fn()} onPrint={vi.fn()} />);
  expect(screen.getByLabelText("O1 风险标注")).toBeDisabled();
});

it.each([
  ["go", "可以推进"], ["go_with_conditions", "满足条件后推进"], ["small_test_first", "先做小规模验证"],
  ["defer", "暂缓决定"], ["no_go", "不建议推进"], ["pilot_before_rollout", "先试点再推广"], ["do_not_pilot", "不建议试点"],
] as const)("renders and exports recommendation %s", (recommendation, label) => {
  const onExportMarkdown = vi.fn();
  renderResult({ decision: { ...legacyDecision, memo: { ...legacyDecision.memo!, recommendation } }, onExportMarkdown });
  expect(screen.getByLabelText("推荐结论")).toHaveTextContent(label);
  fireEvent.click(screen.getByRole("button", { name: "下载 Markdown" }));
  expect(onExportMarkdown).toHaveBeenCalledOnce();
});
it("shows contract conditions and accepts a new 90-day window without a legacy warning", () => {
  renderResult({ decision: splitDecision });
  expect(screen.getByText(/O1：先取得预付款，覆盖工资支出/)).toBeVisible();
  expect(screen.queryByText(/历史周期未对应/)).not.toBeInTheDocument();
});

it("still allows historical export while Live writes are locked", () => {
  renderResult({ decision: legacyDecision, writeDisabled: true });
  expect(screen.getByRole("button", { name: "下载 Markdown" })).toBeEnabled();
});
