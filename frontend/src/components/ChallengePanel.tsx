import type { Decision } from "../types";
import { assumptionName } from "../assumptionName";
export function ChallengePanel({ decision }: { decision: Decision }) {
  const challenge = decision.outputs.challenging;
  if (!challenge) return null;
  return <section className="paper challenge-paper">
    <div className="section-heading"><h2>反方事前验尸</h2><span className="tag warn">先看可能错在哪里</span></div>
    {challenge.novel_objection_count !== undefined && <h3 className="novel-count">反方提出 {challenge.novel_objection_count} 条你没写过的风险</h3>}
    <p className="premortem">{challenge.premortem ?? challenge.objection ?? challenge.summary}</p>
    {challenge.calibration_warnings?.map((warning, index) => <aside className="calibration-warning" key={`${warning.category}-${index}`} aria-label="历史偏差警告">
      <h3>{warning.message}</h3>
      {warning.assumption_ids.map(id => <p key={id}>{assumptionName(decision, id)} 修正参考值：{warning.adjusted_reference[id]?.toLocaleString("zh-CN")} {decision.assumptions?.find(a => a.id === id)?.unit}</p>)}
      <strong>按你历史偏差修正的参考值，不是预测</strong>
    </aside>)}
    <div className="objections">
      {challenge.objections?.map(item => <article key={item.id} className={`objection-card severity-${item.severity}`}>
        <div className="objection-meta"><strong>{{ blocker: "阻断风险", major: "主要风险", minor: "次要风险" }[item.severity]}</strong><span>{item.overlaps_known_risk_index === null ? "🆕 你没想到" : `你已提到：${decision.known_risks?.[item.overlaps_known_risk_index] ?? `风险 ${item.overlaps_known_risk_index + 1}`}`}</span></div>
        <h4>{item.id} · {item.text}</h4>
        {!!item.targets_assumption_ids.length && <p>针对假设：{item.targets_assumption_ids.map(id => assumptionName(decision, id)).join("、")}</p>}
        <div className="citations">{item.evidence_ids.map(id => <a key={id} href={`#evidence-${id}`}>证据 {id}</a>)}</div>
      </article>)}
    </div>
    {!!challenge.hidden_assumptions?.length && <><h3>隐藏假设</h3><ul>{challenge.hidden_assumptions.map(text => <li key={text}>{text}</li>)}</ul></>}
  </section>;
}
