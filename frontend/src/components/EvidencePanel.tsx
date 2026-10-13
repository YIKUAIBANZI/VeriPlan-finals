import { useEffect, useState } from "react";
import type { Evidence } from "../types";
import { onEvidenceFocus } from "./Cite";

type Filter = "all" | Evidence["stance"];
const stanceLabels: Record<Evidence["stance"], string> = { supports: "支持", opposes: "反对", context: "背景" };
const reliabilityLabels = { high: "高", medium: "中", low: "低" } as const;

function host(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export function EvidencePanel({ evidence }: { evidence: Evidence[] }) {
  const [filter, setFilter] = useState<Filter>("all");
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [flash, setFlash] = useState<string | null>(null);
  const hasLiveEvidence = evidence.some((item) => !item.is_demo);
  const keyOf = (item: Evidence, index: number) => item.id ?? String(index + 1);

  useEffect(() => onEvidenceFocus((id) => {
    setFilter("all");
    setOpen((prev) => new Set(prev).add(id));
    setFlash(id);
    requestAnimationFrame(() => {
      const card = document.getElementById(`evidence-${id}`);
      const list = card?.closest<HTMLElement>(".evidence-list");
      if (!card) return;
      // Desktop: the panel is sticky, so scroll only inside it and keep the reader's place.
      if (list && list.scrollHeight > list.clientHeight) {
        list.scrollTo({ top: card.offsetTop - 8, behavior: "smooth" });
      } else {
        card.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
      }
    });
    window.setTimeout(() => setFlash((current) => (current === id ? null : current)), 1600);
  }), []);

  const counts = evidence.reduce<Record<string, number>>((acc, item) => {
    acc[item.stance] = (acc[item.stance] ?? 0) + 1;
    return acc;
  }, {});
  const visible = evidence.map((item, index) => ({ item, key: keyOf(item, index) }))
    .filter(({ item }) => filter === "all" || item.stance === filter);

  function toggle(key: string) {
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  return (
    <aside className="evidence-panel" aria-label="证据对照">
      <div className="evidence-head">
        <h2>证据</h2>
        <span className="count">{evidence.length} 条</span>
      </div>
      {evidence.length > 0 && (
        <>
          <p className="evidence-note">
            {hasLiveEvidence
              ? "包含联网来源摘要；它们是第三方信息，尚未独立核验。"
              : "当前展示合成演示资料，未经联网核验。"}
          </p>
          {Object.keys(counts).length > 1 && <div className="evidence-filters" role="group" aria-label="按立场筛选">
            {(["all", "supports", "opposes", "context"] as Filter[]).map((key) => {
              const n = key === "all" ? evidence.length : counts[key] ?? 0;
              if (key !== "all" && !n) return null;
              return (
                <button key={key} type="button" className="chip" aria-pressed={filter === key} onClick={() => setFilter(key)}>
                  {key === "all" ? "全部" : stanceLabels[key]} {n}
                </button>
              );
            })}
          </div>}
        </>
      )}
      {evidence.length ? (
        <div className="evidence-list">
          {visible.map(({ item, key }) => {
            const expanded = open.has(key);
            return (
              <article
                id={`evidence-${key}`}
                key={key}
                className="evidence"
                data-stance={item.stance}
                data-open={expanded}
                data-flash={flash === key || undefined}
              >
                <button type="button" className="evidence-row" aria-expanded={expanded} onClick={() => toggle(key)}>
                  <span className="evidence-id">#{key}</span>
                  <span className="evidence-title">
                    <h3>{item.title}</h3>
                    <small>
                      <i className="stance-dot" data-stance={item.stance} aria-hidden="true" />
                      {stanceLabels[item.stance]} · {item.is_demo ? "演示" : host(item.source_url)}
                    </small>
                  </span>
                  <span className="caret" aria-hidden="true">{expanded ? "−" : "+"}</span>
                </button>
                <div className="evidence-body" hidden={!expanded}>
                  <p>{item.summary}</p>
                  <small>
                    {item.is_demo ? "演示可靠度：" : "来源可靠度："}
                    {reliabilityLabels[item.reliability]}
                  </small>
                  <div className="source-url">
                    {item.is_demo || !/^https?:\/\//i.test(item.source_url) ? (
                      `${item.is_demo ? "演示占位来源" : "联网来源"} · ${item.source_url}`
                    ) : (
                      <a href={item.source_url} target="_blank" rel="noopener noreferrer">{`联网来源 · ${item.source_url}`}</a>
                    )}
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <div className="empty-evidence">
          <p>确认条件后，这里会展示支持与反对意见的依据。</p>
        </div>
      )}
    </aside>
  );
}
