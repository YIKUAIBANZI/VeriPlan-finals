import { useState } from "react";
import { ChallengePanel } from "./ChallengePanel";
import {
  statusLabels,
  recommendationLabels,
  type Claim,
  type Decision,
  type ReviewAction,
  type ObjectionLabels,
  type ObjectionLabel,
} from "../types";
function Claims({ items }: { items: Claim[] }) {
  return (
    <ul className="claims">
      {items.map((item, index) => (
        <li key={index}>
          {item.text}
          <span className="citations">
            {item.evidence_ids?.map((id) => (
              <a key={id} href={`#evidence-${id}`}>
                查看引用来源
              </a>
            ))}
          </span>
        </li>
      ))}
    </ul>
  );
}
export function DecisionResult({
  decision,
  busy,
  writeDisabled = false,
  onReview,
  onLabel,
  onExportMarkdown,
  onPrint,
  readOnlyReason,
}: {
  decision: Decision;
  busy: boolean;
  writeDisabled?: boolean;
  onLabel?: (labels: ObjectionLabels) => void;
  onReview: (action: ReviewAction, note: string) => void;
  onExportMarkdown: () => void;
  onPrint: () => void;
  readOnlyReason?: string;
}) {
  const [note, setNote] = useState("");
  const memo = decision.memo;
  const recommendation = decision.outputs.delivering?.recommendation ?? memo?.recommendation;
  const conditions = decision.outputs.delivering?.conditions ?? memo?.conditions ?? [];
  const objections = decision.outputs.challenging?.objections ?? [];
  const reviewed = ["accepted", "revised", "deferred"].includes(decision.status);
  const adopted = objections.filter(item => decision.objection_labels?.[item.id] === "adopted").length;

  return (
    <>
      {memo && (
        <section className="paper result-paper">
          <div className="section-heading">
            <h2>决策 Memo</h2>
            <span className="tag">
              {decision.mode === "live" ? "联网研究结论" : "演示结论"}
            </span>
          </div>
          <div className="memo-actions no-print" aria-label="Memo 导出">
            <button disabled={busy} onClick={onExportMarkdown}>
              下载 Markdown
            </button>
            <button disabled={busy} onClick={onPrint}>
              打印 / 存为 PDF
            </button>
          </div>
          {recommendation && <p className="recommendation" aria-label="推荐结论">{recommendationLabels[recommendation] ?? recommendation}</p>}
          <h3 className="verdict">{memo.summary}</h3>
          {conditions.length > 0 && <div className="delivery-conditions"><h3>推进前必须满足的条件</h3><ul>{conditions.map((item, index) => <li key={`${item.objection_id}-${index}`}>{item.objection_id}：{item.condition}</li>)}</ul></div>}
          <div className="support">
            <div>
              <strong>{memo.support_score}</strong>
              <span>/ 100</span>
            </div>
            <div>
              <b>
                决策支持度 ·{" "}
                {memo.support_score < 40
                  ? "证据不足"
                  : memo.support_score < 60
                    ? "低支持"
                    : memo.support_score < 80
                      ? "中等支持"
                      : "高支持"}
              </b>
              <p>衡量证据对建议的支持程度，不代表成功概率。</p>
            </div>
          </div>
          {memo.score_explanation && (
            <p className="muted">{memo.score_explanation}</p>
          )}
          <h3>
            来源陈述（待人工核验）{" "}
            <small>
              {decision.mode === "live"
                ? "联网来源中的陈述"
                : "演示材料中的陈述"}
            </small>
          </h3>
          <p className="muted">
            引用只建立可回看关系，不代表系统已自动核验陈述与来源相互支持。
          </p>
          <Claims items={memo.facts ?? []} />
          <h3>Agent 推断</h3>
          <Claims items={memo.inferences ?? []} />
          {Boolean(memo.research_gaps?.length) && (
            <div className="research-gap">
              <h3>仍需验证</h3>
              <ul>
                {memo.research_gaps?.map((text) => (
                  <li key={text}>{text}</li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}
      <ChallengePanel decision={decision} />
      {memo && (
        <section className="paper action-paper">
          <div className="section-heading">
            <h2>验证行动计划</h2>
            <span>
              总预算上限 ¥{decision.budget_limit.toLocaleString("zh-CN")}
            </span>
          </div>
          <p className="muted">
            决策窗口：{decision.time_window}
            。以小范围验证为目标，行动需要人工执行。
          </p>
          {!decision.horizon_days && !isSupportedWindow(decision.time_window) && (
            <p className="legacy-warning">
              历史周期未对应当前可选范围，请按原始行动计划人工复核。
            </p>
          )}
          <ol className="actions">
            {memo.action_plan?.map((item, index) => (
              <li key={index}>
                <div className="action-days">
                  {item.days ?? `阶段 ${index + 1}`}
                </div>
                <div>
                  <h3>{item.action}</h3>
                  <p>
                    <b>负责人</b> {item.owner}
                  </p>
                  <p>
                    <b>验收指标</b> {item.metric}
                  </p>
                  <p className="stop-condition">
                    <b>停止条件</b> {item.stop_condition}
                  </p>
                  {typeof item.budget_limit === "number" && (
                    <p className="action-budget">
                      单项预算 ¥{item.budget_limit.toLocaleString("zh-CN")}
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}
      <section className="paper review-paper">
        <h2>用户确认</h2>
        {objections.length > 0 && <div className="objection-labels">
          <h3>这些风险，你怎么看？</h3>
          <p>每次标注都会保存；采纳的条目计入方案改变数。</p>
          {objections.map(item => <label key={item.id}>{item.id} · {item.text}
            <select aria-label={`${item.id} 风险标注`} value={decision.objection_labels?.[item.id] ?? ""}
              disabled={busy || writeDisabled || Boolean(readOnlyReason) || !onLabel || (!reviewed && decision.status !== "awaiting_review")}
              onChange={e => onLabel?.({ ...decision.objection_labels, [item.id]: e.target.value as ObjectionLabel })}>
              <option value="" disabled>尚未标注</option>
              <option value="adopted">采纳</option><option value="already_known">已知</option><option value="disagree">不同意</option>
            </select>
          </label>)}
          {reviewed && <p className="adopted-count">{adopted} 条改变了方案</p>}
        </div>}
        {readOnlyReason ? (
          <p className="review-status">{readOnlyReason}</p>
        ) : decision.status === "awaiting_review" ? (
          <>
            <p>你的决定将保存到决策账本。修改意见会留档，暂不自动重写报告。</p>
            <label htmlFor="review-note">审批备注</label>
            <textarea
              id="review-note"
              rows={3}
              maxLength={1000}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="记录你接受的条件、修改意见或暂缓原因。"
            />
            <div className="review-buttons">
              <button
                className="primary"
                disabled={busy || writeDisabled}
                onClick={() => onReview("accepted", note)}
              >
                采纳建议
              </button>
              <button disabled={busy || writeDisabled} onClick={() => onReview("revised", note)}>
                记录修改意见
              </button>
              <button
                disabled={busy || writeDisabled}
                onClick={() => onReview("deferred", note)}
              >
                暂缓决定
              </button>
            </div>
          </>
        ) : (
          <>
            <p className="review-status">{statusLabels[decision.status]}</p>
            <p>{decision.review_note || "未填写审批备注。"}</p>
          </>
        )}
      </section>
    </>
  );
}

function isSupportedWindow(value: string) {
  return /^(7|14|30|90|180|365)\s*(天|days?)$/i.test(value.trim());
}
