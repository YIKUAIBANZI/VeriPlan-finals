import { useState } from "react";
import type { AssumptionInput, RetrospectiveInput, Scenario } from "../types";
import { scenarioLabels } from "../fixtures/scenarios";
import { AssumptionEditor } from "./AssumptionEditor";
type PastAssumption = AssumptionInput & { actual_value?: number };
export function RetrospectiveForm({ busy, onSubmit }: { busy: boolean; onSubmit: (input: RetrospectiveInput) => void }) {
  const [question, setQuestion] = useState("");
  const [scenario, setScenario] = useState<Scenario>("general");
  const [date, setDate] = useState("");
  const [assumptions, setAssumptions] = useState<PastAssumption[]>([]);
  const [note, setNote] = useState("");
  return <form onSubmit={e => {
    e.preventDefault();
    if (assumptions.length && assumptions.every(a => Number.isFinite(a.actual_value))) {
      onSubmit({ question, scenario, decision_date: date, assumptions: assumptions.map(a => ({ ...a, actual_value: a.actual_value! })), note });
    }
  }}>
    <fieldset disabled={busy} className="plain-fieldset">
      <legend>录入一个过去的决定</legend>
      <p>按当时的预测填写，并补上已知实际值。这是回溯样本，直接入账，不启动研究或审批。</p>
      <label htmlFor="past-question">过去的决策问题</label><textarea id="past-question" required minLength={12} maxLength={1000} value={question} onChange={e => setQuestion(e.target.value)} />
      <div className="form-grid"><label>过去的决策场景<select value={scenario} onChange={e => setScenario(e.target.value as Scenario)}>{Object.entries(scenarioLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label>决策日期<input type="date" required value={date} onChange={e => setDate(e.target.value)} /></label></div>
      <AssumptionEditor value={assumptions} onChange={setAssumptions} />
      {assumptions.map((a, i) => <label key={i}>{a.label || `假设 ${i + 1}`} · 实际值（{a.unit}）<input aria-label={`假设 ${i + 1} 实际值`} required type="number" step="any" value={Number.isFinite(a.actual_value) ? a.actual_value : ""} onChange={e => setAssumptions(assumptions.map((item, index) => index === i ? { ...item, actual_value: e.target.valueAsNumber } : item))} /></label>)}
      <label>回溯备注<textarea maxLength={1000} value={note} onChange={e => setNote(e.target.value)} /></label>
      <button className="primary" type="submit" disabled={!assumptions.length}>保存回溯记录</button>
    </fieldset>
  </form>;
}
