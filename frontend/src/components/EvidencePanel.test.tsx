import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, describe, expect, it } from "vitest";

import type { Evidence } from "../types";
import { EvidencePanel } from "./EvidencePanel";

const demoEvidence: Evidence = {
  id: "demo-1",
  title: "演示客服工单摘要",
  summary: "这是用于说明流程的合成材料。",
  source_url: "https://demo.invalid/customer-support",
  stance: "supports",
  reliability: "low",
  is_demo: true,
};

const liveEvidence: Evidence = {
  id: "live-1",
  title: "第三方行业资料",
  summary: "这是搜索服务返回的来源摘要。",
  source_url: "https://example.com/report",
  stance: "context",
  reliability: "medium",
  is_demo: false,
};

afterEach(cleanup);

function expandAll() {
  for (const row of screen.queryAllByRole("button", { expanded: false })) fireEvent.click(row);
}

describe("EvidencePanel provenance labels", () => {
  it("labels every demo card as synthetic placeholder material", () => {
    render(<EvidencePanel evidence={[demoEvidence]} />);
    expandAll();

    expect(screen.getByText("当前展示合成演示资料，未经联网核验。")).toBeVisible();
    expect(screen.getByText(/演示可靠度：/)).toBeVisible();
    expect(
      screen.getByText(`演示占位来源 · ${demoEvidence.source_url}`),
    ).toBeVisible();
  });

  it("labels a real card as an unverified online source", () => {
    render(<EvidencePanel evidence={[liveEvidence]} />);
    expandAll();

    expect(
      screen.getByText("包含联网来源摘要；它们是第三方信息，尚未独立核验。"),
    ).toBeVisible();
    expect(screen.getByText(/来源可靠度：/)).toBeVisible();
    expect(
      screen.getByText(`联网来源 · ${liveEvidence.source_url}`),
    ).toBeVisible();
    expect(screen.queryByText(/以下为合成演示资料/)).not.toBeInTheDocument();
  });

  it("keeps individual provenance labels when sources are mixed", () => {
    render(<EvidencePanel evidence={[demoEvidence, liveEvidence]} />);
    expandAll();

    const demoCard = screen.getByText(demoEvidence.title).closest("article");
    const liveCard = screen.getByText(liveEvidence.title).closest("article");
    expect(demoCard).not.toBeNull();
    expect(liveCard).not.toBeNull();
    expect(within(demoCard!).getByText(/演示可靠度：/)).toBeVisible();
    expect(within(demoCard!).getByText(/演示占位来源/)).toBeVisible();
    expect(within(liveCard!).getByText(/来源可靠度：/)).toBeVisible();
    expect(within(liveCard!).getByText(/联网来源/)).toBeVisible();
  });

  it("renders an empty state without making a provenance claim", () => {
    render(<EvidencePanel evidence={[]} />);
    expandAll();

    expect(
      screen.getByText("确认条件后，这里会展示支持与反对意见的依据。"),
    ).toBeVisible();
    expect(screen.queryByText(/合成演示资料/)).not.toBeInTheDocument();
    expect(screen.queryByText(/联网来源摘要/)).not.toBeInTheDocument();
  });

  it("shows source text without interpreting untrusted HTML", () => {
    const unsafeEvidence: Evidence = {
      ...liveEvidence,
      id: "live-unsafe",
      title: '<img src=x onerror="alert(1)">',
      summary: '<script>window.location="https://evil.example"</script>',
    };
    const { container } = render(
      <EvidencePanel evidence={[unsafeEvidence]} />,
    );
    expandAll();

    expect(screen.getByText(unsafeEvidence.title)).toBeVisible();
    expect(screen.getByText(unsafeEvidence.summary)).toBeVisible();
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
    expect(
      screen.getByText(`联网来源 · ${unsafeEvidence.source_url}`),
    ).toBeVisible();
  });
});

describe("EvidencePanel navigation", () => {
  it("numbers cards by their real id so citations match, and starts collapsed", () => {
    render(<EvidencePanel evidence={[{ ...liveEvidence, id: "13" }, { ...liveEvidence, id: "14", stance: "opposes" }]} />);
    expect(screen.getByText("#13")).toBeVisible();
    expect(screen.getByText("#14")).toBeVisible();
    expect(screen.getByText("2 条")).toBeVisible();
    expect(screen.getAllByText(liveEvidence.summary)[0]).not.toBeVisible();
  });

  it("filters by stance", () => {
    render(<EvidencePanel evidence={[{ ...liveEvidence, id: "1" }, { ...liveEvidence, id: "2", title: "反对材料", stance: "opposes" }]} />);
    fireEvent.click(screen.getByRole("button", { name: "反对 1" }));
    expect(screen.getByText("反对材料")).toBeVisible();
    expect(screen.queryByText("#1")).not.toBeInTheDocument();
  });
});
