import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, expect, it, vi } from "vitest";
import { OutcomesPanel } from "./OutcomesPanel";
import { outcomeDecision, splitDecision } from "../fixtures/decisions";
afterEach(cleanup);
it("only offers outcome writes after approval and preserves an explicit zero actual", () => {
  const onSave = vi.fn();
  const { rerender } = render(<OutcomesPanel decision={splitDecision} busy={false} onSave={onSave} />);
  expect(screen.queryByRole("button", { name: "保存实际结果" })).not.toBeInTheDocument();
  rerender(<OutcomesPanel decision={{ ...outcomeDecision, outcomes: [] }} busy={false} onSave={onSave} />);
  expect(screen.getByRole("button", { name: "保存实际结果" })).toBeDisabled();
  fireEvent.change(screen.getByLabelText("回填节点"), { target: { value: "custom" } });
  fireEvent.change(screen.getByLabelText("A1 实际值"), { target: { value: "0" } });
  fireEvent.change(screen.getByLabelText("结果备注"), { target: { value: "第 45 天复盘" } });
  fireEvent.click(screen.getByRole("button", { name: "保存实际结果" }));
  expect(onSave).toHaveBeenCalledWith({ checkpoint: "custom", note: "第 45 天复盘", actuals: [{ assumption_id: "A1", actual_value: 0 }] });
});
it("shows server-computed errors including zero-prediction uncomputable cases", () => {
  const decision = { ...outcomeDecision, outcomes: [{ ...outcomeDecision.outcomes![0], actuals: [{ assumption_id: "A1", actual_value: 12000, error_pct: null }] }] };
  const { rerender } = render(<OutcomesPanel decision={decision} busy={false} onSave={vi.fn()} readOnlyReason="当前只读" />);
  expect(screen.getByText("不可计算")).toBeVisible();
  expect(screen.queryByRole("button", { name: "保存实际结果" })).not.toBeInTheDocument();
  rerender(<OutcomesPanel decision={outcomeDecision} busy={false} onSave={vi.fn()} />);
  expect(screen.getByText("-40%")).toBeVisible();
  expect(screen.getByText(/同一节点会覆盖/)).toBeVisible();
});
