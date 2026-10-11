import type { ResearchQuery } from "../types";

const labels: Record<ResearchQuery["status"], string> = {
  pending: "等待检索",
  running: "正在检索",
  succeeded: "检索完成",
  failed: "本次查询未完成",
};

export function ResearchQueries({ queries }: { queries: ResearchQuery[] }) {
  if (!queries.length) return null;

  return (
    <section className="paper research-queries" aria-label="公开搜索计划">
      <div className="section-heading">
        <h2>公开搜索计划</h2>
        <span>最多 3 个查询</span>
      </div>
      <ol>
        {queries.map((item) => (
          <li key={item.id} data-status={item.status}>
            <span>{item.query}</span>
            <small>
              {item.status === "succeeded"
                ? `已保存 ${item.evidence_count} 条新证据`
                : labels[item.status]}
            </small>
          </li>
        ))}
      </ol>
    </section>
  );
}
