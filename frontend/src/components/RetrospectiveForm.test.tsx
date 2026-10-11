import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, expect, it, vi } from "vitest";
import { RetrospectiveForm } from "./RetrospectiveForm";
afterEach(cleanup);
it("submits a historical decision with date, confidence and actuals, without workflow fields", () => {
  const onSubmit = vi.fn();
  render(<RetrospectiveForm busy={false} onSubmit={onSubmit} />);
  fireEvent.change(screen.getByLabelText("过去的决策问题"), { target: { value: "过去是否应该投入三万元推广新产品？" } });
  fireEvent.change(screen.getByLabelText("决策日期"), { target: { value: "2026-07-01" } });
  fireEvent.change(screen.getByLabelText("过去的决策场景"), { target: { value: "marketing_spend" } });
  fireEvent.click(screen.getByRole("button", { name: "添加假设" }));
  fireEvent.change(screen.getByLabelText("假设 1 标签"), { target: { value: "月收入" } });
  fireEvent.change(screen.getByLabelText("假设 1 数值"), { target: { value: "20000" } });
  fireEvent.change(screen.getByLabelText("假设 1 实际值"), { target: { value: "12000" } });
  fireEvent.click(screen.getByRole("button", { name: "保存回溯记录" }));
  expect(onSubmit).toHaveBeenCalledWith({ question: "过去是否应该投入三万元推广新产品？", scenario: "marketing_spend", decision_date: "2026-07-01", assumptions: [{ label: "月收入", category: "revenue", value: 20000, unit: "元", confidence: 70, actual_value: 12000 }], note: "" });
});
it("requires actuals and locks the form while saving", () => {
  const { rerender } = render(<RetrospectiveForm busy={false} onSubmit={vi.fn()} />);
  expect(screen.getByRole("button", { name: "保存回溯记录" })).toBeDisabled();
  rerender(<RetrospectiveForm busy={true} onSubmit={vi.fn()} />);
  expect(screen.getByLabelText("过去的决策问题")).toBeDisabled();
});
