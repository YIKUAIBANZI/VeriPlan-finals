import type { CouncilRole, Decision, Stance } from "../types";
import { expertLabels } from "../types";
import { assumptionName } from "../assumptionName";
import { Citations } from "./Cite";
const roles: Record<CouncilRole, string> = { opportunity: "机会官", cfo: "财务官", risk: "风险官", expert: "专项专家" };
const stances: Record<Stance, string> = { support: "支持", oppose: "反对", conditional: "有条件支持" };
export function CouncilPanel({ decision }: { decision: Decision }) {
  const output = decision.outputs.analyzing;
  const running = decision.status === "analyzing" || (decision.status === "retrying" && decision.failure?.stage === "analyzing");
  if (decision.status === "retrospective" || (!running && !output?.members && !decision.events.some(e => e.stage.startsWith("council:")))) return null;
  // A retry invalidates completion events and aggregate output from the old attempt.
  const attemptStart = decision.events.map(e => e.stage === "analyzing" && e.status === "started").lastIndexOf(true);
  const events = decision.events.slice(Math.max(0, attemptStart));
  const planning = decision.outputs.planning;
  const expertKind = planning?.expert_kind ?? output?.members?.find(m => m.role === "expert")?.expert_kind;
  const hasExpert = Boolean(expertKind || events.some(e => e.stage === "council:expert") || (running && !output?.members));
  const visibleRoles = (Object.keys(roles) as CouncilRole[]).filter(role =>
    !running && output?.members ? output.members.some(m => m.role === role) : role !== "expert" || hasExpert);
  const allComplete = visibleRoles.every(role => [...events].reverse().find(e => e.stage === `council:${role}`)?.status === "completed");
  return <section className="card council-panel" aria-label="AI 决策委员会">
    <div className="section-heading"><h2>委员会</h2>{decision.mode === "demo" && <span className="demo-badge">Demo · 合成</span>}</div>
    {output?.disagreement?.is_split && (!running || allComplete) && <p className="council-split" role="status">委员会意见分裂</p>}
    <div className={`council-seats${visibleRoles.length === 3 ? " legacy-seats" : ""}`}>
      {visibleRoles.map(role => {
        const event = [...events].reverse().find(e => e.stage === `council:${role}`);
        const completed = event?.status === "completed";
        const member = (!running || completed) ? output?.members?.find(m => m.role === role) : undefined;
        // The frozen event summary carries an explicit stance before members is
        // published. Unknown wording stays neutral; never infer it from the headline.
        const eventLabel = completed ? event.summary.split("：")[1]?.split("——")[0] : undefined;
        const eventStance = (Object.keys(stances) as Stance[]).find(key => stances[key] === eventLabel);
        const stance = member?.stance ?? eventStance;
        const state = member || completed ? "completed" : decision.status === "failed" ? "failed" : "thinking";
        const title = role === "expert" ? `本题加派：${expertKind ? expertLabels[expertKind] : "专项"}专家` : roles[role];
        return <article key={role} aria-label={title} data-stance={stance} className={`council-seat ${state}`}>
          <h3>{title}</h3>
          {role === "expert" && <>
            {planning?.expert_reason && <p className="expert-reason">{planning.expert_reason}</p>}
            {planning?.expert_source === "scenario_default" && planning.expert_reason !== "按场景默认" && <span className="model-badge">按场景默认</span>}
          </>}
          {member?.model_label && <span className="model-badge">{member.model_label}</span>}
          {member?.fallback_from && <span className="fallback-badge">已切换备用模型</span>}
          <div aria-live="polite" aria-atomic="true">
            {member ? <div className="council-conclusion">
              <p className="stance" data-stance={member.stance}><i className="stance-dot" data-stance={member.stance} aria-hidden="true" />{stances[member.stance]}</p>
              <h4>{member.headline}</h4>
              <ul>{member.key_points.map(point => <li key={point}>{point}</li>)}</ul>
              <details className="reasoning"><summary>完整理由</summary><p>{member.reasoning}</p></details>
              <p className="member-meta">委员信心 {member.confidence}%{!!member.challenged_assumption_ids.length && <> · 质疑假设：{member.challenged_assumption_ids.map(id => assumptionName(decision, id)).join("、")}</>}</p>
              <Citations ids={member.evidence_ids} />
            </div> : completed ? <p className="council-conclusion">{event.summary}</p> : <p className="seat-status">{state === "failed" ? "审查中断" : "思考中"}</p>}
          </div>
        </article>;
      })}
    </div>
  </section>;
}
