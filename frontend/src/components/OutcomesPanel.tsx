import { useState } from "react";
import type { Checkpoint, Decision, OutcomeInput } from "../types";
const checkpointLabels: Record<Checkpoint, string> = { day_30: "30 天", day_90: "90 天", day_180: "180 天", custom: "自定义" };
export function OutcomesPanel({ decision, busy, onSave, readOnlyReason }: { decision: Decision; busy: boolean; onSave: (input: OutcomeInput) => void; readOnlyReason?: string }) {
  const [checkpoint, setCheckpoint] = useState<Checkpoint>("day_30");
  const [values, setValues] = useState<Record<string, string>>({});
  const [note, setNote] = useState("");
  const assumptions = decision.assumptions ?? [];
  const outcomes = decision.outcomes ?? [];
  const reviewed = ["accepted", "revised", "deferred"].includes(decision.status);
  if (!reviewed && decision.status !== "retrospective") return null;
  const actuals = assumptions.filter(a => values[a.id]?.trim() && Number.isFinite(Number(values[a.id]))).map(a => ({ assumption_id: a.id, actual_value: Number(values[a.id]) }));
  return <section className="paper outcomes-panel">
    <h2>回填实际结果</h2>
    {assumptions.length === 0 ? <p>这条记录没有数字假设，无法计算偏差。可从“我的偏差画像”录入一个过去的决定。</p> : <>
      <div className="table-scroll"><table><caption>当时的数字假设</caption><thead><tr><th>假设</th><th>预测值</th><th>信心</th></tr></thead><tbody>{assumptions.map(a => <tr key={a.id}><th>{a.id} · {a.label}</th><td>{a.value.toLocaleString("zh-CN")} {a.unit}</td><td>{a.confidence}%</td></tr>)}</tbody></table></div>
      {reviewed && !readOnlyReason && <form onSubmit={e => { e.preventDefault(); if (actuals.length) onSave({ checkpoint, actuals, note }); }}>
        <fieldset disabled={busy} className="plain-fieldset">
          <label htmlFor="checkpoint">回填节点</label><select id="checkpoint" value={checkpoint} onChange={e => {
            const next = e.target.value as Checkpoint;
            setCheckpoint(next);
            const stored = outcomes.find(o => o.checkpoint === next);
            setValues(Object.fromEntries(stored?.actuals.map(a => [a.assumption_id, String(a.actual_value)]) ?? []));
            setNote(stored?.note ?? "");
          }}>{Object.entries(checkpointLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>
          <p className="muted">同一节点会覆盖已有结果；留空的假设不作为零值提交。自定义节点请在备注中写明时间。</p>
          {assumptions.map(a => <label key={a.id}>{a.id} · {a.label}（{a.unit}）<input aria-label={`${a.id} 实际值`} type="number" step="any" value={values[a.id] ?? ""} onChange={e => setValues({ ...values, [a.id]: e.target.value })} /></label>)}
          <label htmlFor="outcome-note">结果备注</label><textarea id="outcome-note" maxLength={1000} value={note} onChange={e => setNote(e.target.value)} />
          <button className="primary" disabled={!actuals.length} type="submit">保存实际结果</button>
        </fieldset>
      </form>}
    </>}
    {readOnlyReason && <p>{readOnlyReason}</p>}
    {outcomes.map(outcome => <div className="outcome-record" key={outcome.checkpoint}>
      <h3>{checkpointLabels[outcome.checkpoint]}回填</h3><p>{outcome.note}</p>
      <time dateTime={outcome.recorded_at}>{new Date(outcome.recorded_at).toLocaleString("zh-CN")}</time>
      <div className="table-scroll"><table><thead><tr><th>假设</th><th>实际值</th><th>误差</th></tr></thead><tbody>{outcome.actuals.map(a => <tr key={a.assumption_id}><th>{a.assumption_id}</th><td>{a.actual_value.toLocaleString("zh-CN")}</td><td>{a.error_pct === null ? "不可计算" : `${a.error_pct > 0 ? "+" : ""}${a.error_pct}%`}</td></tr>)}</tbody></table></div>
    </div>)}
  </section>;
}
