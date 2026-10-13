import type { Decision } from "../types";
const stages = [
  ["clarifying", "目标澄清"],
  ["planning", "研究规划"],
  ["researching", "证据收集"],
  ["analyzing", "多方分析"],
  ["challenging", "反方质询"],
  ["delivering", "决策交付"],
];
export function WorkflowTimeline({ decision }: { decision: Decision | null }) {
  return (
    <ol className="workflow" aria-label="工作流阶段">
      {stages.map(([key, label], index) => {
        const done = decision?.events.some(
          (e) => e.stage === key && e.status === "completed",
        );
        const current =
          decision?.status === key || decision?.failure?.stage === key;
        return (
          <li
            key={key}
            className={done ? "done" : current ? "current" : ""}
            aria-current={current ? "step" : undefined}
          >
            <span className="step-mark">{done ? "✓" : index + 1}</span>
            <span className="step-label">{label}</span>
          </li>
        );
      })}
    </ol>
  );
}
export function EventLog({ decision }: { decision: Decision }) {
  return (
    <details className="card event-log" open={false}>
      <summary>
        执行轨迹 <span>{decision.events.length} 条记录</span>
      </summary>
      <ol>
        {decision.events.map((event, index) => (
          <li key={index}>
            <span className="event-dot">
              {event.status === "completed"
                ? "✓"
                : event.status === "failed"
                  ? "!"
                  : "·"}
            </span>
            <div>
              <p>{event.summary}</p>
              <time dateTime={event.created_at}>
                {new Date(event.created_at).toLocaleTimeString("zh-CN", {
                  hour12: false,
                })}
              </time>
            </div>
          </li>
        ))}
      </ol>
      {!decision.events.length && (
        <p className="muted">任务已创建，等待执行记录。</p>
      )}
    </details>
  );
}
