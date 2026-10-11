import { useEffect, useRef, useState } from "react";
import type { DecisionApi } from "../api";
import type { CalibrationProfile, Decision, RetrospectiveInput } from "../types";
import { categoryLabels } from "../fixtures/scenarios";
import { RetrospectiveForm } from "./RetrospectiveForm";
export function CalibrationPanel({ api, mode, onCreated, readOnlyReason }: { api: DecisionApi; mode?: "demo" | "live"; onCreated: (decision: Decision) => void; readOnlyReason?: string }) {
  const [profile, setProfile] = useState<CalibrationProfile | null>(null);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const [busy, setBusy] = useState(false);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => {
    let current = true;
    setProfile(null); setError("");
    api.getCalibration().then(next => { if (current) setProfile(next); }).catch(err => { if (current) setError(err.message); });
    return () => { current = false; };
  }, [api, reload, mode]);
  async function create(input: RetrospectiveInput) {
    setBusy(true); setError("");
    try {
      const next = await api.createRetrospective(input);
      if (alive.current) onCreated(next);
    } catch (err) { if (alive.current) setError((err as Error).message); }
    finally { if (alive.current) setBusy(false); }
  }
  const sameMode = profile && profile.mode === mode;
  return <section className="paper calibration-panel">
    <h2>我的偏差画像</h2>
    <p>把过去的预测与实际结果对照，供下次决策参考。命中指误差在 ±20% 以内；偏差为负表示实际低于预测。</p>
    {error && <div role="alert" className="error-banner">{error}<button onClick={() => setReload(n => n + 1)}>重试加载画像</button></div>}
    {!profile && !error && <p role="status">正在加载画像…</p>}
    {profile && !sameMode && <p role="alert">画像模式与当前应用不一致，请刷新后重试。</p>}
    {sameMode && <>
      {!profile.categories.length ? <p>还没有可计算的样本。先回填实际结果，或录入一个过去的决定。</p> : <div className="table-scroll"><table><caption>当前{mode === "demo" ? "演示" : "真实"}模式的偏差统计</caption><thead><tr><th>类别</th><th>样本</th><th>平均偏差</th><th>命中率</th><th>平均信心</th><th>信心落差</th></tr></thead><tbody>
        {profile.categories.map(row => <tr key={row.category}><th>{categoryLabels[row.category]}</th><td>{row.n}</td><td>{row.mean_bias_pct > 0 ? "+" : ""}{row.mean_bias_pct}%</td><td>{Number((row.hit_rate * 100).toFixed(1))}%</td><td>{row.mean_confidence}%</td><td>{row.overconfidence_gap} 个百分点</td></tr>)}
      </tbody></table></div>}
      <h3>样本来源</h3>
      <ul className="sample-sources">{profile.samples.map((sample, i) => <li key={`${sample.decision_id}-${sample.assumption_id}-${i}`}><span className={sample.source === "demo" ? "tag warn" : "tag"}>{{ live: "Live", demo: "合成", retrospective: "回溯" }[sample.source]}</span> {categoryLabels[sample.category]} · {sample.decision_id} / {sample.assumption_id}</li>)}</ul>
    </>}
    {readOnlyReason ? <p>{readOnlyReason}</p> : <details className="retrospective-entry"><summary>录入一个过去的决定</summary><RetrospectiveForm busy={busy} onSubmit={input => void create(input)} /></details>}
  </section>;
}
