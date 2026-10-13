import { createContext, useContext } from "react";
import type { Evidence } from "../types";

const EVENT = "veriplan:evidence";

/** Maps stored (database-wide) evidence ids to their 1-based number within one decision. */
export const EvidenceNumbers = createContext<Map<string, number>>(new Map());

export function evidenceNumbers(evidence: Evidence[]) {
  return new Map(evidence.map((item, index) => [item.id ?? String(index + 1), index + 1]));
}

export function focusEvidence(id: string) {
  window.dispatchEvent(new CustomEvent<string>(EVENT, { detail: id }));
}

export function onEvidenceFocus(handler: (id: string) => void) {
  const listener = (event: Event) => handler((event as CustomEvent<string>).detail);
  window.addEventListener(EVENT, listener);
  return () => window.removeEventListener(EVENT, listener);
}

export function Cite({ id, label }: { id: string; label?: string }) {
  const number = useContext(EvidenceNumbers).get(id) ?? id;
  return (
    <a
      className="cite"
      href={`#evidence-${id}`}
      onClick={(event) => {
        event.preventDefault();
        focusEvidence(id);
      }}
    >
      {label ?? `证据 ${number}`}
    </a>
  );
}

export function Citations({ ids }: { ids: string[] }) {
  if (!ids.length) return null;
  return <div className="citations">{ids.map(id => <Cite key={id} id={id} />)}</div>;
}
