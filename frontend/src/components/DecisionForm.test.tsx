import { scenarioExamples, emptyBaseline } from "../fixtures/scenarios";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DecisionForm } from "./DecisionForm";

afterEach(cleanup);

describe("DecisionForm business baseline", () => {
  it("submits every empty optional baseline field as unknown", () => {
    const onSubmit = vi.fn();
    render(<DecisionForm busy={false} onSubmit={onSubmit} />);
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
    render(<DecisionForm busy={false} onSubmit={onSubmit} />);
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
    expect(screen.getByText(/合成演示数字/)).toBeVisible();
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
  while (!screen.getByRole("button", { name: "添加已知风险" }).hasAttribute("disabled")) fireEvent.click(screen.getByRole("button", { name: "添加已知风险" }));
  expect(screen.getAllByLabelText(/^已知风险 \d$/)).toHaveLength(5);
  while (!screen.getByRole("button", { name: "添加假设" }).hasAttribute("disabled")) fireEvent.click(screen.getByRole("button", { name: "添加假设" }));
  expect(screen.getAllByLabelText(/^假设 \d 信心$/)).toHaveLength(8);
  for (let n = 8; n >= 2; n--) fireEvent.click(screen.getByRole("button", { name: `删除假设 ${n}` }));
  for (let n = 5; n >= 1; n--) fireEvent.click(screen.getByRole("button", { name: `删除风险 ${n}` }));
  fireEvent.click(screen.getByRole("button", { name: "创建并开始研究" }));
  expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ horizon_days: 180, known_risks: [], assumptions: [expect.objectContaining({ value: 25000, confidence: 95 })] }));
});

it("never sends inherited customer baseline fields from a general snapshot", () => {
  const onSubmit = vi.fn();
  render(<DecisionForm busy={false} onSubmit={onSubmit} initial={{ ...scenarioExamples.general, business_baseline: emptyBaseline }} />);
  fireEvent.click(screen.getByRole("button", { name: "创建并开始研究" }));
  expect(onSubmit.mock.lastCall![0]).not.toHaveProperty("business_baseline");
});
