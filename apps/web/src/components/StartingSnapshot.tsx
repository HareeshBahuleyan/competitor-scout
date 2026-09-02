import Link from "next/link";

import { formatUserDateTime } from "@/lib/dates";
import type { StartingSnapshot as StartingSnapshotData } from "@/lib/schemas";

const topicHeadings = {
  positioning: "Positioning",
  product: "Product",
  pricing: "Pricing",
  go_to_market: "Go to market",
  other: "Other",
} as const;

type StartingSnapshotProps = {
  snapshot: StartingSnapshotData;
  timeZone: string;
  variant?: "detail" | "preview";
};

export function StartingSnapshot({
  snapshot,
  timeZone,
  variant = "detail",
}: StartingSnapshotProps) {
  const publishedLabel = formatUserDateTime(snapshot.published_at, timeZone);
  const covered = snapshot.coverage.inspected_source_count;
  const coverageText = snapshot.coverage.coverage_complete
    ? `Checked all ${covered} approved ${covered === 1 ? "source" : "sources"}.`
    : `Checked ${covered} of ${snapshot.coverage.approved_source_count} approved sources; ${snapshot.coverage.uninspected_source_count} remain uninspected.`;

  return (
    <section className="surface space-y-6 p-6" id="starting-snapshot">
      <header>
        <p className="eyebrow">Starting Snapshot</p>
        <h2 className="mt-1 text-xl font-semibold">
          What Scout established about {snapshot.competitor_name}
        </h2>
        <p className="mt-2 text-sm text-slate-500">
          Based on the first monitoring scan ·{" "}
          <time dateTime={snapshot.published_at}>{publishedLabel}</time>
        </p>
        <p className="mt-4 leading-7 text-slate-700">{snapshot.executive_summary}</p>
      </header>

      {variant === "preview" ? (
        <>
          <ul aria-label="Snapshot topics" className="flex flex-wrap gap-2">
            {snapshot.sections.map((section) => (
              <li
                className="rounded-full bg-[var(--color-accent-soft)] px-3 py-1 text-sm font-medium text-[var(--color-accent-strong)]"
                key={section.topic}
              >
                {topicHeadings[section.topic]}
              </li>
            ))}
          </ul>
          <p className="text-sm text-slate-600">{coverageText}</p>
          <Link
            className="inline-block rounded-lg bg-slate-950 px-4 py-2 font-semibold text-white"
            href={`/competitors/${snapshot.competitor_id}#starting-snapshot`}
          >
            View {snapshot.competitor_name} snapshot
          </Link>
        </>
      ) : (
        <>
          <div className="space-y-8">
            {snapshot.sections.map((section) => (
              <section aria-labelledby={`snapshot-${section.topic}`} key={section.topic}>
                <h3 className="text-lg font-semibold" id={`snapshot-${section.topic}`}>
                  {topicHeadings[section.topic]}
                </h3>
                <p className="mt-2 leading-7 text-slate-700">{section.narrative}</p>
                <details className="mt-3 rounded-lg border border-slate-200 p-4">
                  <summary className="cursor-pointer font-medium">
                    Evidence ({section.references.length})
                  </summary>
                  <ol className="mt-4 space-y-4">
                    {section.references.map((reference, index) => (
                      <li key={reference.evidence_id}>
                        <p className="text-sm text-slate-700">
                          <span aria-hidden="true">{index + 1}. </span>
                          {reference.statement}
                        </p>
                        <blockquote className="mt-2 border-l-2 border-slate-200 pl-3 text-sm text-slate-600">
                          “{reference.quoted_text}”
                        </blockquote>
                        <a
                          className="text-link mt-2 inline-block text-sm"
                          href={reference.source_url}
                          rel="noopener noreferrer"
                          target="_blank"
                        >
                          {reference.source_title}
                        </a>
                      </li>
                    ))}
                  </ol>
                </details>
              </section>
            ))}
          </div>
          <aside
            className={`rounded-lg border p-4 ${
              snapshot.coverage.coverage_complete
                ? "border-emerald-200 bg-emerald-50 text-emerald-900"
                : "border-amber-200 bg-amber-50 text-amber-900"
            }`}
            aria-label="Snapshot source coverage"
          >
            <p className="font-semibold">
              {snapshot.coverage.coverage_complete ? "Source coverage complete" : "Coverage gaps"}
            </p>
            <p className="mt-1 text-sm">{coverageText}</p>
          </aside>
          <Link className="section-link inline-block" href={`/runs/${snapshot.scout_run_id}`}>
            View the scan that produced this snapshot
          </Link>
        </>
      )}
    </section>
  );
}
