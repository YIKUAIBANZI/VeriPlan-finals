import { afterEach, expect, it, vi } from "vitest";

import { api } from "./api";

afterEach(() => vi.unstubAllGlobals());

it("reads a decision export as markdown text instead of JSON", async () => {
  const fetch = vi.fn().mockResolvedValue(
    new Response("# VeriPlan 决策 Memo", {
      status: 200,
      headers: { "Content-Type": "text/markdown; charset=utf-8" },
    }),
  );
  vi.stubGlobal("fetch", fetch);

  await expect(api.exportDecision("decision / 1")).resolves.toBe(
    "# VeriPlan 决策 Memo",
  );
  expect(fetch).toHaveBeenCalledWith(
    "/api/decisions/decision%20%2F%201/export.md",
    expect.objectContaining({ method: "GET" }),
  );
});

it("uses the existing not-ready message for a premature export", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response("not ready", { status: 409 })),
  );

  await expect(api.exportDecision("draft")).rejects.toThrow(
    "任务状态已更新，请刷新任务后继续。",
  );
});

it("uses the frozen endpoint paths and JSON envelopes", async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
  vi.stubGlobal("fetch", fetch);
  await api.labelObjections("a / b", { O1: "adopted" });
  expect(fetch).toHaveBeenLastCalledWith("/api/decisions/a%20%2F%20b/objection-labels", expect.objectContaining({ method: "POST", body: JSON.stringify({ labels: { O1: "adopted" } }) }));
  const outcome = { checkpoint: "day_30" as const, actuals: [{ assumption_id: "A1", actual_value: 12000 }], note: "实收" };
  await api.saveOutcomes("a", outcome);
  expect(fetch).toHaveBeenLastCalledWith("/api/decisions/a/outcomes", expect.objectContaining({ method: "POST", body: JSON.stringify(outcome) }));
  const past = { question: "过去是否应该投入这笔营销费用？", scenario: "marketing_spend" as const, decision_date: "2026-07-01", assumptions: [{ label: "收入", category: "revenue" as const, value: 20000, unit: "元", confidence: 70, actual_value: 12000 }], note: "回溯" };
  await api.createRetrospective(past);
  expect(fetch).toHaveBeenLastCalledWith("/api/retrospectives", expect.objectContaining({ body: JSON.stringify(past) }));
  await api.getCalibration();
  expect(fetch).toHaveBeenLastCalledWith("/api/calibration", expect.objectContaining({ method: "GET", body: undefined }));
});
