import type { DecisionApi } from "../api";
import type { Decision, OutcomeInput, Outcome } from "../types";
import { calibrationFixture, councilEvent, legacyDecision, members, outcomeDecision, splitDecision } from "./decisions";

// Explicit opt-in, in-memory development adapter. Never calls fetch or providers.
// Fixture arithmetic demonstrates UI states; backend calibration remains authoritative.
export function createFixtureApi(seed: Decision[] = [splitDecision, outcomeDecision, legacyDecision]): DecisionApi {
  const rows = new Map(seed.map(row => [row.id, structuredClone(row)]));
  const profile = structuredClone(calibrationFixture);
  let sequence = 0;
  const clone = <T,>(value: T): T => structuredClone(value);
  const get = (id: string) => {
    const row = rows.get(id);
    if (!row) throw new Error("未找到这个决策，请从账本重新选择。");
    return row;
  };
  const outcome = (row: Decision, input: OutcomeInput): Outcome => ({
    ...clone(input), recorded_at: new Date().toISOString(),
    actuals: input.actuals.map(a => {
      const predicted = row.assumptions?.find(item => item.id === a.assumption_id)?.value;
      if (predicted === undefined) throw new Error("假设 ID 不存在");
      return { ...a, error_pct: predicted === 0 ? null : Number(((a.actual_value - predicted) / Math.abs(predicted) * 100).toFixed(1)) };
    }),
  });
  return {
    health: async () => ({ mode: "demo", database: "fixture", live_available: false }),
    listDecisions: async () => clone([...rows.values()]),
    getDecision: async id => {
      const row = get(id);
      if (row.status === "analyzing") {
        const count = row.events.filter(e => e.stage.startsWith("council:") && e.status === "completed").length;
        if (count < 3) row.events.push(councilEvent(members[count].role, "completed"));
        else {
          row.status = "awaiting_review";
          row.outputs = clone(splitDecision.outputs);
          row.memo = clone(splitDecision.memo);
          // A mock must not cite A1 on a decision that has no assumptions.
          const ids = row.assumptions?.map(a => a.id) ?? [];
          for (const m of row.outputs.analyzing?.members ?? []) m.challenged_assumption_ids = ids.slice(0, 1);
          for (const o of row.outputs.challenging?.objections ?? []) {
            o.targets_assumption_ids = ids.slice(0, 1);
            if (o.overlaps_known_risk_index !== null && !row.known_risks?.length) o.overlaps_known_risk_index = null;
          }
          const challenge = row.outputs.challenging!;
          challenge.novel_objection_count = challenge.objections!.filter(o => o.overlaps_known_risk_index === null).length;
          const revenue = row.assumptions?.filter(a => a.category === "revenue") ?? [];
          challenge.calibration_warnings = revenue.length ? [{ ...calibrationFixtureWarning(), assumption_ids: revenue.map(a => a.id), adjusted_reference: Object.fromEntries(revenue.map(a => [a.id, a.value * .615])) }] : [];
          challenge.premortem = `假设 ${row.horizon_days} 天后失败：回款延迟，固定支出耗尽储备。`;
        }
      }
      return clone(row);
    },
    createDecision: async input => {
      const row: Decision = { ...clone(input), id: `fixture-new-${++sequence}`, mode: "demo", status: "draft", time_window: `${input.horizon_days} 天`, assumptions: input.assumptions.map((a, i) => ({ ...a, id: `A${i + 1}` })), is_retrospective: false, research_queries: [], evidence: clone(splitDecision.evidence), events: [], outputs: {}, memo: null, review_note: null, objection_labels: {}, outcomes: [] };
      rows.set(row.id, row); return clone(row);
    },
    runDecision: async id => {
      const row = get(id);
      if (row.status === "draft") { row.status = "awaiting_confirmation"; row.outputs.clarifying = { summary: "请确认周期、预算和数字假设。" }; }
      else if (row.status === "planning") { row.status = "analyzing"; row.events = members.map(m => councilEvent(m.role, "started")); }
      else throw new Error("当前状态不能运行");
      return clone(row);
    },
    confirmDecision: async id => { const row = get(id); if (row.status !== "awaiting_confirmation") throw new Error("当前状态不能确认"); row.status = "planning"; return clone(row); },
    retryDecision: async id => { const row = get(id); if (row.status !== "failed") throw new Error("当前状态不能重试"); row.status = "analyzing"; row.outputs = {}; row.events = []; return clone(row); },
    reviewDecision: async (id, action, note) => { const row = get(id); if (row.status !== "awaiting_review") throw new Error("当前状态不能审批"); row.status = action; row.review_note = note; return clone(row); },
    labelObjections: async (id, labels) => {
      const row = get(id);
      if (!["awaiting_review", "accepted", "revised", "deferred"].includes(row.status)) throw new Error("当前状态不能标注");
      if (Object.keys(labels).some(key => !row.outputs.challenging?.objections?.some(o => o.id === key))) throw new Error("风险 ID 不存在");
      row.objection_labels = { ...row.objection_labels, ...labels }; return clone(row);
    },
    saveOutcomes: async (id, input) => {
      const row = get(id);
      if (!["accepted", "revised", "deferred"].includes(row.status)) throw new Error("审批后才可回填");
      const saved = outcome(row, input);
      row.outcomes = [...(row.outcomes ?? []).filter(o => o.checkpoint !== input.checkpoint), saved]; return clone(row);
    },
    createRetrospective: async input => {
      const row: Decision = { id: `fixture-past-${++sequence}`, question: input.question, scenario: input.scenario, time_window: "回溯记录", budget_limit: 0, primary_goal: "复盘历史预测", assumptions: input.assumptions.map(({ actual_value: _actual, ...a }, i) => ({ ...a, id: `A${i + 1}` })), known_risks: [], mode: "demo", status: "retrospective", is_retrospective: true, research_queries: [], evidence: [], events: [], outputs: {}, memo: null, review_note: input.note, outcomes: [] };
      row.outcomes = [outcome(row, { checkpoint: "custom", note: `${input.decision_date} 决策。${input.note}`, actuals: input.assumptions.map((a, i) => ({ assumption_id: `A${i + 1}`, actual_value: a.actual_value })) })];
      rows.set(row.id, row);
      profile.samples.push(...row.assumptions!.map(a => ({ decision_id: row.id, assumption_id: a.id, category: a.category, source: "retrospective" as const })));
      return clone(row);
    },
    getCalibration: async () => clone(profile),
    exportDecision: async id => { const row = get(id); return `# ${row.question}\n\n> 本地合成 fixture\n\n${row.memo?.summary ?? "回溯记录"}\n\n${JSON.stringify({ recommendation: row.memo?.recommendation, outputs: row.outputs, objection_labels: row.objection_labels, outcomes: row.outcomes }, null, 2)}\n`; },
  };
}
function calibrationFixtureWarning() { return structuredClone(splitDecision.outputs.challenging!.calibration_warnings![0]); }
