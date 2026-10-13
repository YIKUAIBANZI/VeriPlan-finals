import { scenarioExamples, emptyBaseline } from "../fixtures/scenarios";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DecisionForm } from "./DecisionForm";

afterEach(cleanup);

describe("DecisionForm business baseline", () => {
  it("submits every empty optional baseline field as unknown", () => {
    const onSubmit = vi.fn();
    render(<DecisionForm busy={false} onSubmit={onSubmit} initial={{ ...scenarioExamples.ai_tool_pilot, business_baseline: { ...emptyBaseline } }} />);
    fireEvent.change(screen.getByLabelText("经营决策问题"), {
      target: { value: "我们是否应该先小范围验证 AI 售后客服？" },
    });

    fireEvent.click(screen.getByRole("button", { name: "创建并开始研究" }));

    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
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
    }));
  });

  it("converts optional numeric inputs and restores cleared values to unknown", () => {
    const onSubmit = vi.fn();
    render(<DecisionForm busy={false} onSubmit={onSubmit} initial={{ ...scenarioExamples.ai_tool_pilot, business_baseline: { ...emptyBaseline } }} />);
    fireEvent.change(screen.getByLabelText("经营决策问题"), {
      target: { value: "我们是否应该先小范围验证 AI 售后客服？" },
    });
    fireEvent.click(screen.getByText("业务基线（可选）"));
    fireEvent.change(screen.getByLabelText("月售后工单量"), { target: { value: "1250" } });
    fireEvent.change(screen.getByLabelText("重复咨询占比"), { target: { value: "62.5" } });
    fireEvent.change(screen.getByLabelText("重复咨询占比"), { target: { value: "" } });

    fireEvent.click(screen.getByRole("button", { name: "创建并开始研究" }));

    expect(onSubmit.mock.calls[0][0].business_baseline).toEqual(
      expect.objectContaining({ monthly_ticket_volume: 1250, repetitive_ticket_rate: null }),
    );
  });

  it("fills a clearly disclosed synthetic baseline with the demo example", () => {
    render(<DecisionForm busy={false} onSubmit={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "填入 AI 售后客服示例" }));
    fireEvent.click(screen.getByText("业务基线（可选）"));

    expect(screen.getByLabelText("月售后工单量")).toHaveValue(1200);
    expect(screen.getByLabelText("预计 AI 独立解决率")).toHaveValue(70);
    expect(screen.getByText(/数字是合成的/)).toBeVisible();
  });
});

it("fills all five scenarios and omits the customer baseline outside AI pilots", () => {
  const onSubmit = vi.fn();
  render(<DecisionForm busy={false} onSubmit={onSubmit} />);
  for (const [name, scenario] of [["AI 售后客服", "ai_tool_pilot"], ["首位员工", "first_hire"], ["大额订单", "big_order"], ["营销投入", "marketing_spend"], ["其他决策", "general"]]) {
    fireEvent.click(screen.getByRole("button", { name: `填入 ${name}示例` }));
    fireEvent.click(screen.getByRole("button", { name: "创建并开始研究" }));
    const payload = onSubmit.mock.lastCall![0];
    expect(payload.scenario).toBe(scenario);
    expect(payload.horizon_days).toBeGreaterThanOrEqual(7);
    expect(payload).not.toHaveProperty("time_window");
    if (scenario !== "ai_tool_pilot") expect(payload).not.toHaveProperty("business_baseline");
  }
});

it("edits bounded risks and assumptions with confidence, preserving the selected horizon", () => {
  const onSubmit = vi.fn();
  render(<DecisionForm busy={false} onSubmit={onSubmit} />);
  fireEvent.click(screen.getByRole("button", { name: "填入 首位员工示例" }));
  fireEvent.change(screen.getByLabelText("时间窗口"), { target: { value: "180" } });
  fireEvent.change(screen.getByLabelText("假设 1 数值"), { target: { value: "25000" } });
  fireEvent.change(screen.getByLabelText("假设 1 信心"), { target: { value: "95" } });
  fireEvent.click(screen.getByText("补充你已想到的风险和数字假设"));
  fireEvent.change(screen.getByLabelText("已知风险"), { target: { value: "a\n\n b \nc\nd\ne\nf" } });
  expect(screen.getByText("只会提交前 5 条。")).toBeVisible();
  while (!screen.getByRole("button", { name: "添加假设" }).hasAttribute("disabled")) fireEvent.click(screen.getByRole("button", { name: "添加假设" }));
  expect(screen.getAllByLabelText(/^假设 \d 信心$/)).toHaveLength(8);
  for (let n = 8; n >= 2; n--) fireEvent.click(screen.getByRole("button", { name: `删除假设 ${n}` }));
  fireEvent.click(screen.getByRole("button", { name: "创建并开始研究" }));
  expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ horizon_days: 180, known_risks: ["a", "b", "c", "d", "e"], assumptions: [expect.objectContaining({ value: 25000, confidence: 95 })] }));
});

it("never sends inherited customer baseline fields from a general snapshot", () => {
  const onSubmit = vi.fn();
  render(<DecisionForm busy={false} onSubmit={onSubmit} initial={{ ...scenarioExamples.general, business_baseline: emptyBaseline }} />);
  fireEvent.click(screen.getByRole("button", { name: "创建并开始研究" }));
  expect(onSubmit.mock.lastCall![0]).not.toHaveProperty("business_baseline");
});

it("starts blank: no prefilled goal or budget, and requires them before submitting", () => {
  const onSubmit = vi.fn();
  render(<DecisionForm busy={false} onSubmit={onSubmit} />);
  expect(screen.getByLabelText("首要目标")).toHaveValue("");
  expect(screen.getByLabelText("预算上限（元）")).toHaveValue(null);
  fireEvent.change(screen.getByLabelText("经营决策问题"), { target: { value: "要不要把三个工程师换成 AI 编程助手？" } });
  fireEvent.click(screen.getByRole("button", { name: "创建并开始研究" }));
  expect(onSubmit).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("预算上限（元）"), { target: { value: "30000" } });
  fireEvent.change(screen.getByLabelText("首要目标"), { target: { value: "交付不降" } });
  fireEvent.click(screen.getByRole("button", { name: "创建并开始研究" }));
  expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ scenario: "general", budget_limit: 30000, known_risks: [] }));
  expect(onSubmit.mock.lastCall![0]).not.toHaveProperty("business_baseline");
});
