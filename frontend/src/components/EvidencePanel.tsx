import type { Evidence } from "../types";
export function EvidencePanel({ evidence }: { evidence: Evidence[] }) {
  const hasLiveEvidence = evidence.some((item) => !item.is_demo);

  return (
    <aside className="paper evidence-panel">
      <div className="section-heading">
        <h2>证据对照</h2>
        <span>{evidence.length} 条</span>
      </div>
      {evidence.length > 0 && (
        <p className="muted">
          {hasLiveEvidence
            ? "包含联网来源摘要；它们是第三方信息，尚未独立核验。"
            : "当前展示合成演示资料，未经联网核验。"}
        </p>
      )}
      {evidence.length ? (
        evidence.map((item, index) => (
          <article
            id={`evidence-${item.id ?? index + 1}`}
            key={item.id ?? index}
            className="evidence"
          >
            <div className="evidence-meta">
              <span>证据 {index + 1}</span>
              <span className={item.stance === "opposes" ? "tag warn" : "tag"}>
                {
                  { supports: "支持", opposes: "反对", context: "背景" }[
                    item.stance
                  ]
                }
              </span>
            </div>
            <h3>{item.title}</h3>
            <p>{item.summary}</p>
            <small>
              {item.is_demo ? "演示可靠度：" : "来源可靠度："}
              {{ high: "高", medium: "中", low: "低" }[item.reliability]}
            </small>
            <div className="source-url">
              {item.is_demo ? "演示占位来源" : "联网来源"} · {item.source_url}
            </div>
          </article>
        ))
      ) : (
        <div className="empty-evidence">
          <span aria-hidden="true">▤</span>
          <p>确认条件后，这里会展示支持与反对意见的依据。</p>
        </div>
      )}
    </aside>
  );
}
