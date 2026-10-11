import { useState } from "react";
import {
  statusLabels,
  type Claim,
  type Decision,
  type ReviewAction,
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
  onReview,
  onExportMarkdown,
  onPrint,
  readOnlyReason,
}: {
  decision: Decision;
  busy: boolean;
  onReview: (action: ReviewAction, note: string) => void;
  onExportMarkdown: () => void;
  onPrint: () => void;
  readOnlyReason?: string;
}) {
  const [note, setNote] = useState("");
  const memo = decision.memo;
  const challenge = decision.outputs.challenging;
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
          <h3 className="verdict">{memo.summary}</h3>
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
      {challenge && (
        <section className="paper challenge-paper">
          <div className="section-heading">
            <h2>反方质询</h2>
            <span className="tag warn">先看可能错在哪里</span>
          </div>
          <p className="objection">
            {challenge.objection ?? challenge.summary}
          </p>
          <ul>
            {challenge.hidden_assumptions?.map((text) => (
              <li key={text}>{text}</li>
            ))}
          </ul>
        </section>
      )}
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
          {!isSupportedWindow(decision.time_window) && (
            <p className="legacy-warning">
              旧模板未受当前 14 天约束校验，请按历史输出人工复核。
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
                disabled={busy}
                onClick={() => onReview("accepted", note)}
              >
                采纳建议
              </button>
              <button disabled={busy} onClick={() => onReview("revised", note)}>
                记录修改意见
              </button>
              <button
                disabled={busy}
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
  const normalized = value.trim().replace(/\s+/g, " ").toLowerCase();
  return ["14 天", "14天", "14 day", "14 days"].includes(normalized);
}
