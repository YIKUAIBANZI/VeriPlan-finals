import { cleanup, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, expect, it } from "vitest";
import { ChallengePanel } from "./ChallengePanel";
import { legacyDecision, splitDecision } from "../fixtures/decisions";
afterEach(cleanup);
it("uses the server novelty count, discloses severity, targets and known risk overlap", () => {
  render(<ChallengePanel decision={splitDecision} />);
  expect(screen.getByRole("heading", { name: "反方提出 1 条你没写过的风险" })).toBeVisible();
  expect(screen.getByText(/假设 90 天后失败/)).toBeVisible();
  expect(screen.getByText("阻断风险")).toBeVisible();
  expect(screen.getByText("你没想到")).toBeVisible();
  expect(screen.getByText(/你已提到：需求不稳定/)).toBeVisible();
  expect(screen.getAllByText(/针对假设：A1/)).toHaveLength(2);
});
it("keeps legacy objections readable without claiming new risk counts", () => {
  render(<ChallengePanel decision={legacyDecision} />);
  expect(screen.getByText("误答风险")).toBeVisible();
  expect(screen.queryByText(/条你没写过/)).not.toBeInTheDocument();
});

it("shows immutable historical warnings and the exact adjusted-reference disclaimer", () => {
  render(<ChallengePanel decision={splitDecision} />);
  expect(screen.getByText("你过去 3 次收入类预测平均高估 38.5%")).toBeVisible();
  expect(screen.getByText(/A1 .*修正参考值：12,300/)).toBeVisible();
  expect(screen.getByText("按你历史偏差修正的参考值，不是预测")).toBeVisible();
});
