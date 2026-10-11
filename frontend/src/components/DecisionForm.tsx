import { useState } from "react";
import type { BusinessBaseline, DecisionInput } from "../types";
const emptyBaseline: BusinessBaseline = {
  monthly_ticket_volume: null,
  repetitive_ticket_rate: null,
  average_handle_minutes: null,
  loaded_hourly_cost: null,
  expected_ai_resolution_rate: null,
  review_minutes_per_ai_ticket: null,
  monthly_tool_cost: null,
  max_acceptable_error_rate: null,
};
const example: DecisionInput = {
  question:
    "我们的售后消息越来越多，想用 AI 客服降低人力成本，但担心体验变差。两周内应该直接上线，还是先做小范围验证？",
  time_window: "14 天",
  budget_limit: 8000,
  primary_goal: "降低重复咨询，同时守住客户满意度",
  business_baseline: {
    monthly_ticket_volume: 1200,
    repetitive_ticket_rate: 60,
    average_handle_minutes: 8,
    loaded_hourly_cost: 45,
    expected_ai_resolution_rate: 70,
    review_minutes_per_ai_ticket: 1.5,
    monthly_tool_cost: 1200,
    max_acceptable_error_rate: 2,
  },
};

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
  onSubmit,
  initial,
}: {
  busy: boolean;
  onSubmit: (input: DecisionInput) => void;
  initial?: DecisionInput;
}) {
  const [value, setValue] = useState(
    initial
      ? {
          ...initial,
          time_window: example.time_window,
          business_baseline: initial.business_baseline ?? { ...emptyBaseline },
        }
      : { ...example, question: "", business_baseline: { ...emptyBaseline } },
  );
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
          onSubmit(value);
        }}
      >
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
        <button
          className="text-button"
          type="button"
          onClick={() => setValue(example)}
        >
          填入 AI 售后客服示例
        </button>
        <div className="form-grid">
          <div>
            <label htmlFor="window">时间窗口</label>
            <input
              id="window"
              required
              maxLength={80}
              value={value.time_window}
              readOnly
            />
            <small className="field-hint">
              当前版本固定为 14 天验证计划。
            </small>
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
        <details className="baseline-form">
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
                        value={value.business_baseline[field.key] ?? ""}
                        onChange={(event) =>
                          setValue({
                            ...value,
                            business_baseline: {
                              ...value.business_baseline,
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
          <p className="synthetic-note">
            “填入示例”使用合成演示数字，不代表你的真实业务。
          </p>
        </details>
        <div className="form-bottom">
          <p>当前演示范围：AI 售后客服试点决策。</p>
          <button className="primary" disabled={busy} type="submit">
            {busy ? "正在创建…" : "创建并开始研究"}
          </button>
        </div>
      </form>
    </section>
  );
}
