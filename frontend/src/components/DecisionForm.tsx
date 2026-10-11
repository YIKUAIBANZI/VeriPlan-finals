import { useState } from "react";
import type { BusinessBaseline, DecisionInput } from "../types";
import { emptyBaseline, scenarioExamples, scenarioLabels } from "../fixtures/scenarios";
import { AssumptionEditor } from "./AssumptionEditor";
import type { HorizonDays, Scenario } from "../types";
const example = scenarioExamples.ai_tool_pilot;

const baselineGroups: {
  title: string;
  fields: {
    key: keyof BusinessBaseline;
    label: string;
    suffix: string;
    max: number;
    step: number;
  }[];
}[] = [
  {
    title: "规模",
    fields: [
      { key: "monthly_ticket_volume", label: "月售后工单量", suffix: "条", max: 10000000, step: 1 },
      { key: "repetitive_ticket_rate", label: "重复咨询占比", suffix: "%", max: 100, step: 0.1 },
    ],
  },
  {
    title: "当前成本",
    fields: [
      { key: "average_handle_minutes", label: "平均处理时长", suffix: "分钟", max: 1440, step: 0.1 },
      { key: "loaded_hourly_cost", label: "综合人力时薪", suffix: "元", max: 1000000, step: 0.01 },
    ],
  },
  {
    title: "AI 试点假设",
    fields: [
      { key: "expected_ai_resolution_rate", label: "预计 AI 独立解决率", suffix: "%", max: 100, step: 0.1 },
      { key: "review_minutes_per_ai_ticket", label: "单条 AI 工单复核时长", suffix: "分钟", max: 1440, step: 0.1 },
    ],
  },
  {
    title: "成本与风险门槛",
    fields: [
      { key: "monthly_tool_cost", label: "预计月工具成本", suffix: "元", max: 10000000, step: 0.01 },
      { key: "max_acceptable_error_rate", label: "可接受最大误答率", suffix: "%", max: 100, step: 0.1 },
    ],
  },
];
export function DecisionForm({
  busy,
  disabled = false,
  onSubmit,
  initial,
}: {
  busy: boolean;
  disabled?: boolean;
  onSubmit: (input: DecisionInput) => void;
  initial?: DecisionInput;
}) {
  const [value, setValue] = useState<DecisionInput>(initial ?? {
    ...example, question: "", known_risks: [], assumptions: [], business_baseline: { ...emptyBaseline },
  });
  return (
    <section className="paper create-paper">
      <div className="form-intro">
        <span className="section-number">开始一个有依据的决定</span>
        <h2>这次，你在犹豫什么？</h2>
        <p>
          把问题和边界说清楚。先确认决策条件，再查看证据、反方意见和验证计划。
        </p>
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (busy || disabled) return;
          const { business_baseline, ...input } = value;
          onSubmit({ ...input, known_risks: value.known_risks.map(risk => risk.trim()).filter(Boolean),
            ...(value.scenario === "ai_tool_pilot" ? { business_baseline: business_baseline ?? { ...emptyBaseline } } : {}),
          });
        }}
      >
        <div className="scenario-cards" aria-label="决策场景">
          {(Object.keys(scenarioLabels) as Scenario[]).map(scenario => <article key={scenario} data-selected={value.scenario === scenario}>
            <button type="button" aria-pressed={value.scenario === scenario} onClick={() => {
              const { business_baseline: _baseline, ...rest } = value;
              setValue({ ...rest, scenario, ...(scenario === "ai_tool_pilot" ? { business_baseline: { ...emptyBaseline } } : {}) });
            }}>{scenarioLabels[scenario]}</button>
            <button type="button" className="text-button" onClick={() => setValue(structuredClone(scenarioExamples[scenario]))}>填入 {scenarioLabels[scenario]}示例</button>
          </article>)}
        </div>
        <p className="synthetic-note">示例均为合成演示数字，请替换为你的实际假设。</p>
        <label htmlFor="question">经营决策问题</label>
        <textarea
          id="question"
          required
          minLength={12}
          maxLength={1000}
          rows={5}
          value={value.question}
          onChange={(e) => setValue({ ...value, question: e.target.value })}
          placeholder="例如：该直接上线 AI 售后客服，还是先做小范围验证？"
        />
        <div className="form-grid">
          <div>
            <label htmlFor="window">时间窗口</label>
            <select id="window" value={value.horizon_days} onChange={e => setValue({ ...value, horizon_days: Number(e.target.value) as HorizonDays })}>
              {[7, 14, 30, 90, 180, 365].map(days => <option key={days} value={days}>{days} 天</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="budget">预算上限（元）</label>
            <input
              id="budget"
              required
              type="number"
              min={0}
              max={10000000}
              step={1}
              value={value.budget_limit}
              onChange={(e) =>
                setValue({ ...value, budget_limit: e.target.valueAsNumber })
              }
            />
          </div>
        </div>
        <label htmlFor="goal">首要目标</label>
        <input
          id="goal"
          required
          maxLength={200}
          value={value.primary_goal}
          onChange={(e) => setValue({ ...value, primary_goal: e.target.value })}
        />
        <fieldset className="known-risks">
          <legend>你已经想到的风险（最多 5 条）</legend>
          {value.known_risks.map((risk, index) => <div className="risk-input" key={index}>
            <input aria-label={`已知风险 ${index + 1}`} maxLength={200} value={risk} onChange={e => setValue({ ...value, known_risks: value.known_risks.map((r, i) => i === index ? e.target.value : r) })} />
            <button type="button" aria-label={`删除风险 ${index + 1}`} onClick={() => setValue({ ...value, known_risks: value.known_risks.filter((_, i) => i !== index) })}>删除</button>
          </div>)}
          <button type="button" disabled={value.known_risks.length >= 5} onClick={() => setValue({ ...value, known_risks: [...value.known_risks, ""] })}>添加已知风险</button>
        </fieldset>
        <AssumptionEditor value={value.assumptions} onChange={assumptions => setValue({ ...value, assumptions })} />
        {value.scenario === "ai_tool_pilot" && <details className="baseline-form">

          <summary>
            <span>业务基线（可选）</span>
            <small>留空即未知，系统不会用行业均值补齐</small>
          </summary>
          <p className="baseline-intro">
            这些数字会随决策冻结。信息齐全时才生成收益试算；缺失项会变成采集任务。
          </p>
          <div className="baseline-input-groups">
            {baselineGroups.map((group) => (
              <fieldset key={group.title}>
                <legend>{group.title}</legend>
                {group.fields.map((field) => (
                  <div className="baseline-input" key={field.key}>
                    <label htmlFor={field.key}>{field.label}</label>
                    <div>
                      <input
                        id={field.key}
                        type="number"
                        min={0}
                        max={field.max}
                        step={field.step}
                        value={value.business_baseline?.[field.key] ?? ""}
                        onChange={(event) =>
                          setValue({
                            ...value,
                            business_baseline: {
                              ...(value.business_baseline ?? emptyBaseline),
                              [field.key]:
                                event.target.value === ""
                                  ? null
                                  : event.target.valueAsNumber,
                            },
                          })
                        }
                      />
                      <span>{field.suffix}</span>
                    </div>
                  </div>
                ))}
              </fieldset>
            ))}
          </div>
        </details>}
        <div className="form-bottom">
          <p>先确认条件，再由委员会审查。</p>
          <button className="primary" disabled={busy || disabled} type="submit">
            {busy ? "正在创建…" : "创建并开始研究"}
          </button>
        </div>
      </form>
    </section>
  );
}
