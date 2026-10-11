import { cleanup, render, screen, within } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, expect, it } from "vitest";
import { CouncilPanel } from "./CouncilPanel";
import { councilEvent, splitDecision } from "../fixtures/decisions";
afterEach(cleanup);
it("starts three seats together and reveals completed events before aggregate output exists", () => {
  const decision = { ...splitDecision, status: "analyzing" as const, outputs: {}, events: [] };
  const { rerender } = render(<CouncilPanel decision={decision} />);
  expect(screen.getAllByText("思考中")).toHaveLength(3);
  rerender(<CouncilPanel decision={{ ...decision, events: [councilEvent("cfo", "completed")] }} />);
  expect(screen.getAllByText("思考中")).toHaveLength(2);
  expect(screen.getByText(/财务官：反对——现金储备/)).toBeVisible();
  rerender(<CouncilPanel decision={splitDecision} />);
  expect(screen.getByText("委员会意见分裂")).toBeVisible();
  expect(within(screen.getByRole("article", { name: "财务官" })).getByText("反对")).toBeVisible();
  expect(screen.getByRole("article", { name: "财务官" })).toHaveAttribute("data-stance", "oppose");
});
it("does not reuse prior attempt completions while retrying the analyzing stage", () => {
  render(<CouncilPanel decision={{ ...splitDecision, status: "analyzing", events: [...splitDecision.events, { stage: "analyzing", status: "started", summary: "重跑", created_at: "2026-10-11T10:01:00Z" }] }} />);
  expect(screen.getAllByText("思考中")).toHaveLength(3);
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
