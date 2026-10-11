import type { CouncilRole, Decision, Stance } from "../types";
import { assumptionName } from "../assumptionName";
const roles: Record<CouncilRole, string> = { opportunity: "机会官", cfo: "财务官", risk: "风险官" };
const stances: Record<Stance, string> = { support: "支持", oppose: "反对", conditional: "有条件支持" };
export function CouncilPanel({ decision }: { decision: Decision }) {
  const output = decision.outputs.analyzing;
  const running = decision.status === "analyzing" || (decision.status === "retrying" && decision.failure?.stage === "analyzing");
  if (decision.status === "retrospective" || (!running && !output?.members && !decision.events.some(e => e.stage.startsWith("council:")))) return null;
  // A retry invalidates completion events and aggregate output from the old attempt.
  const attemptStart = decision.events.map(e => e.stage === "analyzing" && e.status === "started").lastIndexOf(true);
  const events = decision.events.slice(Math.max(0, attemptStart));
  const allComplete = (Object.keys(roles) as CouncilRole[]).every(role => [...events].reverse().find(e => e.stage === `council:${role}`)?.status === "completed");
  return <section className="paper council-panel" aria-label="AI 决策委员会">
    <div className="section-heading"><h2>AI 决策委员会</h2>{decision.mode === "demo" && <span className="demo-badge">Demo · 合成</span>}</div>
    {output?.disagreement?.is_split && (!running || allComplete) && <p className="council-split" role="status">委员会意见分裂</p>}
    <div className="council-seats">
      {(Object.keys(roles) as CouncilRole[]).map(role => {
        const event = [...events].reverse().find(e => e.stage === `council:${role}`);
        const completed = event?.status === "completed";
        const member = (!running || completed) ? output?.members?.find(m => m.role === role) : undefined;
        // The frozen event summary carries an explicit stance before members is
        // published. Unknown wording stays neutral; never infer it from the headline.
        const eventLabel = completed ? event.summary.split("：")[1]?.split("——")[0] : undefined;
        const eventStance = (Object.keys(stances) as Stance[]).find(key => stances[key] === eventLabel);
        const stance = member?.stance ?? eventStance;
        const state = member || completed ? "completed" : decision.status === "failed" ? "failed" : "thinking";
        return <article key={role} aria-label={roles[role]} data-stance={stance} className={`council-seat ${state}`}>
          <h3>{roles[role]}</h3>
          <div aria-live="polite" aria-atomic="true">
            {member ? <div className="council-conclusion">
              <strong className="stance">{stances[member.stance]}</strong>
              <h4>{member.headline}</h4><p>{member.reasoning}</p>
              <ul>{member.key_points.map(point => <li key={point}>{point}</li>)}</ul>
              <p className="member-meta">委员信心 {member.confidence}%</p>
              {!!member.challenged_assumption_ids.length && <p>质疑假设：{member.challenged_assumption_ids.map(id => assumptionName(decision, id)).join("、")}</p>}
              <div className="citations">{member.evidence_ids.map(id => <a key={id} href={`#evidence-${id}`}>证据 {id}</a>)}</div>
            </div> : completed ? <p className="council-conclusion">{event.summary}</p> : <p className="seat-status">{state === "failed" ? "审查中断" : "思考中"}</p>}
          </div>
        </article>;
      })}
    </div>
  </section>;
}
