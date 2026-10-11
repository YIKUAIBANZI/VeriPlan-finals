import type { BaselineAnalysis, BusinessBaseline } from "../types";

const fields: {
  key: keyof BusinessBaseline;
  label: string;
  format: (value: number) => string;
}[] = [
  { key: "monthly_ticket_volume", label: "月售后工单量", format: (value) => `${value.toLocaleString("zh-CN")} 条` },
  { key: "repetitive_ticket_rate", label: "重复咨询占比", format: (value) => `${value}%` },
  { key: "average_handle_minutes", label: "平均处理时长", format: (value) => `${value} 分钟` },
  { key: "loaded_hourly_cost", label: "综合人力时薪", format: (value) => `¥${value.toLocaleString("zh-CN")}` },
  { key: "expected_ai_resolution_rate", label: "预计 AI 独立解决率", format: (value) => `${value}%` },
  { key: "review_minutes_per_ai_ticket", label: "AI 工单复核时长", format: (value) => `${value} 分钟` },
  { key: "monthly_tool_cost", label: "预计月工具成本", format: (value) => `¥${value.toLocaleString("zh-CN")}` },
  { key: "max_acceptable_error_rate", label: "最大可接受误答率", format: (value) => `${value}%` },
];

export function BusinessBaselinePanel({
  baseline,
  analysis,
}: {
  baseline: BusinessBaseline;
  analysis: BaselineAnalysis;
}) {
  const completeness = Math.round(
    (analysis.known_field_count / analysis.total_field_count) * 100,
  );
  return (
    <section className="paper baseline-paper" aria-labelledby="baseline-title">
      <div className="section-heading">
        <div>
          <h2 id="baseline-title">业务基线</h2>
          <p>创建时冻结 · 未知项不做猜测</p>
        </div>
        <span>{analysis.known_field_count} / {analysis.total_field_count} 已知</span>
      </div>
      <div
        className="baseline-progress"
        role="progressbar"
        aria-label="业务基线完整度"
        aria-valuemin={0}
        aria-valuemax={analysis.total_field_count}
        aria-valuenow={analysis.known_field_count}
      >
        <span style={{ width: `${completeness}%` }} />
      </div>
      <dl className="baseline-values">
        {fields.map((field) => {
          const value = baseline[field.key];
          return (
            <div key={field.key} data-known={value !== null}>
              <dt>{field.label}</dt>
              <dd>{value === null ? "未知" : field.format(value)}</dd>
            </div>
          );
        })}
      </dl>
      {analysis.is_calculable ? (
        <div className="baseline-estimate">
          <div><span>预计自动解决</span><strong>{analysis.automatable_ticket_volume?.toLocaleString("zh-CN")} 条 / 月</strong></div>
          <div><span>预计节省工时</span><strong>{analysis.monthly_hours_saved?.toLocaleString("zh-CN")} 小时 / 月</strong></div>
          <div><span>预计月净节省</span><strong>¥{analysis.estimated_monthly_net_savings?.toLocaleString("zh-CN")}</strong></div>
          <p>{analysis.disclaimer}</p>
        </div>
      ) : (
        <div className="baseline-collection">
          <h3>先补这些内部数据</h3>
          <ol>
            {analysis.collection_tasks.map((task) => <li key={task}>{task}</li>)}
          </ol>
          <p>{analysis.disclaimer}；输入不完整，本次不计算收益。</p>
        </div>
      )}
    </section>
  );
}
