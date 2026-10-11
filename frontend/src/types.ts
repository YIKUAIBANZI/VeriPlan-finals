export type Status =
  | "draft"
  | "clarifying"
  | "awaiting_confirmation"
  | "planning"
  | "researching"
  | "analyzing"
  | "challenging"
  | "delivering"
  | "awaiting_review"
  | "accepted"
  | "revised"
  | "deferred"
  | "failed"
  | "retrying";
export type ReviewAction = "accepted" | "revised" | "deferred";
export interface BusinessBaseline {
  monthly_ticket_volume: number | null;
  repetitive_ticket_rate: number | null;
  average_handle_minutes: number | null;
  loaded_hourly_cost: number | null;
  expected_ai_resolution_rate: number | null;
  review_minutes_per_ai_ticket: number | null;
  monthly_tool_cost: number | null;
  max_acceptable_error_rate: number | null;
}
export interface BaselineAnalysis {
  known_field_count: number;
  total_field_count: number;
  is_calculable: boolean;
  automatable_ticket_volume: number | null;
  monthly_hours_saved: number | null;
  estimated_monthly_net_savings: number | null;
  collection_tasks: string[];
  disclaimer: string;
}
export interface DecisionInput {
  question: string;
  time_window: string;
  budget_limit: number;
  primary_goal: string;
  business_baseline: BusinessBaseline;
}
export interface Evidence {
  id?: string;
  research_query_id?: number | null;
  title: string;
  summary: string;
  source_url: string;
  stance: "supports" | "opposes" | "context";
  reliability: "high" | "medium" | "low";
  is_demo: boolean;
}
export interface ResearchQuery {
  id: number;
  ordinal: number;
  query: string;
  status: "pending" | "running" | "succeeded" | "failed";
  attempt_count: number;
  last_error_code: string | null;
  evidence_count: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}
export interface Claim {
  text: string;
  evidence_ids: string[];
}
export interface Action {
  days: string;
  action: string;
  owner: string;
  metric: string;
  stop_condition: string;
  budget_limit?: number;
}
export interface Memo {
  summary: string;
  recommendation?: string;
  support_score: number;
  score_explanation?: string;
  facts: Claim[];
  inferences: Claim[];
  objections?: string[];
  action_plan: Action[];
  research_gaps?: string[];
}
export interface StageOutput {
  summary: string;
  assumptions?: string[];
  questions?: string[];
  research_questions?: string[];
  research_gaps?: string[];
  queries?: string[];
  analyses?: {
    perspective: string;
    conclusion: string;
    evidence_ids: string[];
  }[];
  objection?: string;
  hidden_assumptions?: string[];
}
export interface Decision extends DecisionInput {
  id: string;
  mode: "demo" | "live";
  status: Status;
  research_queries: ResearchQuery[];
  evidence: Evidence[];
  events: {
    stage: string;
    status: string;
    summary: string;
    created_at: string;
  }[];
  outputs: Record<string, StageOutput>;
  memo: Memo | null;
  review_note: string | null;
  failure?: { stage: string; code: string; message: string } | null;
  baseline_analysis: BaselineAnalysis;
}
export interface Health {
  mode: "demo" | "live";
  database: string;
  status?: string;
  live_workflow_enabled?: boolean;
  live_model_configured?: boolean;
  live_model_adapter_available?: boolean;
  live_search_configured?: boolean;
  live_search_adapter_available?: boolean;
  live_search_available?: boolean;
  live_available: boolean;
}
export const statusLabels: Record<Status, string> = {
  draft: "待开始",
  clarifying: "正在澄清",
  awaiting_confirmation: "待确认条件",
  planning: "研究规划中",
  researching: "正在取证",
  analyzing: "多方分析中",
  challenging: "反方质询中",
  delivering: "正在交付",
  awaiting_review: "待人工审批",
  accepted: "已采纳",
  revised: "已记录修改意见",
  deferred: "已暂缓",
  failed: "执行中断",
  retrying: "正在重试",
};
export const activeStatuses = new Set<Status>([
  "clarifying",
  "planning",
  "researching",
  "analyzing",
  "challenging",
  "delivering",
  "retrying",
]);
