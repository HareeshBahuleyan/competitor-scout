export type EvidenceItem = {
  id: string;
  citation_order: number;
  source_title: string;
  source_url: string;
  quoted_text: string;
  published_at: string | null;
  captured_at: string;
  agent_task_id?: string;
  scout_run_id?: string;
};

type EvidenceListProps = {
  evidence: readonly EvidenceItem[];
};

function safeHttpsUrl(value: string) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" ? url.toString() : null;
  } catch {
    return null;
  }
}

export function EvidenceList({ evidence }: EvidenceListProps) {
  const orderedEvidence = [...evidence].sort(
    (first, second) => first.citation_order - second.citation_order,
  );

  return (
    <section aria-labelledby="evidence-heading" className="space-y-4">
      <h2 className="text-xl font-semibold" id="evidence-heading">
        Evidence
      </h2>
      <ol aria-label="Finding citations" className="space-y-2">
        {orderedEvidence.map((item) => {
          const sourceUrl = safeHttpsUrl(item.source_url);

          return (
            <li className="surface px-4 py-3" key={item.id}>
              {sourceUrl ? (
                <a
                  className="text-link font-medium"
                  href={sourceUrl}
                  rel="noopener noreferrer"
                  target="_blank"
                >
                  {item.source_title}
                  <span aria-hidden="true" className="ml-1 no-underline">
                    ↗
                  </span>
                </a>
              ) : (
                <span className="font-medium text-slate-950">{item.source_title}</span>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
