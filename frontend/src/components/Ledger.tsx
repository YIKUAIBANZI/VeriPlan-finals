import { statusLabels, type Decision } from "../types";
export function Ledger({
  items,
  selected,
  onSelect,
  onNew,
  onCalibration,
  calibrationSelected,
}: {
  items: Decision[];
  selected?: string;
  onSelect: (id: string) => void;
  onNew: () => void;
  onCalibration?: () => void;
  calibrationSelected?: boolean;
}) {
  const reviewed = new Set(["accepted", "revised", "deferred", "retrospective"]);
  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-mark">证</span>
        <div>
          <strong>证策</strong>
          <span>VeriPlan</span>
        </div>
      </div>
      <button className="new-button" onClick={onNew}>
        <span aria-hidden="true">＋</span> 新建决策
      </button>
      {onCalibration && <button className="ledger-item calibration-nav" aria-current={calibrationSelected ? "page" : undefined} onClick={onCalibration}>我的偏差画像</button>}
      <nav aria-label="任务与决策账本">
        {[
          ["进行中的任务", false],
          ["决策账本", true],
        ].map(([title, isReviewed]) => (
          <section key={String(title)}>
            <h2>{title}</h2>
            {items
              .filter((item) => reviewed.has(item.status) === isReviewed)
              .map((item) => (
                <button
                  aria-current={item.id === selected ? "page" : undefined}
                  className="ledger-item"
                  key={item.id}
                  onClick={() => onSelect(item.id)}
                >
                  <span>{item.question}</span>
                  <small>{statusLabels[item.status]}</small>
                </button>
              ))}
            {!items.some(
              (item) => reviewed.has(item.status) === isReviewed,
            ) && (
              <p className="sidebar-empty">
                {isReviewed ? "审批后的决定会保存在这里" : "从一个真实问题开始"}
              </p>
            )}
          </section>
        ))}
      </nav>
      <div className="sidebar-footer">
        <span className="human-dot" />
        人工保留最终决定权<p>采纳、修改或暂缓，均只记录意见。</p>
      </div>
    </aside>
  );
}
