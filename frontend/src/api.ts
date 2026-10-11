import type { Decision, DecisionInput, Health, ReviewAction } from "./types";
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
      throw new Error("请检查问题长度、预算和必填条件。");
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
  exportDecision: async (id: string) => {
    const response = await fetchResponse(
      `/decisions/${encodeURIComponent(id)}/export.md`,
    );
    return response.text();
  },
};
export type DecisionApi = typeof api;
