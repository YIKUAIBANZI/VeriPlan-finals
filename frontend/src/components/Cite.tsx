const EVENT = "veriplan:evidence";

export function focusEvidence(id: string) {
  window.dispatchEvent(new CustomEvent<string>(EVENT, { detail: id }));
}

export function onEvidenceFocus(handler: (id: string) => void) {
  const listener = (event: Event) => handler((event as CustomEvent<string>).detail);
  window.addEventListener(EVENT, listener);
  return () => window.removeEventListener(EVENT, listener);
}

export function Cite({ id, label }: { id: string; label?: string }) {
  return (
    <a
      className="cite"
      href={`#evidence-${id}`}
      onClick={(event) => {
        event.preventDefault();
        focusEvidence(id);
      }}
    >
      {label ?? `证据 ${id}`}
    </a>
  );
}

export function Citations({ ids }: { ids: string[] }) {
  if (!ids.length) return null;
  return <div className="citations">{ids.map(id => <Cite key={id} id={id} />)}</div>;
}
