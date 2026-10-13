import { useState } from "react";
import type { BusinessBaseline, DecisionInput, HorizonDays, Scenario } from "../types";
import { emptyBaseline, scenarioExamples, scenarioLabels } from "../fixtures/scenarios";
import { AssumptionEditor } from "./AssumptionEditor";

const blank: DecisionInput = {
  scenario: "general", question: "", horizon_days: 30, budget_limit: Number.NaN,
  primary_goal: "", known_risks: [], assumptions: [],
};

const baselineFields: { key: keyof BusinessBaseline; label: string; suffix: string; max: number; step: number }[] = [
  { key: "monthly_ticket_volume", label: "月售后工单量", suffix: "条", max: 10000000, step: 1 },
  { key: "repetitive_ticket_rate", label: "重复咨询占比", suffix: "%", max: 100, step: 0.1 },
  { key: "average_handle_minutes", label: "平均处理时长", suffix: "分钟", max: 1440, step: 0.1 },
  { key: "loaded_hourly_cost", label: "综合人力时薪", suffix: "元", max: 1000000, step: 0.01 },
  { key: "expected_ai_resolution_rate", label: "预计 AI 独立解决率", suffix: "%", max: 100, step: 0.1 },
  { key: "review_minutes_per_ai_ticket", label: "单条 AI 工单复核时长", suffix: "分钟", max: 1440, step: 0.1 },
  { key: "monthly_tool_cost", label: "预计月工具成本", suffix: "元", max: 10000000, step: 0.01 },
  { key: "max_acceptable_error_rate", label: "可接受最大误答率", suffix: "%", max: 100, step: 0.1 },
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
  const [value, setValue] = useState<DecisionInput>(initial ?? blank);
  const [risks, setRisks] = useState((initial?.known_risks ?? []).join("\n"));
  const [fromExample, setFromExample] = useState(false);
  const riskLines = risks.split("\n").map(line => line.trim()).filter(Boolean);
  const hasDetails = riskLines.length > 0 || value.assumptions.length > 0;

  function fill(scenario: Scenario) {
    const example = structuredClone(scenarioExamples[scenario]);
    setValue(example);
    setRisks(example.known_risks.join("\n"));
    setFromExample(true);
  }

  return (
    <section className="composer">
      <p className="eyebrow">新建决策</p>
      <h1 className="display">这次，你在犹豫什么？</h1>
      <p className="lede">用一两句话说清楚。委员会先和你对齐条件，再去找证据、互相质疑。</p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (busy || disabled) return;
          const { business_baseline, ...input } = value;
          onSubmit({
            ...input,
            known_risks: riskLines.slice(0, 5),
            ...(value.scenario === "ai_tool_pilot" ? { business_baseline: business_baseline ?? { ...emptyBaseline } } : {}),
          });
        }}
      >
        <div className="question-box">
          <textarea
            id="question"
            aria-label="经营决策问题"
            required
            minLength={12}
            maxLength={1000}
            rows={4}
            value={value.question}
            onChange={(e) => setValue({ ...value, question: e.target.value })}
            placeholder="比如：接单已经排到 6 周后，要不要每月花 1.2 万招第一个设计助理？"
          />
          <div className="example-row" aria-label="示例">
            <span>试试示例</span>
            {(Object.keys(scenarioLabels) as Scenario[]).map(scenario => (
              <button
                key={scenario}
                type="button"
                className="chip"
                aria-label={`填入 ${scenarioLabels[scenario]}示例`}
                aria-pressed={fromExample && value.scenario === scenario}
                onClick={() => fill(scenario)}
              >
                {scenarioLabels[scenario]}
              </button>
            ))}
          </div>
        </div>
        {fromExample && <p className="synthetic-note">示例里的数字是合成的，换成你自己的再提交。</p>}

        <div className="essentials">
          <label>
            <span>多久内要定</span>
            <select id="window" aria-label="时间窗口" value={value.horizon_days} onChange={e => setValue({ ...value, horizon_days: Number(e.target.value) as HorizonDays })}>
              {[7, 14, 30, 90, 180, 365].map(days => <option key={days} value={days}>{days} 天</option>)}
            </select>
          </label>
          <label>
            <span>最多花多少</span>
            <div className="affix">
              <input
                id="budget"
                aria-label="预算上限（元）"
                required
                type="number"
                min={0}
                max={10000000}
                step={1}
                placeholder="例如 30000"
                value={Number.isFinite(value.budget_limit) ? value.budget_limit : ""}
                onChange={(e) => setValue({ ...value, budget_limit: e.target.valueAsNumber })}
              />
              <span>元</span>
            </div>
          </label>
          <label className="wide">
            <span>最想达成什么</span>
            <input
              id="goal"
              aria-label="首要目标"
              required
              maxLength={200}
              placeholder="例如：三个月内产能翻倍，口碑不降"
              value={value.primary_goal}
              onChange={(e) => setValue({ ...value, primary_goal: e.target.value })}
            />
          </label>
        </div>

        <details className="more" open={Boolean(initial && hasDetails) || undefined}>
          <summary>
            <span>补充你已想到的风险和数字假设</span>
            <small>{hasDetails ? `已填 ${riskLines.length} 条风险 · ${value.assumptions.length} 条假设` : "可选 · 写得越具体，反方越能挑出你没想到的"}</small>
          </summary>
          <label className="block-label">
            <span>已经想到的风险（每行一条，最多 5 条）</span>
            <textarea
              aria-label="已知风险"
              rows={3}
              value={risks}
              onChange={e => setRisks(e.target.value)}
              placeholder={"客户可能拖欠尾款\n招来的人带不起来"}
            />
          </label>
          {riskLines.length > 5 && <p className="field-hint">只会提交前 5 条。</p>}
          <AssumptionEditor value={value.assumptions} onChange={assumptions => setValue({ ...value, assumptions })} />
          {value.scenario === "ai_tool_pilot" && (
            <details className="baseline-form">
              <summary>业务基线（可选）<small>留空即未知，系统不会用行业均值补齐</small></summary>
              <div className="baseline-grid">
                {baselineFields.map((field) => (
                  <label key={field.key}>
                    <span>{field.label}</span>
                    <div className="affix">
                      <input
                        id={field.key}
                        aria-label={field.label}
                        type="number"
                        min={0}
                        max={field.max}
                        step={field.step}
                        value={value.business_baseline?.[field.key] ?? ""}
                        onChange={(event) => setValue({
                          ...value,
                          business_baseline: {
                            ...(value.business_baseline ?? emptyBaseline),
                            [field.key]: event.target.value === "" ? null : event.target.valueAsNumber,
                          },
                        })}
                      />
                      <span>{field.suffix}</span>
                    </div>
                  </label>
                ))}
              </div>
            </details>
          )}
        </details>

        <div className="form-bottom">
          <p>提交后会先请你确认条件，再开始检索。</p>
          <button className="primary" disabled={busy || disabled} type="submit">
            {busy ? "正在创建…" : "创建并开始研究"}
          </button>
        </div>
      </form>
    </section>
  );
}
