import { cleanup, render, screen } from "@testing-library/react";
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

    expect(screen.getByText(/旧模板未受当前 14 天约束校验/)).toBeVisible();
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
