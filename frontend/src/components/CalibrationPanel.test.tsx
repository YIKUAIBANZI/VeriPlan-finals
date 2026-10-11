import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, expect, it, vi } from "vitest";
import { CalibrationPanel } from "./CalibrationPanel";
import { calibrationFixture } from "../fixtures/decisions";
import type { DecisionApi } from "../api";
afterEach(cleanup);
it("renders signed bias, hit rate, confidence gap and explicit provenance", async () => {
  const profile = { ...calibrationFixture, mode: "live", samples: [{ decision_id: "live-1", assumption_id: "A1", category: "revenue", source: "live" }, { decision_id: "past-1", assumption_id: "A1", category: "revenue", source: "retrospective" }] };
  render(<CalibrationPanel mode="live" api={{ getCalibration: vi.fn().mockResolvedValue(profile) } as unknown as DecisionApi} onCreated={vi.fn()} />);
  expect(await screen.findByText("-38.5%")).toBeVisible();
  expect(screen.getByText("0%")).toBeVisible();
  expect(screen.getByText("70 个百分点")).toBeVisible();
  expect(screen.getByText("Live")).toBeVisible();
  expect(screen.getByText("回溯")).toBeVisible();
});
it("offers retry for failures and labels synthetic samples without mixing modes", async () => {
  const getCalibration = vi.fn().mockRejectedValueOnce(new Error("画像加载失败")).mockResolvedValue(calibrationFixture);
  const { rerender } = render(<CalibrationPanel mode="demo" api={{ getCalibration } as unknown as DecisionApi} onCreated={vi.fn()} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("画像加载失败");
  fireEvent.click(screen.getByRole("button", { name: "重试加载画像" }));
  expect(await screen.findAllByText("合成")).toHaveLength(3);
  rerender(<CalibrationPanel mode="live" api={{ getCalibration } as unknown as DecisionApi} onCreated={vi.fn()} />);
  expect(await screen.findByText(/画像模式与当前应用不一致/)).toBeVisible();
  expect(screen.queryByText("-38.5%")).not.toBeInTheDocument();
});
