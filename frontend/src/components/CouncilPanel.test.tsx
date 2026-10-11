import { cleanup, render, screen, within } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, expect, it } from "vitest";
import { CouncilPanel } from "./CouncilPanel";
import { councilEvent, splitDecision } from "../fixtures/decisions";
afterEach(cleanup);
it("starts four seats together and reveals completed events before aggregate output exists", () => {
  const decision = { ...splitDecision, status: "analyzing" as const, outputs: {}, events: [] };
  const { rerender } = render(<CouncilPanel decision={decision} />);
  expect(screen.getAllByText("思考中")).toHaveLength(4);
  rerender(<CouncilPanel decision={{ ...decision, events: [councilEvent("cfo", "completed")] }} />);
  expect(screen.getAllByText("思考中")).toHaveLength(3);
  expect(screen.getByText(/财务官：反对——现金储备/)).toBeVisible();
  rerender(<CouncilPanel decision={splitDecision} />);
  expect(screen.getByText("委员会意见分裂")).toBeVisible();
  expect(within(screen.getByRole("article", { name: "财务官" })).getByText("反对")).toBeVisible();
  expect(screen.getByRole("article", { name: "财务官" })).toHaveAttribute("data-stance", "oppose");
});
it("does not reuse prior attempt completions while retrying the analyzing stage", () => {
  render(<CouncilPanel decision={{ ...splitDecision, status: "analyzing", events: [...splitDecision.events, { stage: "analyzing", status: "started", summary: "重跑", created_at: "2026-10-11T10:01:00Z" }] }} />);
  expect(screen.getAllByText("思考中")).toHaveLength(4);
  expect(screen.queryByText("委员会意见分裂")).not.toBeInTheDocument();
});
it("stops thinking on failure, and never invents a council for a retrospective", () => {
  const { rerender } = render(<CouncilPanel decision={{ ...splitDecision, outputs: {}, status: "failed", events: [councilEvent("cfo", "started")] }} />);
  expect(screen.queryByText("思考中")).not.toBeInTheDocument();
  expect(screen.getAllByText("审查中断")).toHaveLength(3);
  rerender(<CouncilPanel decision={{ ...splitDecision, status: "retrospective" }} />);
  expect(screen.queryByText("AI 决策委员会")).not.toBeInTheDocument();
});

it("colors a completed event using its explicit stance before structured members arrive", () => {
  render(<CouncilPanel decision={{ ...splitDecision, status: "analyzing", outputs: {}, events: [councilEvent("cfo", "completed")] }} />);
  expect(screen.getByRole("article", { name: "财务官" })).toHaveAttribute("data-stance", "oppose");
});

it("renders four seats, the selected expert reason, model labels and fallback status", () => {
  const decision = structuredClone(splitDecision);
  decision.outputs.planning = { summary: "规划", expert_kind: "legal_compliance", expert_reason: "招聘需要核对用工义务", expert_source: "model" };
  decision.outputs.analyzing.members = [
    ...decision.outputs.analyzing.members!.filter(m => m.role !== "expert").map(m => ({ ...m, model_label: "DeepSeek v4-flash" })),
    { ...decision.outputs.analyzing.members![0], role: "expert", expert_kind: "legal_compliance", model_label: "通义千问 qwen3.8-flash", fallback_from: "minimax" },
  ];
  render(<CouncilPanel decision={decision} />);
  expect(screen.getAllByRole("article")).toHaveLength(4);
  const expert = screen.getByRole("article", { name: "本题加派：法务合规专家" });
  expect(within(expert).getByText("招聘需要核对用工义务")).toBeVisible();
  expect(within(expert).getByText("通义千问 qwen3.8-flash")).toBeVisible();
  expect(within(expert).getByText("已切换备用模型")).toBeVisible();
  expect(screen.getAllByText("DeepSeek v4-flash")).toHaveLength(3);
  expect(screen.queryByText("按场景默认")).not.toBeInTheDocument();
});

it("shows scenario-default expert selection during work and waits for the fourth completion", () => {
  const decision = structuredClone(splitDecision);
  decision.status = "analyzing";
  decision.outputs.planning = { summary: "规划", expert_kind: "operations", expert_reason: "按场景默认", expert_source: "scenario_default" };
  decision.events = ["opportunity", "cfo", "risk"].map(role => councilEvent(role as "cfo", "completed"));
  const { rerender } = render(<CouncilPanel decision={decision} />);
  expect(screen.getByRole("heading", { name: "本题加派：运营产能专家" })).toBeVisible();
  expect(screen.getByText("按场景默认")).toBeVisible();
  expect(screen.getAllByText("思考中")).toHaveLength(1);
  expect(screen.queryByText("委员会意见分裂")).not.toBeInTheDocument();
  decision.events.push({ stage: "council:expert", status: "completed", summary: "运营产能专家：反对——产能不足", created_at: "2026-10-12T10:00:00Z" });
  rerender(<CouncilPanel decision={decision} />);
  expect(screen.getByText("委员会意见分裂")).toBeVisible();
});

it("renders historical three-seat records without an empty expert seat or invented metadata", () => {
  const decision = structuredClone(splitDecision);
  delete decision.outputs.planning;
  decision.outputs.analyzing.members = decision.outputs.analyzing.members!.filter(m => m.role !== "expert").map(({ model_label: _model, fallback_from: _fallback, ...m }) => m);
  decision.events = decision.events.filter(e => e.stage !== "council:expert");
  render(<CouncilPanel decision={decision} />);
  expect(screen.getAllByRole("article")).toHaveLength(3);
  expect(screen.queryByText(/本题加派/)).not.toBeInTheDocument();
  expect(screen.queryByText("已切换备用模型")).not.toBeInTheDocument();
});
