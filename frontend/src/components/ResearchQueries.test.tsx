import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { describe, expect, it } from "vitest";
import { ResearchQueries } from "./ResearchQueries";

const queries = [
  {
    id: 1,
    ordinal: 0,
    query: "baseline",
    status: "succeeded" as const,
    attempt_count: 1,
    last_error_code: null,
    evidence_count: 2,
    created_at: "2026-09-11T00:00:00Z",
    started_at: "2026-09-11T00:00:01Z",
    finished_at: "2026-09-11T00:00:02Z",
  },
  {
    id: 2,
    ordinal: 1,
    query: "risk",
    status: "failed" as const,
    attempt_count: 1,
    last_error_code: "search_timeout",
    evidence_count: 0,
    created_at: "2026-09-11T00:00:00Z",
    started_at: "2026-09-11T00:00:01Z",
    finished_at: "2026-09-11T00:00:02Z",
  },
];

describe("ResearchQueries", () => {
  it("shows disclosed queries and aggregate safe statuses", () => {
    render(<ResearchQueries queries={queries} />);
    expect(screen.getByText("baseline")).toBeVisible();
    expect(screen.getByText("已保存 2 条新证据")).toBeVisible();
    expect(screen.getByText("risk")).toBeVisible();
    expect(screen.getByText("本次查询未完成")).toBeVisible();
    expect(screen.queryByText("search_timeout")).not.toBeInTheDocument();
  });

  it("renders nothing before planning creates queries", () => {
    const { container } = render(<ResearchQueries queries={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
