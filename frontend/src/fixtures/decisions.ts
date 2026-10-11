import type { Decision, MemberOpinion, CalibrationProfile } from "../types";
import { scenarioExamples, emptyBaseline } from "./scenarios";
export const members: MemberOpinion[] = [
  { role: "opportunity", stance: "support", headline: "新订单足以支持一次验证", reasoning: "优先验证增量需求。", key_points: ["先锁定客户意向"], challenged_assumption_ids: ["A1"], evidence_ids: ["3"], confidence: 65 },
  { role: "cfo", stance: "oppose", headline: "现金储备不足以覆盖回款延迟", reasoning: "收入不能等同于当期现金流。", key_points: ["先谈预付款"], challenged_assumption_ids: ["A1"], evidence_ids: [], confidence: 80 },
  { role: "risk", stance: "conditional", headline: "必须保留退出条件", reasoning: "产能和需求仍未验证。", key_points: ["分阶段签约"], challenged_assumption_ids: ["A1"], evidence_ids: [], confidence: 70 },
];
export function councilEvent(role: MemberOpinion["role"], status: "started" | "completed") {
  const member = members.find(m => m.role === role)!;
  return { stage: `council:${role}`, status, summary: status === "started" ? `${role} 开始审查` : `${{ opportunity: "机会官", cfo: "财务官", risk: "风险官" }[role]}：${{ support: "支持", oppose: "反对", conditional: "有条件支持" }[member.stance]}——${member.headline}`, created_at: "2026-10-11T10:00:00Z" };
}
export const splitDecision: Decision = {
  ...scenarioExamples.first_hire, id: "fixture-council", mode: "demo", status: "awaiting_review", time_window: "90 天",
  assumptions: [{ id: "A1", label: "月新增收入", category: "revenue", value: 20000, unit: "元/月", confidence: 70 }],
  known_risks: ["需求不稳定"], is_retrospective: false,
  evidence: [{ id: "3", title: "合成客户意向记录", summary: "三位意向客户尚未付款。", source_url: "https://demo.invalid/intents", stance: "context", reliability: "low", is_demo: true }],
  research_queries: [], events: members.map(m => councilEvent(m.role, "completed")),
  outputs: {
    analyzing: { summary: "机会与现金流判断出现分歧", members, disagreement: { stances: { opportunity: "support", cfo: "oppose", risk: "conditional" }, is_split: true } },
    challenging: { summary: "先解决现金缺口", premortem: "假设 90 天后失败：客户延迟付款，工资支出耗尽储备，工作室被迫中断交付。",
      objections: [
        { id: "O1", text: "回款周期与工资支付错配", severity: "blocker", targets_assumption_ids: ["A1"], overlaps_known_risk_index: null, evidence_ids: ["3"] },
        { id: "O2", text: "需求不稳定导致闲置产能", severity: "major", targets_assumption_ids: ["A1"], overlaps_known_risk_index: 0, evidence_ids: [] },
      ], hidden_assumptions: ["把意向收入视为现金到账"], novel_objection_count: 1,
      calibration_warnings: [{ category: "revenue", bias_pct: -38.5, sample_size: 3, assumption_ids: ["A1"], adjusted_reference: { A1: 12300 }, message: "你过去 3 次收入类预测平均高估 38.5%" }],
    },
    delivering: { summary: "先用短约验证", recommendation: "small_test_first", conditions: [{ objection_id: "O1", condition: "先取得预付款，覆盖工资支出" }] },
  },
  memo: { summary: "先签短约验证需求，再决定是否全职招聘", recommendation: "small_test_first", support_score: 59, facts: [], inferences: [], action_plan: [] },
  review_note: null, objection_labels: {}, outcomes: [],
};
export const outcomeDecision: Decision = { ...splitDecision, id: "fixture-outcome", status: "accepted", objection_labels: { O1: "adopted", O2: "already_known" }, outcomes: [{ checkpoint: "day_30", recorded_at: "2026-10-11T10:00:00Z", note: "实收", actuals: [{ assumption_id: "A1", actual_value: 12000, error_pct: -40 }] }] };
export const legacyDecision: Decision = {
  id: "fixture-legacy", question: "旧记录：我们是否应该试点 AI 售后客服？", time_window: "14 天", budget_limit: 8000, primary_goal: "降低重复咨询", business_baseline: emptyBaseline,
  mode: "demo", status: "accepted", research_queries: [], evidence: [], events: [], outputs: { challenging: { summary: "需人工复核", objection: "误答风险" } }, review_note: null,
  memo: { summary: "先做小范围试点", recommendation: "pilot_before_rollout", support_score: 59, facts: [], inferences: [], action_plan: [] },
};
export const calibrationFixture: CalibrationProfile = {
  mode: "demo", categories: [{ category: "revenue", n: 3, mean_bias_pct: -38.5, hit_rate: 0, mean_confidence: 70, overconfidence_gap: 70 }],
  samples: [1, 2, 3].map(n => ({ decision_id: `synthetic-${n}`, assumption_id: "A1", category: "revenue", source: "demo" })),
};
