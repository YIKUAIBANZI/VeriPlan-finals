import { useEffect, useRef, useState } from "react";
import { api as defaultApi, type DecisionApi } from "./api";
import {
  activeStatuses,
  statusLabels,
  type Decision,
  type DecisionInput,
  type Health,
  type ReviewAction,
} from "./types";
import { CalibrationPanel } from "./components/CalibrationPanel";
import { OutcomesPanel } from "./components/OutcomesPanel";
import { CouncilPanel } from "./components/CouncilPanel";
import { ChallengePanel } from "./components/ChallengePanel";
import { DecisionForm } from "./components/DecisionForm";
import { WorkflowTimeline, EventLog } from "./components/WorkflowTimeline";
import { EvidencePanel } from "./components/EvidencePanel";
import { DecisionResult } from "./components/DecisionResult";
import { Ledger } from "./components/Ledger";
import { ResearchQueries } from "./components/ResearchQueries";
import { BusinessBaselinePanel } from "./components/BusinessBaseline";
import "./styles.css";

export function App({ api = defaultApi }: { api?: DecisionApi }) {
  const [page, setPage] = useState<"decision" | "calibration">("decision");
  const [decision, setDecision] = useState<Decision | null>(null);
  const [items, setItems] = useState<Decision[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [initial, setInitial] = useState<DecisionInput | undefined>();
  const [formVersion, setFormVersion] = useState(0);
  const epoch = useRef(0);
  const listVersion = useRef(0);
  const refreshLedger = async () => {
    const version = ++listVersion.current;
    const next = await api.listDecisions();
    if (version === listVersion.current) setItems(next);
  };
  useEffect(() => {
    let alive = true;
    const version = ++listVersion.current;
    Promise.all([api.health(), api.listDecisions()])
      .then(([h, rows]) => {
        if (alive) {
          setHealth(h);
          if (version === listVersion.current) setItems(rows);
        }
      })
      .catch((err) => {
        if (alive && version === listVersion.current) setError(err.message);
      });
    return () => {
      alive = false;
      epoch.current++;
      listVersion.current++;
    };
  }, [api]);
  useEffect(() => {
    if (
      !decision ||
      !activeStatuses.has(decision.status) ||
      busy ||
      waitingToRun(decision)
    )
      return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const generation = epoch.current;
    const poll = async () => {
      try {
        const next = await api.getDecision(decision.id);
        if (!alive || epoch.current !== generation) return;
        setDecision(next);
        if (activeStatuses.has(next.status)) timer = setTimeout(poll, 750);
        else await refreshLedger();
      } catch (err) {
        if (alive && epoch.current === generation)
          setError((err as Error).message);
      }
    };
    timer = setTimeout(poll, 750);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [api, decision?.id, decision?.status, busy]);

  function newDecision(value?: DecisionInput) {
    setPage("decision");
    epoch.current++;
    setDecision(null);
    setBusy(false);
    setError("");
    setInitial(value);
    setFormVersion((v) => v + 1);
  }
  async function operate(work: (generation: number) => Promise<Decision>) {
    const generation = ++epoch.current;
    setBusy(true);
    setError("");
    try {
      const next = await work(generation);
      if (epoch.current === generation) {
        setDecision(next);
        await refreshLedger();
      }
    } catch (err) {
      if (epoch.current === generation) setError((err as Error).message);
    } finally {
      if (epoch.current === generation) setBusy(false);
    }
  }
  function create(input: DecisionInput) {
    void operate(async (generation) => {
      const created = await api.createDecision(input);
      if (epoch.current !== generation) return created;
      setDecision(created);
      return api.runDecision(created.id);
    });
  }
  function confirm() {
    if (!decision) return;
    void operate(async (generation) => {
      const confirmed = await api.confirmDecision(decision.id);
      if (epoch.current !== generation) return confirmed;
      setDecision(confirmed);
      return api.runDecision(decision.id);
    });
  }
  function review(action: ReviewAction, note: string) {
    if (decision)
      void operate(() => api.reviewDecision(decision.id, action, note));
  }
  async function exportMarkdown() {
    if (!decision) return;
    setExporting(true);
    setError("");
    try {
      const markdown = await api.exportDecision(decision.id);
      const url = URL.createObjectURL(
        new Blob([markdown], { type: "text/markdown;charset=utf-8" }),
      );
      try {
        const link = document.createElement("a");
        link.href = url;
        link.download = `veriplan-${decision.id}.md`;
        document.body.append(link);
        link.click();
        link.remove();
      } finally {
        URL.revokeObjectURL(url);
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setExporting(false);
    }
  }
  function waitingToRun(item: Decision) {
    return (
      item.status === "planning" &&
      !item.events.some(
        (event) =>
          event.stage === "planning" &&
          ["queued", "started"].includes(event.status),
      )
    );
  }
  const finished =
    decision &&
    ["awaiting_review", "accepted", "revised", "deferred"].includes(
      decision.status,
    );
  const contentMode = decision?.mode ?? health?.mode ?? "demo";
  const liveUnlocked = health?.mode === "live" && health.live_available;
  const writesLocked = health?.mode === "live" && !liveUnlocked;
  const modeMismatch = Boolean(
    decision && health && decision.mode !== health.mode,
  );
  const finishedWithFailedQuery = Boolean(
    decision &&
      finished &&
      decision.research_queries.some((query) => query.status === "failed"),
  );
  const pendingAction = decision && !modeMismatch ? (
    decision.status === "awaiting_confirmation" ? null
      : waitingToRun(decision) ? { title: "条件已确认，研究尚未启动", body: "已保存你的确认，可以继续研究。", label: "继续研究", run: () => api.runDecision(decision.id) }
      : decision.status === "draft" ? { title: "决策已保存", body: "", label: "开始研究", run: () => api.runDecision(decision.id) }
      : decision.status === "failed" ? { title: "执行中断，已保留完成的阶段", body: decision.failure?.message ?? "请重试以继续这个决策。", label: "重试失败阶段", run: () => api.retryDecision(decision.id), warn: true }
      : null
  ) : null;
  return (
    <div className="app-shell">
      <a className="skip-link" href="#workspace">
        跳至工作台
      </a>
      <Ledger
        items={items}
        selected={decision?.id}
        onSelect={(id) => { setPage("decision"); void operate(() => api.getDecision(id)); }}
        onNew={() => newDecision()}
        calibrationSelected={page === "calibration"}
        onCalibration={() => { newDecision(); setPage("calibration"); }}
      />
      <div className="main-shell">
        <header className="topbar">
          <span className="topbar-title">{page === "calibration" ? "偏差画像" : decision ? "决策工作台" : "新建决策"}</span>
          <span className="mode-badge" data-live={liveUnlocked || undefined}>
            <i aria-hidden="true" />
            {liveUnlocked
              ? "真实联网模式"
              : health?.mode === "live"
                ? "真实模式未解锁"
                : "演示数据模式"}
          </span>
        </header>
        <main id="workspace">
          {error && (
            <div className="error-banner" role="alert">
              <span>{error}</span>
              <button
                onClick={() =>
                  decision
                    ? void operate(() => api.getDecision(decision.id))
                    : void Promise.all([
                        api.health().then(setHealth),
                        refreshLedger(),
                      ])
                        .then(() => setError(""))
                        .catch((err) => setError(err.message))
                }
              >
                刷新{decision ? "任务" : "连接"}
              </button>
            </div>
          )}
          {page === "calibration" ? (
            <CalibrationPanel api={api} mode={health?.mode} readOnlyReason={!health ? "正在确认运行模式…" : health.mode === "live" && !liveUnlocked ? "真实模式未解锁，暂不能录入。" : undefined}
              onCreated={created => { newDecision(); setDecision(created); void refreshLedger().catch(err => setError(err.message)); }} />
          ) : !decision ? (
            <>
              <DecisionForm
                key={formVersion}
                initial={initial}
                busy={busy}
                disabled={writesLocked}
                onSubmit={create}
              />
              <p className="demo-notice">
                {contentMode === "live"
                  ? "真实联网模式：会调用模型和搜索服务，联网来源摘要仍需人工核验。"
                  : "演示模式：使用合成证据与预置流程，不代表实时调研或真实经营结论。"}
              </p>
            </>
          ) : (
            <>
              <div className="decision-head">
                <div className="decision-eyebrow">
                  <span
                    className={`status-pill ${decision.status === "failed" ? "warn" : ""}`}
                    role="status"
                  >
                    {statusLabels[decision.status]}
                  </span>
                  <span>{decision.mode === "live" ? "真实联网决策 · 联网来源摘要仍需人工核验" : "演示数据 · 合成证据，不代表真实经营结论"}</span>
                </div>
                <h1 className="decision-question">{decision.question}</h1>
                {decision.status !== "retrospective" && <dl className="constraints">
                  <div><dt>决策窗口</dt><dd>{decision.time_window}</dd></div>
                  <div><dt>预算上限</dt><dd>¥{decision.budget_limit.toLocaleString("zh-CN")}</dd></div>
                  <div><dt>首要目标</dt><dd>{decision.primary_goal}</dd></div>
                </dl>}
              </div>
              {decision.status !== "retrospective" && <WorkflowTimeline decision={decision} />}
              {modeMismatch && health && (
                <section className="card notice-card">
                  <span className="tag warn">历史任务只读</span>
                  <h2>运行模式不同，不能继续修改</h2>
                  <p>
                    历史任务来自{modeLabel(decision.mode)}，当前应用是
                    {modeLabel(health.mode)}。为避免混用供应商和证据链，当前只能查看。
                  </p>
                  <button
                    className="primary"
                    onClick={() => newDecision(copyDecisionInput(decision))}
                  >
                    复制条件并在当前模式新建
                  </button>
                </section>
              )}
              <div className="workspace-grid">
                <div className="work-content">
                  {decision.status === "awaiting_confirmation" && (
                    <section className="card clarification">
                      <span className="tag">需要你的确认</span>
                      <h2>先对齐条件，再开始研究</h2>
                      <p>{decision.outputs.clarifying?.summary}</p>
                      {Boolean(decision.outputs.clarifying?.assumptions?.length) && (
                        <>
                          <h3>待确认的假设</h3>
                          <ul>
                            {decision.outputs.clarifying.assumptions?.map((s) => <li key={s}>{s}</li>)}
                          </ul>
                        </>
                      )}
                      {Boolean(decision.outputs.clarifying?.questions?.length) && (
                        <>
                          <h3>仍待验证的信息</h3>
                          <ul>
                            {decision.outputs.clarifying.questions?.map((s) => <li key={s}>{s}</li>)}
                          </ul>
                        </>
                      )}
                      {!modeMismatch && (
                        <div className="review-buttons">
                          <button className="primary" disabled={busy || writesLocked} onClick={confirm}>
                            确认条件并继续研究
                          </button>
                          <button disabled={busy || writesLocked} onClick={() => newDecision(copyDecisionInput(decision))}>
                            调整条件并新建
                          </button>
                        </div>
                      )}
                    </section>
                  )}
                  {pendingAction && (
                    <section className={`card notice-card${pendingAction.warn ? " warn" : ""}`}>
                      <h2>{pendingAction.title}</h2>
                      {pendingAction.body && <p>{pendingAction.body}</p>}
                      <button
                        className="primary"
                        disabled={busy || writesLocked}
                        onClick={() => void operate(pendingAction.run)}
                      >
                        {pendingAction.label}
                      </button>
                    </section>
                  )}
                  {activeStatuses.has(decision.status) && !waitingToRun(decision) && (
                    <div className="running-note" role="status">
                      <span className="pulse" />
                      {busy ? "正在提交操作…" : `${statusLabels[decision.status]}，阶段结果将自动更新。`}
                    </div>
                  )}
                  <CouncilPanel decision={decision} />
                  {decision.business_baseline && decision.baseline_analysis && (!decision.scenario || decision.scenario === "ai_tool_pilot") && <BusinessBaselinePanel
                    baseline={decision.business_baseline}
                    analysis={decision.baseline_analysis}
                  />}
                  {decision.outputs.analyzing?.analyses && (
                    <section className="card">
                      <h2>三个视角，分别审查</h2>
                      <div className="analyses">
                        {decision.outputs.analyzing.analyses.map((item) => (
                          <article key={item.perspective}>
                            <h3>{{ growth: "增长机会", cost: "成本投入", risk: "体验风险" }[item.perspective] ?? item.perspective}</h3>
                            <p>{item.conclusion}</p>
                          </article>
                        ))}
                      </div>
                    </section>
                  )}
                  {!finished && decision.status !== "retrospective" && <ChallengePanel decision={decision} />}
                  {finishedWithFailedQuery && (
                    <section className="card notice-card warn">
                      <h2>本次研究存在未完成查询</h2>
                      <p>当前报告不会原地补查；补查会使分析、Memo 和审批版本失效。请复制原条件重新研究。</p>
                      <button className="primary" onClick={() => newDecision(copyDecisionInput(decision))}>
                        复制条件重新研究
                      </button>
                    </section>
                  )}
                  {finished && (
                    <DecisionResult
                      key={decision.id}
                      decision={decision}
                      onReview={review}
                      onLabel={labels => { if (!modeMismatch && !writesLocked) void operate(() => api.labelObjections(decision.id, labels)); }}
                      onExportMarkdown={() => void exportMarkdown()}
                      onPrint={() => window.print()}
                      busy={busy || exporting}
                      writeDisabled={writesLocked}
                      readOnlyReason={modeMismatch ? "历史任务来自另一运行模式，当前只读。" : undefined}
                    />
                  )}
                  <OutcomesPanel key={`outcomes-${decision.id}`} decision={decision} busy={busy || writesLocked}
                    readOnlyReason={modeMismatch ? "历史任务来自另一运行模式，当前只读。" : undefined}
                    onSave={input => { if (!modeMismatch && !writesLocked) void operate(() => api.saveOutcomes(decision.id, input)); }} />
                  {(decision.outputs.planning || decision.research_queries.length > 0) && (
                    <details className="card process" open={!finished}>
                      <summary>
                        <span>研究过程</span>
                        <small>{decision.research_queries.length} 条检索 · {decision.evidence.length} 条证据</small>
                      </summary>
                      {decision.outputs.planning && (
                        <div className="research-plan">
                          <h3>研究计划</h3>
                          <p>{decision.outputs.planning.summary}</p>
                          <ul>
                            {(decision.outputs.planning.research_questions ?? decision.outputs.planning.queries ?? []).map((query) => (
                              <li key={query}>{query}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      <ResearchQueries queries={decision.research_queries} />
                    </details>
                  )}
                  {decision.status !== "retrospective" && <EventLog decision={decision} />}
                </div>
                {decision.status !== "retrospective" && <EvidencePanel evidence={decision.evidence} />}
              </div>
            </>
          )}
          <footer className="page-footer">
            <span>证策 VeriPlan</span><span>证据 · 质询 · 人工决策</span>
          </footer>
        </main>
      </div>
    </div>
  );
}

function copyDecisionInput(decision: Decision): DecisionInput {
  return {
    question: decision.question,
    scenario: decision.scenario ?? "ai_tool_pilot",
    horizon_days: decision.horizon_days ?? 14,
    known_risks: [...(decision.known_risks ?? [])],
    assumptions: (decision.assumptions ?? []).map(({ id: _id, ...input }) => input),
    budget_limit: decision.budget_limit,
    primary_goal: decision.primary_goal,
    ...(decision.business_baseline ? { business_baseline: { ...decision.business_baseline } } : {}),
  };
}

function modeLabel(mode: Decision["mode"]) {
  return mode === "live" ? "真实联网模式" : "演示数据模式";
}
