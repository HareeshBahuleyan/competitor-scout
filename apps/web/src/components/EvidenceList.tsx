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

/* Quoted source text often contains bare URLs. Split on them so each one
   becomes a real link, while every other character stays inert text that React
   escapes. */
const httpsUrlPattern = /https:\/\/[^\s<>"'()[\]]+/g;

function trimUrlPunctuation(value: string) {
  return value.replace(/[.,;:!?'"]+$/, "");
}

type QuotedSegment = { key: string; text: string; url: string | null };

function segmentQuotedText(value: string): readonly QuotedSegment[] {
  const segments: QuotedSegment[] = [];
  let cursor = 0;

  for (const match of value.matchAll(httpsUrlPattern)) {
    const start = match.index ?? 0;
    const candidate = trimUrlPunctuation(match[0]);
    const url = safeHttpsUrl(candidate);
    if (!url) continue;
    if (start > cursor) {
      segments.push({ key: `text-${cursor}`, text: value.slice(cursor, start), url: null });
    }
    segments.push({ key: `link-${start}`, text: candidate, url });
    cursor = start + candidate.length;
  }

  if (cursor < value.length) {
    segments.push({ key: `text-${cursor}`, text: value.slice(cursor), url: null });
  }

  return segments;
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
            <li className="surface p-5" key={item.id}>
              <article>
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Citation {item.citation_order}
                </p>
                <h3 className="mt-2 font-semibold text-slate-950">
                  {sourceUrl ? (
                    <a
                      className="text-link font-semibold"
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
                    item.source_title
                  )}
                </h3>
                {sourceUrl ? (
                  <p className="mt-1 text-xs break-all text-slate-500">{sourceUrl}</p>
                ) : null}
                <blockquote className="mt-4 rounded-r-xl border-l-4 border-[var(--color-accent)] bg-slate-50 px-4 py-3 text-sm leading-6 text-slate-700">
                  {segmentQuotedText(item.quoted_text).map((segment) =>
                    segment.url ? (
                      <a
                        className="text-link"
                        href={segment.url}
                        key={segment.key}
                        rel="noopener noreferrer"
                        target="_blank"
                      >
                        {segment.text}
                      </a>
                    ) : (
                      <span key={segment.key}>{segment.text}</span>
                    ),
                  )}
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
                    className="section-link mt-3 inline-block text-xs"
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
