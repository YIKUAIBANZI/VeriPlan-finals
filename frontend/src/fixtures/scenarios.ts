import type { BusinessBaseline, DecisionInput, Scenario, AssumptionCategory } from "../types";
export const emptyBaseline: BusinessBaseline = {
  monthly_ticket_volume: null, repetitive_ticket_rate: null, average_handle_minutes: null,
  loaded_hourly_cost: null, expected_ai_resolution_rate: null, review_minutes_per_ai_ticket: null,
  monthly_tool_cost: null, max_acceptable_error_rate: null,
};
export const scenarioLabels: Record<Scenario, string> = {
  ai_tool_pilot: "AI 售后客服", first_hire: "首位员工", big_order: "大额订单", marketing_spend: "营销投入", general: "其他决策",
};
export const categoryLabels: Record<AssumptionCategory, string> = {
  revenue: "收入", cost: "成本", volume: "数量", time: "耗时", conversion: "转化", other: "其他",
};
const base = { horizon_days: 90 as const, budget_limit: 30000, known_risks: ["需求不稳定"], assumptions: [{ label: "月新增收入", category: "revenue" as const, value: 20000, unit: "元/月", confidence: 70 }] };
export const scenarioExamples: Record<Scenario, DecisionInput> = {
  ai_tool_pilot: {
    ...base, scenario: "ai_tool_pilot", horizon_days: 14, budget_limit: 8000,
    question: "我们的售后消息越来越多，想用 AI 客服降低人力成本，但担心体验变差。两周内应该直接上线，还是先做小范围验证？",
    primary_goal: "降低重复咨询，同时守住客户满意度", known_risks: ["误答影响客户体验"],
    assumptions: [{ label: "每月节省工时", category: "time", value: 60, unit: "小时/月", confidence: 70 }],
    business_baseline: { monthly_ticket_volume: 1200, repetitive_ticket_rate: 60, average_handle_minutes: 8, loaded_hourly_cost: 45, expected_ai_resolution_rate: 70, review_minutes_per_ai_ticket: 1.5, monthly_tool_cost: 1200, max_acceptable_error_rate: 2 },
  },
  first_hire: { ...base, scenario: "first_hire", question: "要不要花三万元给工作室招第一个全职设计师？", primary_goal: "三个月内接单产能翻倍" },
  big_order: { ...base, scenario: "big_order", horizon_days: 30, question: "客户要求先垫资交付一笔大额订单，我是否应该接下？", primary_goal: "在不透支现金流的前提下完成交付", known_risks: ["客户拖欠尾款"] },
  marketing_spend: { ...base, scenario: "marketing_spend", horizon_days: 30, question: "是否应该把三万元预算投入一个尚未验证的新营销渠道？", primary_goal: "验证获客成本与回款周期" },
  general: { ...base, scenario: "general", question: "是否应该用三个月时间开发一个新的付费服务产品？", primary_goal: "验证真实付费需求" },
};
