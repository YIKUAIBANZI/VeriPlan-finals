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
