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
