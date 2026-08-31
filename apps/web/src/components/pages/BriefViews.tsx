"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { apiGetClient } from "@/lib/api";
import { weeklyBriefPageSchema, weeklyBriefSchema } from "@/lib/schemas";

function errorText(error: unknown) {
  return error instanceof Error ? error.message : "Something went wrong.";
}

function formatDate(value: string) {
  return new Date(`${value}T00:00:00Z`).toLocaleDateString("en-US", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
    year: "numeric",
  });
}

function period(start: string, end: string) {
  return `${formatDate(start)} – ${formatDate(end)}`;
}

export function BriefsListView() {
  const query = useQuery({
    queryKey: ["briefs"],
    queryFn: () => apiGetClient("/api/v1/briefs", weeklyBriefPageSchema),
  });
  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-3xl font-bold">Weekly briefs</h1>
        <p className="mt-1 text-slate-600">Validated summaries grounded in accepted findings.</p>
      </header>
      {query.isPending ? <p role="status">Loading weekly briefs…</p> : null}
      {query.isError ? <p className="text-red-700" role="alert">{errorText(query.error)}</p> : null}
      {query.data?.items.length === 0 ? <p className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-slate-600">No weekly briefs yet.</p> : null}
      {query.data?.items.length ? (
        <ul className="space-y-4">
          {query.data.items.map((brief) => (
            <li className="rounded-xl border border-slate-200 bg-white p-5" key={brief.id}>
              <p className="text-sm text-slate-500">{period(brief.period_start, brief.period_end)}</p>
              <h2 className="mt-1 text-lg font-semibold"><Link className="hover:underline" href={`/briefs/${brief.id}`}>{brief.title}</Link></h2>
              <p className="mt-2 text-slate-600">{brief.executive_summary}</p>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

export function BriefDetailView({ briefId }: { briefId: string }) {
  const query = useQuery({
    queryKey: ["brief", briefId],
    queryFn: () => apiGetClient(`/api/v1/briefs/${briefId}`, weeklyBriefSchema),
  });
  if (query.isPending) return <p role="status">Loading weekly brief…</p>;
  if (query.isError) return <p className="text-red-700" role="alert">{errorText(query.error)}</p>;
  const brief = query.data;
  return (
    <article className="space-y-8">
      <header>
        <p className="text-sm font-medium text-slate-500">{period(brief.period_start, brief.period_end)}</p>
        <h1 className="mt-2 text-3xl font-bold">{brief.title}</h1>
        <p className="mt-3 text-lg text-slate-700">{brief.executive_summary}</p>
      </header>
      {brief.sections.length ? brief.sections.map((section, index) => (
        <section aria-labelledby={`brief-section-${index}`} className="rounded-xl border border-slate-200 bg-white p-5" key={`${section.heading}-${index}`}>
          <h2 className="text-xl font-semibold" id={`brief-section-${index}`}>{section.heading}</h2>
          <p className="mt-3 text-slate-700">{section.narrative}</p>
          <ol aria-label={`Evidence references for ${section.heading}`} className="mt-4 space-y-3 border-t border-slate-100 pt-4">
            {section.references.map((reference, referenceIndex) => (
              <li className="text-sm text-slate-600" key={`${reference.finding_id}-${referenceIndex}`}>
                <p><span aria-hidden="true">{referenceIndex + 1}. </span>{reference.statement}</p>
                <Link className="mt-1 inline-block font-medium text-blue-700 hover:underline" href={`/findings/${reference.finding_id}`}>
                  View finding and evidence
                </Link>
              </li>
            ))}
          </ol>
        </section>
      )) : (
        <p className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-slate-600">
          This brief intentionally contains no finding references for an empty week.
        </p>
      )}
      <Link className="text-sm font-medium text-blue-700 hover:underline" href={`/runs/${brief.scout_run_id}`}>View brief generation run</Link>
    </article>
  );
}
