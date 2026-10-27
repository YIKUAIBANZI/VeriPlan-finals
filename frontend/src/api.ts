import type { Decision, DecisionInput, Health, ReviewAction, ObjectionLabels, OutcomeInput, RetrospectiveInput, CalibrationProfile, User } from "./types";
// AuthGate listens for this and drops back to the sign-in page.
export const UNAUTHORIZED_EVENT = "veriplan:unauthorized";
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
    if (response.status === 401) {
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
      throw new Error("登录已过期，请重新登录。");
    }
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
// Auth endpoints surface the server's own message (wrong password, name taken…).
async function authRequest<T>(path: string, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/auth${path}`, {
      method: body === undefined ? "GET" : "POST",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(15000),
    });
  } catch {
    throw new Error("无法连接服务，请稍后重试。");
  }
  if (response.status === 204) return undefined as T;
  if (!response.ok) {
    const detail = await response.json().then(d => d?.detail, () => undefined);
    throw new AuthError(response.status, typeof detail === "string" ? detail : authFallback(response.status));
  }
  return response.json();
}
export class AuthError extends Error {
  constructor(readonly status: number, message: string) { super(message); }
}
function authFallback(status: number) {
  return ({ 401: "用户名或密码不正确。", 403: "邀请码不正确。", 409: "这个用户名已被注册。", 422: "请检查用户名和密码格式。", 429: "尝试次数过多，请 15 分钟后再试。" } as Record<number, string>)[status]
    ?? "服务暂时不可用，请稍后重试。";
}
export const authApi = {
  me: () => authRequest<{ user: User }>("/me").then(r => r.user),
  login: (username: string, password: string) =>
    authRequest<{ user: User }>("/login", { username, password }).then(r => r.user),
  register: (username: string, password: string, invite_code?: string) =>
    authRequest<{ user: User }>("/register", { username, password, ...(invite_code ? { invite_code } : {}) }).then(r => r.user),
  logout: () => authRequest<void>("/logout", {}),
  health: () => request<Health>("/health"),
};
export type AuthApi = typeof authApi;
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
