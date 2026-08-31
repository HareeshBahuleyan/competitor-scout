import Link from "next/link";

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

function formatTimestamp(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    month: "short",
    timeZone: "UTC",
    timeZoneName: "short",
    year: "numeric",
  }).format(new Date(value));
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
      <ol aria-label="Finding citations" className="space-y-4">
        {orderedEvidence.map((item) => {
          const sourceUrl = safeHttpsUrl(item.source_url);

          return (
            <li className="rounded-xl border border-slate-200 bg-white p-5" key={item.id}>
              <article>
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Citation {item.citation_order}
                </p>
                <h3 className="mt-2 font-semibold text-slate-950">
                  {sourceUrl ? (
                    <a
                      className="text-blue-700 hover:underline"
                      href={sourceUrl}
                      rel="noopener noreferrer"
                      target="_blank"
                    >
                      {item.source_title}
                    </a>
                  ) : (
                    item.source_title
                  )}
                </h3>
                <blockquote className="mt-4 border-l-4 border-slate-300 pl-4 text-sm leading-6 text-slate-700">
                  {item.quoted_text}
                </blockquote>
                <dl className="mt-4 grid gap-2 text-xs text-slate-500 sm:grid-cols-2">
                  <div>
                    <dt className="font-medium text-slate-700">Published</dt>
                    <dd>
                      {item.published_at ? (
                        <time dateTime={item.published_at}>
                          {formatTimestamp(item.published_at)}
                        </time>
                      ) : (
                        "Publication time unavailable"
                      )}
                    </dd>
                  </div>
                  <div>
                    <dt className="font-medium text-slate-700">Captured</dt>
                    <dd>
                      <time dateTime={item.captured_at}>{formatTimestamp(item.captured_at)}</time>
                    </dd>
                  </div>
                </dl>
                {item.agent_task_id && item.scout_run_id ? (
                  <Link
                    className="mt-3 inline-block text-xs font-medium text-blue-700 hover:underline"
                    href={`/runs/${item.scout_run_id}#task-${item.agent_task_id}`}
                  >
                    Child task {item.citation_order}
                  </Link>
                ) : null}
              </article>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
