"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { DigestStatusCard } from "@/components/DigestStatusCard";
import { MonitoringCoverageReceipt } from "@/components/MonitoringCoverageReceipt";
import { LoadingState } from "@/components/ui/LoadingState";
import { apiGetClient } from "@/lib/api";
import { meQueryOptions } from "@/lib/current-user";
import { formatUserDateTime } from "@/lib/dates";
import { digestOverviewSchema, weeklyBriefPageSchema, weeklyBriefSchema } from "@/lib/schemas";

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
  const briefs = useQuery({
    queryKey: ["briefs"],
    queryFn: () => apiGetClient("/api/v1/briefs", weeklyBriefPageSchema),
  });
  const overview = useQuery({
    queryKey: ["briefs", "overview"],
    queryFn: () => apiGetClient("/api/v1/briefs/overview", digestOverviewSchema),
  });
  const me = useQuery(meQueryOptions);
  const queries = [briefs, overview, me];
  const failed = queries.find((query) => query.isError);
  const history =
    briefs.data?.items.filter((brief) => brief.id !== overview.data?.latest_brief?.id) ?? [];

  return (
    <section className="space-y-7">
      <header>
        <p className="eyebrow">Executive intelligence</p>
        <h1 className="mt-1 text-4xl font-semibold">Weekly Digest</h1>
        <p className="mt-2 text-slate-600">
          Your week in one page, backed by the updates behind it.
        </p>
      </header>
      {queries.some((query) => query.isPending) ? (
        <LoadingState label="Loading Weekly Digests…" rows={4} />
      ) : null}
      {failed ? (
        <p className="text-red-700" role="alert">
          {errorText(failed.error)}
        </p>
      ) : null}
      {overview.data && me.data ? (
        <DigestStatusCard overview={overview.data} timeZone={me.data.timezone} />
      ) : null}
      {briefs.data && overview.data ? (
        <section aria-labelledby="digest-archive-heading" className="space-y-4">
          <div>
            <p className="eyebrow">Published record</p>
            <h2 className="mt-1 text-xl font-semibold" id="digest-archive-heading">
              Digest archive
            </h2>
          </div>
          {history.length ? (
            <ul className="space-y-4">
              {history.map((brief) => (
                <li className="surface surface-interactive p-5" key={brief.id}>
                  <p className="text-sm text-slate-500">
                    {period(brief.period_start, brief.period_end)}
                  </p>
                  <h3 className="mt-1 text-lg font-semibold">
                    <Link className="hover:underline" href={`/briefs/${brief.id}`}>
                      {brief.title}
                    </Link>
                  </h3>
                  <p className="mt-2 text-slate-600">{brief.executive_summary}</p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="empty-state p-6 text-sm">
              {overview.data.latest_brief
                ? "No earlier digests in the archive."
                : "The archive will begin when the first digest is published."}
            </p>
          )}
        </section>
      ) : null}
    </section>
  );
}

export function BriefDetailView({ briefId }: { briefId: string }) {
  const query = useQuery({
    queryKey: ["brief", briefId],
    queryFn: () => apiGetClient(`/api/v1/briefs/${briefId}`, weeklyBriefSchema),
  });
  const overview = useQuery({
    queryKey: ["briefs", "overview"],
    queryFn: () => apiGetClient("/api/v1/briefs/overview", digestOverviewSchema),
  });
  const me = useQuery(meQueryOptions);
  if (query.isPending) return <LoadingState label="Loading the Weekly Digest…" rows={4} />;
  if (query.isError)
    return (
      <p className="text-red-700" role="alert">
        {errorText(query.error)}
      </p>
    );
  const brief = query.data;
  return (
    <article className="mx-auto max-w-3xl space-y-10">
      <header>
        <p className="text-sm font-medium text-slate-500">
          {period(brief.period_start, brief.period_end)}
        </p>
        <h1 className="mt-2 text-4xl font-semibold">{brief.title}</h1>
        <p className="mt-4 text-lg leading-8 text-slate-700">{brief.executive_summary}</p>
      </header>
      <MonitoringCoverageReceipt coverage={brief.coverage} />
      {brief.sections.length ? (
        brief.sections.map((section, index) => (
          <section
            aria-labelledby={`brief-section-${index}`}
            className="border-t border-slate-200 pt-8 first:border-t-0 first:pt-0"
            key={`${section.heading}-${index}`}
          >
            <h2 className="text-xl font-semibold" id={`brief-section-${index}`}>
              {section.heading}
            </h2>
            <p className="mt-3 leading-7 text-slate-700">{section.narrative}</p>
            <ol
              aria-label={`Evidence references for ${section.heading}`}
              className="mt-4 space-y-3 border-t border-slate-100 pt-4"
            >
              {section.references.map((reference, referenceIndex) => (
                <li
                  className="text-sm text-slate-600"
                  key={`${reference.finding_id}-${referenceIndex}`}
                >
                  <p>
                    <span aria-hidden="true">{referenceIndex + 1}. </span>
                    {reference.statement}
                  </p>
                  <Link
                    className="mt-1 inline-block font-medium text-blue-700 hover:underline"
                    href={`/findings/${reference.finding_id}`}
                  >
                    View the update and its evidence
                  </Link>
                </li>
              ))}
            </ol>
          </section>
        ))
      ) : (
        <section className="rounded-xl border border-dashed border-slate-300 p-8">
          <p className="eyebrow">Quiet week</p>
          <h2 className="mt-2 text-xl font-semibold">No important changes found this week</h2>
          <p className="mt-3 leading-7 text-slate-600">
            Scout published no accepted material changes for this period. This is a monitoring
            result, not a missing report; expand the coverage receipt to see what was checked and
            where coverage was incomplete.
          </p>
        </section>
      )}
      {!brief.sections.length && overview.data?.next_digest_at && me.data ? (
        <p className="text-sm text-slate-600">
          Next Weekly Digest:{" "}
          <time dateTime={overview.data.next_digest_at}>
            {formatUserDateTime(overview.data.next_digest_at, me.data.timezone)}
          </time>
        </p>
      ) : null}
      <Link
        className="text-sm font-medium text-blue-700 hover:underline"
        href={`/runs/${brief.scout_run_id}`}
      >
        View monitoring activity
      </Link>
    </article>
  );
}
