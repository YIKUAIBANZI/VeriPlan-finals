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
  | "retrying"
  | "retrospective";
export type DecisionStatus = Status;
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
export type Scenario = "ai_tool_pilot" | "first_hire" | "big_order" | "marketing_spend" | "general";
export type HorizonDays = 7 | 14 | 30 | 90 | 180 | 365;
export type AssumptionCategory = "revenue" | "cost" | "volume" | "time" | "conversion" | "other";
export interface AssumptionInput {
  label: string;
  category: AssumptionCategory;
  value: number;
  unit: string;
  confidence: number;
}
export interface Assumption extends AssumptionInput { id: string }
export interface DecisionInput {
  scenario: Scenario;
  question: string;
  horizon_days: HorizonDays;
  budget_limit: number;
  primary_goal: string;
  known_risks: string[];
  assumptions: AssumptionInput[];
  business_baseline?: BusinessBaseline;
}
export type CouncilRole = "opportunity" | "cfo" | "risk" | "expert";
export type ExpertKind = "legal_compliance" | "customer" | "operations" | "platform_rules" | "personal_longterm";
export const expertLabels: Record<ExpertKind, string> = {
  legal_compliance: "法务合规", customer: "客户视角", operations: "运营产能",
  platform_rules: "平台规则", personal_longterm: "个人长期发展",
};
export type Stance = "support" | "oppose" | "conditional";
export interface MemberOpinion {
  role: CouncilRole;
  expert_kind?: ExpertKind | null;
  model_label?: string | null;
  fallback_from?: string | null;
  stance: Stance;
  headline: string;
  reasoning: string;
  key_points: string[];
  challenged_assumption_ids: string[];
  evidence_ids: string[];
  confidence: number;
}
export interface Objection {
  id: string;
  text: string;
  severity: "blocker" | "major" | "minor";
  targets_assumption_ids: string[];
  overlaps_known_risk_index: number | null;
  evidence_ids: string[];
}
export type ObjectionLabel = "adopted" | "already_known" | "disagree";
export type ObjectionLabels = Record<string, ObjectionLabel>;
export interface CalibrationWarning {
  category: AssumptionCategory;
  bias_pct: number;
  sample_size: number;
  assumption_ids: string[];
  adjusted_reference: Record<string, number>;
  message: string;
}
export type Checkpoint = "day_30" | "day_90" | "day_180" | "custom";
export interface OutcomeInput {
  checkpoint: Checkpoint;
  actuals: { assumption_id: string; actual_value: number }[];
  note: string;
}
export interface Outcome extends Omit<OutcomeInput, "actuals"> {
  recorded_at: string;
  actuals: { assumption_id: string; actual_value: number; error_pct: number | null }[];
}
// The spec describes these two payloads in prose; integration assumptions are
// isolated here and recorded in docs/finals-frontend-notes.md.
export interface RetrospectiveInput {
  question: string;
  scenario: Scenario;
  decision_date: string;
  assumptions: (AssumptionInput & { actual_value: number })[];
  note: string;
}
export interface CalibrationProfile {
  mode: "demo" | "live";
  categories: {
    category: AssumptionCategory;
    n: number;
    mean_bias_pct: number;
    hit_rate: number;
    mean_confidence: number;
    overconfidence_gap: number;
  }[];
  samples: {
    decision_id: string;
    assumption_id: string;
    category: AssumptionCategory;
    source: "live" | "demo" | "retrospective";
  }[];
}
export type Recommendation = "go" | "go_with_conditions" | "small_test_first" | "defer" | "no_go" | "pilot_before_rollout" | "do_not_pilot";
export interface DeliveryCondition { objection_id: string; condition: string }
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
  recommendation?: Recommendation;
  conditions?: DeliveryCondition[];
  support_score: number;
  score_explanation?: string;
  facts: Claim[];
  inferences: Claim[];
  objections?: string[];
  action_plan: Action[];
  research_gaps?: string[];
}
export interface StageOutput {
  expert_kind?: ExpertKind;
  expert_reason?: string;
  expert_source?: "model" | "scenario_default";
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
  members?: MemberOpinion[];
  disagreement?: { stances: Partial<Record<CouncilRole, Stance>>; is_split: boolean };
  premortem?: string;
  objections?: Objection[];
  novel_objection_count?: number;
  calibration_warnings?: CalibrationWarning[];
  recommendation?: Recommendation;
  conditions?: DeliveryCondition[];
  objection?: string;
  hidden_assumptions?: string[];
}
export interface Decision extends Omit<DecisionInput, "scenario" | "horizon_days" | "known_risks" | "assumptions"> {
  // Absent on pre-finals snapshots. New create requests always carry these.
  scenario?: Scenario;
  horizon_days?: HorizonDays;
  time_window: string;
  known_risks?: string[];
  assumptions?: Assumption[];
  is_retrospective?: boolean;
  objection_labels?: ObjectionLabels;
  outcomes?: Outcome[];
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
  baseline_analysis?: BaselineAnalysis;
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
  registration_requires_invite?: boolean;
}
export interface User {
  id: number;
  username: string;
  created_at: string;
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
  retrospective: "回溯记录",
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

export const recommendationLabels: Record<Recommendation, string> = {
  go: "可以推进", go_with_conditions: "满足条件后推进", small_test_first: "先做小规模验证",
  defer: "暂缓决定", no_go: "不建议推进", pilot_before_rollout: "先试点再推广", do_not_pilot: "不建议试点",
};
