import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

const input = {
  question: "我们是否应该先小范围验证 AI 售后客服？",
  time_window: "14 天",
  budget_limit: 8000,
  primary_goal: "降低重复咨询",
  business_baseline: {
    monthly_ticket_volume: null,
    repetitive_ticket_rate: null,
    average_handle_minutes: null,
    loaded_hourly_cost: null,
    expected_ai_resolution_rate: null,
    review_minutes_per_ai_ticket: null,
    monthly_tool_cost: null,
    max_acceptable_error_rate: null,
  },
};
const snapshot = (status = "draft", mode: "demo" | "live" = "demo") => ({
  id: "decision-1",
  ...input,
  mode,
  status,
  research_queries: [],
  evidence: [],
  events: [],
  outputs: {},
  memo: null,
  review_note: null,
  baseline_analysis: {
    known_field_count: 0,
    total_field_count: 8,
    is_calculable: false,
    automatable_ticket_volume: null,
    monthly_hours_saved: null,
    estimated_monthly_net_savings: null,
    collection_tasks: ["抽样最近 7 天售后工单。"],
    disclaimer: "用户输入试算，不是已验证收益",
  },
});
function fakeApi(initial: any = snapshot()) {
  let state = initial;
  return {
    health: vi.fn(async () => ({
      mode: "demo",
      database: "ok",
      live_available: false,
    })),
    listDecisions: vi.fn(async () => (state.status === "draft" ? [] : [state])),
    createDecision: vi.fn(async () => (state = snapshot())),
    getDecision: vi.fn(async () => state),
    runDecision: vi.fn(
      async () =>
        (state = {
          ...state,
          status:
            state.status === "planning"
              ? "awaiting_review"
              : "awaiting_confirmation",
          outputs: { clarifying: { summary: "请确认试点范围" } },
        }),
    ),
    confirmDecision: vi.fn(
      async () => (state = { ...state, status: "planning" }),
    ),
    retryDecision: vi.fn(
      async () => (state = { ...state, status: "awaiting_confirmation" }),
    ),
    reviewDecision: vi.fn(
      async (_id: string, action: string, note: string) =>
        (state = { ...state, status: action, review_note: note }),
    ),
    exportDecision: vi.fn(async () => "# VeriPlan 决策 Memo"),
  };
}
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("decision workspace", () => {
  it("creates a labelled demo and requires clarification confirmation before research", async () => {
    const api = fakeApi();
    render(<App api={api as any} />);
    fireEvent.change(screen.getByLabelText("经营决策问题"), {
      target: { value: input.question },
    });
    fireEvent.click(screen.getByRole("button", { name: "创建并开始研究" }));
    expect(
      await screen.findByRole("button", { name: "确认条件并继续研究" }),
    ).toBeVisible();
    expect(screen.getByText("演示数据模式")).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "采纳建议" }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "确认条件并继续研究" }));
    expect(
      await screen.findByRole("button", { name: "采纳建议" }),
    ).toBeVisible();
  });

  it("records a human review and restores it from the ledger", async () => {
    const api = fakeApi({
      ...snapshot("awaiting_review"),
      memo: {
        summary: "先做小范围试点",
        support_score: 59,
        action_plan: [],
        facts: [],
        inferences: [],
      },
    });
    render(<App api={api as any} />);
    fireEvent.click(
      await screen.findByRole("button", { name: new RegExp(input.question) }),
    );
    await screen.findByRole("button", { name: "采纳建议" });
    fireEvent.change(screen.getByLabelText("审批备注"), {
      target: { value: "仅同意人工复核的试点" },
    });
    fireEvent.click(screen.getByRole("button", { name: "采纳建议" }));
    expect(
      await screen.findByText("仅同意人工复核的试点", { selector: "p" }),
    ).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "采纳建议" }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "新建决策" }));
    fireEvent.click(
      screen.getByRole("button", { name: new RegExp(input.question) }),
    );
    expect(
      await screen.findByText("仅同意人工复核的试点", { selector: "p" }),
    ).toBeVisible();
  });

  it("shows request errors and lets the user resume a failed run", async () => {
    const api = fakeApi(snapshot("failed"));
    api.retryDecision.mockRejectedValueOnce(new Error("服务暂时不可用"));
    render(<App api={api as any} />);
    fireEvent.click(
      await screen.findByRole("button", { name: new RegExp(input.question) }),
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "重试失败阶段" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "服务暂时不可用",
    );
    fireEvent.click(screen.getByRole("button", { name: "重试失败阶段" }));
    expect(
      await screen.findByRole("button", { name: "确认条件并继续研究" }),
    ).toBeVisible();
  });

  it("does not overwrite a new form when an old snapshot request completes", async () => {
    const api = fakeApi(snapshot("researching"));
    let resolve: (value: any) => void = () => {};
    api.getDecision.mockImplementationOnce(
      () =>
        new Promise((r) => {
          resolve = r;
        }),
    );
    render(<App api={api as any} />);
    fireEvent.click(
      await screen.findByRole("button", { name: new RegExp(input.question) }),
    );
    fireEvent.click(screen.getByRole("button", { name: "新建决策" }));
    await act(async () => resolve(snapshot("researching")));
    expect(screen.getByLabelText("经营决策问题")).toBeVisible();
  });

  it("shows truthful live copy and disclosed research query progress", async () => {
    const api = fakeApi({
      ...snapshot("researching", "live"),
      outputs: {
        planning: {
          summary: "先查询业务基线与风险。",
          research_questions: ["baseline", "risk"],
        },
      },
      research_queries: [
        {
          id: 1,
          ordinal: 0,
          query: "baseline",
          status: "succeeded",
          attempt_count: 1,
          last_error_code: null,
          evidence_count: 2,
          created_at: "2026-09-11T00:00:00Z",
          started_at: "2026-09-11T00:00:01Z",
          finished_at: "2026-09-11T00:00:02Z",
        },
      ],
    });
    api.health.mockResolvedValue({
      mode: "live",
      database: "ok",
      live_available: true,
    });

    render(<App api={api as any} />);
    fireEvent.click(
      await screen.findByRole("button", { name: new RegExp(input.question) }),
    );

    expect(await screen.findByText("真实联网模式")).toBeVisible();
    expect(screen.getByText(/真实联网决策/)).toHaveTextContent(
      "联网来源摘要仍需人工核验",
    );
    expect(screen.getByRole("region", { name: "公开搜索计划" })).toBeVisible();
    expect(screen.getByText("baseline", { selector: "li" })).toBeVisible();
    expect(screen.getByText("已保存 2 条新证据")).toBeVisible();
  });

  it("keeps a cross-mode historical task read-only and copies only its inputs", async () => {
    const historical = {
      ...snapshot("awaiting_confirmation", "live"),
      time_window: "3 days",
      outputs: { clarifying: { summary: "历史 Live 任务" } },
      evidence: [
        {
          id: "old-evidence",
          title: "Old evidence",
          summary: "Must not be copied",
          source_url: "https://example.com/old",
          stance: "context",
          reliability: "medium",
          is_demo: false,
        },
      ],
    };
    const api = fakeApi(historical);

    render(<App api={api as any} />);
    fireEvent.click(
      await screen.findByRole("button", { name: new RegExp(input.question) }),
    );

    expect(await screen.findByText(/历史任务来自真实联网模式/)).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "确认条件并继续研究" }),
    ).not.toBeInTheDocument();
    expect(api.confirmDecision).not.toHaveBeenCalled();

    fireEvent.click(
      screen.getByRole("button", { name: "复制条件并在当前模式新建" }),
    );

    expect(screen.getByLabelText("经营决策问题")).toHaveValue(input.question);
    expect(screen.getByLabelText("时间窗口")).toHaveValue("14 天");
    expect(screen.getByLabelText("时间窗口")).toHaveAttribute("readonly");
    expect(screen.getByLabelText("预算上限（元）")).toHaveValue(8000);
    fireEvent.click(screen.getByText("业务基线（可选）"));
    expect(screen.getByLabelText("月售后工单量")).toHaveValue(null);
    expect(screen.queryByText("Old evidence")).not.toBeInTheDocument();
  });

  it("offers a clean rebuild when a completed report contains a failed query", async () => {
    const api = fakeApi({
      ...snapshot("awaiting_review"),
      research_queries: [
        {
          id: 1,
          ordinal: 0,
          query: "risk",
          status: "failed",
          attempt_count: 1,
          last_error_code: "search_timeout",
          evidence_count: 0,
          created_at: "2026-09-11T00:00:00Z",
          started_at: "2026-09-11T00:00:01Z",
          finished_at: "2026-09-11T00:00:02Z",
        },
      ],
      memo: {
        summary: "需要补证据",
        support_score: 59,
        action_plan: [],
        facts: [],
        inferences: [],
        research_gaps: ["风险查询未完成"],
      },
    });

    render(<App api={api as any} />);
    fireEvent.click(
      await screen.findByRole("button", { name: new RegExp(input.question) }),
    );

    expect(await screen.findByText(/当前报告不会原地补查/)).toBeVisible();
    fireEvent.click(
      screen.getByRole("button", { name: "复制条件重新研究" }),
    );

    expect(screen.getByLabelText("经营决策问题")).toHaveValue(input.question);
    expect(screen.getByLabelText("时间窗口")).toHaveValue("14 天");
  });

  it("uses a fixed fourteen-day window for new decisions", async () => {
    render(<App api={fakeApi() as any} />);

    const window = await screen.findByLabelText("时间窗口");
    expect(window).toHaveValue("14 天");
    expect(window).toHaveAttribute("readonly");
    expect(screen.getByText("当前版本固定为 14 天验证计划。")).toBeVisible();
  });

  it("downloads the canonical markdown and releases the object URL", async () => {
    const api = fakeApi({
      ...snapshot("awaiting_review"),
      memo: {
        summary: "先做小范围试点",
        support_score: 59,
        action_plan: [],
        facts: [],
        inferences: [],
      },
    });
    const createObjectURL = vi.fn(() => "blob:decision-memo");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { ...URL, createObjectURL, revokeObjectURL });
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});
    render(<App api={api as any} />);
    fireEvent.click(
      await screen.findByRole("button", { name: new RegExp(input.question) }),
    );

    fireEvent.click(await screen.findByRole("button", { name: "下载 Markdown" }));

    await waitFor(() => expect(api.exportDecision).toHaveBeenCalledWith("decision-1"));
    expect(createObjectURL).toHaveBeenCalledOnce();
    expect(click).toHaveBeenCalledOnce();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:decision-memo");
  });
});

it("polls background snapshots and stops at the human confirmation gate", async () => {
  vi.useFakeTimers();
  const api = fakeApi(snapshot("draft"));
  api.runDecision.mockResolvedValueOnce(snapshot("clarifying"));
  api.getDecision.mockResolvedValue({
    ...snapshot("awaiting_confirmation"),
    outputs: { clarifying: { summary: "请核对约束" } },
  });
  render(<App api={api as any} />);
  await act(async () => {});
  fireEvent.change(screen.getByLabelText("经营决策问题"), {
    target: { value: input.question },
  });
  await act(async () =>
    fireEvent.click(screen.getByRole("button", { name: "创建并开始研究" })),
  );
  expect(
    screen.queryByRole("button", { name: "确认条件并继续研究" }),
  ).not.toBeInTheDocument();
  await act(async () => vi.advanceTimersByTimeAsync(750));
  expect(
    screen.getByRole("button", { name: "确认条件并继续研究" }),
  ).toBeVisible();
  api.getDecision.mockRejectedValue(new Error("不应继续轮询"));
  await act(async () => vi.advanceTimersByTimeAsync(3000));
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

it("offers resume after confirmation succeeds but starting research fails", async () => {
  const api = fakeApi(snapshot("awaiting_confirmation"));
  api.runDecision.mockRejectedValueOnce(new Error("网络中断"));
  render(<App api={api as any} />);
  fireEvent.click(
    await screen.findByRole("button", { name: new RegExp(input.question) }),
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "确认条件并继续研究" }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent("网络中断");
  fireEvent.click(screen.getByRole("button", { name: "继续研究" }));
  expect(await screen.findByRole("button", { name: "采纳建议" })).toBeVisible();
});

it("does not replace a newly created ledger row with a slow startup response", async () => {
  const api = fakeApi();
  let finish: (value: any) => void = () => {};
  api.listDecisions.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  render(<App api={api as any} />);
  fireEvent.change(screen.getByLabelText("经营决策问题"), {
    target: { value: input.question },
  });
  fireEvent.click(screen.getByRole("button", { name: "创建并开始研究" }));
  await screen.findByRole("button", { name: "确认条件并继续研究" });
  await screen.findByRole("button", { name: new RegExp(input.question) });
  await act(async () => finish([]));
  expect(
    screen.getByRole("button", { name: new RegExp(input.question) }),
  ).toBeVisible();
});
