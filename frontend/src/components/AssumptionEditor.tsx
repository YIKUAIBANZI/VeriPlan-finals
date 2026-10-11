import type { AssumptionInput, AssumptionCategory } from "../types";
import { categoryLabels } from "../fixtures/scenarios";
export function AssumptionEditor({ value, onChange }: { value: AssumptionInput[]; onChange: (next: AssumptionInput[]) => void }) {
  function update(index: number, patch: Partial<AssumptionInput>) {
    onChange(value.map((item, i) => i === index ? { ...item, ...patch } : item));
  }
  return <fieldset className="assumptions-editor">
    <legend>数字假设（最多 8 条）</legend>
    <p className="muted">信心表示：你有多大把握，实际值落在假设值的 ±20% 以内。</p>
    {value.map((item, index) => <div className="assumption-row" key={index}>
      <label>标签<input aria-label={`假设 ${index + 1} 标签`} required value={item.label} onChange={e => update(index, { label: e.target.value })} /></label>
      <label>类别<select aria-label={`假设 ${index + 1} 类别`} value={item.category} onChange={e => update(index, { category: e.target.value as AssumptionCategory })}>{Object.entries(categoryLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label>数值<input aria-label={`假设 ${index + 1} 数值`} type="number" step="any" required value={Number.isFinite(item.value) ? item.value : ""} onChange={e => update(index, { value: e.target.valueAsNumber })} /></label>
      <label>单位<input aria-label={`假设 ${index + 1} 单位`} required value={item.unit} onChange={e => update(index, { unit: e.target.value })} /></label>
      <label>信心 {item.confidence}%<input aria-label={`假设 ${index + 1} 信心`} type="range" min={50} max={95} value={item.confidence} onChange={e => update(index, { confidence: e.target.valueAsNumber })} /></label>
      <button type="button" aria-label={`删除假设 ${index + 1}`} onClick={() => onChange(value.filter((_, i) => i !== index))}>删除</button>
    </div>)}
    <button type="button" disabled={value.length >= 8} onClick={() => onChange([...value, { label: "", category: "revenue", value: 0, unit: "元", confidence: 70 }])}>添加假设</button>
  </fieldset>;
}
