import type { Decision, DecisionInput, Health, ReviewAction, ObjectionLabels, OutcomeInput, RetrospectiveInput, CalibrationProfile } from "./types";
async function fetchResponse(path: string, body?: unknown): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method: body === undefined ? "GET" : "POST",
      headers:
        body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(15000),
    });
  } catch {
    throw new Error("无法连接服务，请确认后端已启动后重试。");
  }
  if (!response.ok) {
    if (response.status === 409)
      throw new Error("任务状态已更新，请刷新任务后继续。");
    if (response.status === 404)
      throw new Error("未找到这个决策，请从账本重新选择。");
    if (response.status === 422)
      throw new Error("请检查必填字段、数字范围和关联的假设或风险。");
    throw new Error("服务暂时不可用，请稍后重试。");
  }
  return response;
}
async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetchResponse(path, body);
  return response.json();
}
export const api = {
  health: () => request<Health>("/health"),
  listDecisions: () => request<Decision[]>("/decisions"),
  getDecision: (id: string) =>
    request<Decision>(`/decisions/${encodeURIComponent(id)}`),
  createDecision: (input: DecisionInput) =>
    request<Decision>("/decisions", input),
  runDecision: (id: string) =>
    request<Decision>(`/decisions/${encodeURIComponent(id)}/run`, {}),
  confirmDecision: (id: string) =>
    request<Decision>(`/decisions/${encodeURIComponent(id)}/confirm`, {}),
  retryDecision: (id: string) =>
    request<Decision>(`/decisions/${encodeURIComponent(id)}/retry`, {}),
  reviewDecision: (id: string, action: ReviewAction, note: string) =>
    request<Decision>(`/decisions/${encodeURIComponent(id)}/review`, {
      action,
      note,
    }),
  labelObjections: (id: string, labels: ObjectionLabels) =>
    request<Decision>(`/decisions/${encodeURIComponent(id)}/objection-labels`, { labels }),
  saveOutcomes: (id: string, input: OutcomeInput) =>
    request<Decision>(`/decisions/${encodeURIComponent(id)}/outcomes`, input),
  // The server assigns A1…An in submission order and expects actuals separately.
  createRetrospective: (input: RetrospectiveInput) =>
    request<Decision>("/retrospectives", {
      question: input.question,
      scenario: input.scenario,
      decision_date: input.decision_date,
      assumptions: input.assumptions.map(({ actual_value: _actual, ...assumption }) => assumption),
      actuals: input.assumptions.map((item, index) => ({
        assumption_id: `A${index + 1}`,
        actual_value: item.actual_value,
      })),
      note: input.note,
    }),
  getCalibration: () => request<CalibrationProfile>("/calibration"),
  exportDecision: async (id: string) => {
    const response = await fetchResponse(
      `/decisions/${encodeURIComponent(id)}/export.md`,
    );
    return response.text();
  },
};
export type DecisionApi = typeof api;
