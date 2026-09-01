"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { FindingCard } from "@/components/FindingCard";
import { LoadingState } from "@/components/ui/LoadingState";
import { apiGetClient } from "@/lib/api";
import {
  competitorPageSchema,
  findingPageSchema,
  runPageSchema,
  weeklyBriefPageSchema,
  type Run,
} from "@/lib/schemas";

const COMPETITOR_LIMIT = 10;

function errorText(error: unknown) {
  return error instanceof Error ? error.message : "Something went wrong.";
}

function latestRunFor(competitorId: string, runs: Run[]) {
  return runs
    .filter((run) => run.competitor_id === competitorId)
    .sort((left, right) => right.created_at.localeCompare(left.created_at))[0];
}

export function DashboardView() {
  const competitors = useQuery({
    queryKey: ["dashboard", "competitors"],
    queryFn: () => apiGetClient("/api/v1/competitors?limit=100", competitorPageSchema),
  });
  const criticalFindings = useQuery({
    queryKey: ["dashboard", "findings", "critical"],
    queryFn: () =>
      apiGetClient("/api/v1/findings?significance=critical&limit=5", findingPageSchema),
  });
  const highFindings = useQuery({
    queryKey: ["dashboard", "findings", "high"],
    queryFn: () => apiGetClient("/api/v1/findings?significance=high&limit=5", findingPageSchema),
  });
  const mediumFindings = useQuery({
    queryKey: ["dashboard", "findings", "medium"],
    queryFn: () => apiGetClient("/api/v1/findings?significance=medium&limit=5", findingPageSchema),
  });
  const runs = useQuery({
    queryKey: ["dashboard", "runs"],
    queryFn: () => apiGetClient("/api/v1/runs?limit=25", runPageSchema),
  });
  const briefs = useQuery({
    queryKey: ["dashboard", "briefs"],
    queryFn: () => apiGetClient("/api/v1/briefs?limit=1", weeklyBriefPageSchema),
  });

  const queries = [competitors, criticalFindings, highFindings, mediumFindings, runs, briefs];
  if (queries.some((query) => query.isPending)) {
    return <LoadingState label="Loading dashboard…" rows={5} />;
  }
  const failed = queries.find((query) => query.isError);
  if (failed)
    return (
      <p className="text-red-700" role="alert">
        {errorText(failed.error)}
      </p>
    );

  const competitorPage = competitors.data;
  const criticalFindingPage = criticalFindings.data;
  const highFindingPage = highFindings.data;
  const mediumFindingPage = mediumFindings.data;
  const runPage = runs.data;
  const briefPage = briefs.data;
  if (
    !competitorPage ||
    !criticalFindingPage ||
    !highFindingPage ||
    !mediumFindingPage ||
    !runPage ||
    !briefPage
  ) {
    return (
      <p className="text-red-700" role="alert">
        Dashboard data is unavailable.
      </p>
    );
  }

  const activeCompetitors = competitorPage.items.filter((item) => item.status === "active");
  const materialFindings = [
    ...criticalFindingPage.items,
    ...highFindingPage.items,
    ...mediumFindingPage.items,
  ]
    .sort((left, right) => right.published_at.localeCompare(left.published_at))
    .slice(0, 10);
  const unhealthyRuns = runPage.items.filter(
    (run) => run.status === "partial" || run.status === "failed",
  );
  const latestBrief = briefPage.items[0];

  return (
    <section className="space-y-9">
      <header className="flex flex-wrap items-end justify-between gap-5">
        <div>
          <p className="eyebrow">Intelligence overview</p>
          <h1 className="mt-1.5 text-4xl font-semibold">Dashboard</h1>
          <p className="mt-2 max-w-2xl text-slate-600">
            The signals that matter, without the noise.
          </p>
        </div>
        <Link
          className="inline-flex min-h-10 items-center gap-2 rounded-xl bg-[#d34d50] px-4 py-2.5 text-sm font-semibold text-white shadow-[0_5px_14px_rgba(185,62,66,0.2)] transition hover:bg-[#b93e42]"
          href="/competitors/new"
        >
          <span aria-hidden="true" className="text-lg leading-none">
            +
          </span>
          Add competitor
        </Link>
      </header>

      <div className="grid gap-3 sm:grid-cols-3">
        <article className="surface p-4">
          <p className="text-xs font-medium text-slate-500">Active monitors</p>
          <div className="mt-2 flex items-end justify-between gap-3">
            <p className="text-3xl font-semibold tracking-[-0.04em]">{activeCompetitors.length}</p>
            <span className="mb-1 flex items-center gap-1.5 text-xs text-emerald-700">
              <span className="size-1.5 rounded-full bg-emerald-500" /> Live
            </span>
          </div>
        </article>
        <article className="surface p-4">
          <p className="text-xs font-medium text-slate-500">Material signals</p>
          <div className="mt-2 flex items-end justify-between gap-3">
            <p className="text-3xl font-semibold tracking-[-0.04em]">{materialFindings.length}</p>
            <span className="mb-1 text-xs text-slate-500">Latest view</span>
          </div>
        </article>
        <article className="surface p-4">
          <p className="text-xs font-medium text-slate-500">Runs to review</p>
          <div className="mt-2 flex items-end justify-between gap-3">
            <p className="text-3xl font-semibold tracking-[-0.04em]">{unhealthyRuns.length}</p>
            <span
              className={`mb-1 text-xs ${unhealthyRuns.length ? "text-amber-700" : "text-slate-500"}`}
            >
              {unhealthyRuns.length ? "Needs attention" : "All clear"}
            </span>
          </div>
        </article>
      </div>

      {unhealthyRuns.length ? (
        <section
          aria-labelledby="run-warnings-heading"
          className="flex gap-3 rounded-xl border border-amber-200 bg-amber-50/70 p-4"
          role="alert"
        >
          <span aria-hidden="true" className="mt-0.5 text-amber-700">
            ●
          </span>
          <div>
            <h2 className="font-semibold text-amber-950" id="run-warnings-heading">
              Run health needs attention
            </h2>
            <ul className="mt-1.5 space-y-1 text-sm text-amber-900">
              {unhealthyRuns.map((run) => (
                <li key={run.id}>
                  <Link className="font-semibold capitalize underline" href={`/runs/${run.id}`}>
                    {run.status} run
                  </Link>
                  {run.failure_summary ? `: ${run.failure_summary}` : null}
                  {run.partial_reasons.length ? `: ${run.partial_reasons.join("; ")}` : null}
                </li>
              ))}
            </ul>
          </div>
        </section>
      ) : null}

      <div className="grid items-start gap-7 lg:grid-cols-[minmax(0,1.7fr)_minmax(16rem,0.8fr)]">
        <section aria-labelledby="latest-findings-heading" className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="eyebrow">Signal feed</p>
              <h2 className="mt-1 text-xl font-semibold" id="latest-findings-heading">
                Latest findings
              </h2>
            </div>
            <Link className="section-link" href="/findings">
              View all →
            </Link>
          </div>
          {materialFindings.length ? (
            <div className="space-y-3">
              {materialFindings.map((item) => (
                <FindingCard finding={item} key={item.id} />
              ))}
            </div>
          ) : (
            <p className="empty-state p-6">No material findings yet.</p>
          )}
        </section>

        <div className="space-y-6">
          <section aria-labelledby="active-competitors-heading" className="surface overflow-hidden">
            <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
              <h2 className="font-semibold" id="active-competitors-heading">
                Watching
              </h2>
              <Link className="section-link" href="/competitors">
                Manage
              </Link>
            </div>
            {activeCompetitors.length ? (
              <ul className="divide-y divide-slate-100">
                {activeCompetitors.map((competitor) => {
                  const latestRun = latestRunFor(competitor.id, runPage.items);
                  return (
                    <li className="px-5 py-3.5" key={competitor.id}>
                      <div className="flex items-center justify-between gap-3">
                        <Link
                          className="min-w-0 truncate text-sm font-semibold hover:text-[#b93e42]"
                          href={`/competitors/${competitor.id}`}
                        >
                          {competitor.name}
                        </Link>
                        <span className="inline-flex shrink-0 items-center gap-1.5 text-[11px] capitalize text-slate-500">
                          <span className="size-1.5 rounded-full bg-emerald-500" />
                          {latestRun?.status ?? "Not run yet"}
                        </span>
                      </div>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="p-5 text-sm text-slate-600">No active competitors yet.</p>
            )}
            <div className="border-t border-slate-100 bg-slate-50/60 px-5 py-4">
              <div className="flex items-center justify-between gap-3 text-xs text-slate-500">
                <span>Monitoring capacity</span>
                <span>
                  {competitorPage.items.length} of {COMPETITOR_LIMIT}
                </span>
              </div>
              <progress
                aria-label="Competitor slots used"
                className="mt-2 w-full"
                max={COMPETITOR_LIMIT}
                value={competitorPage.items.length}
              />
              <p className="sr-only">
                {competitorPage.items.length} of {COMPETITOR_LIMIT} competitor slots used
              </p>
            </div>
          </section>

          <section aria-labelledby="latest-brief-heading" className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold" id="latest-brief-heading">
                Weekly brief
              </h2>
              <Link className="section-link" href="/briefs">
                Archive
              </Link>
            </div>
            {latestBrief ? (
              <article className="surface p-5">
                <p className="eyebrow">Latest edition</p>
                <h3 className="mt-2 leading-snug">
                  <Link
                    className="font-semibold hover:text-[#b93e42]"
                    href={`/briefs/${latestBrief.id}`}
                  >
                    {latestBrief.title}
                  </Link>
                </h3>
                <p className="mt-2 line-clamp-4 text-sm leading-6 text-slate-600">
                  {latestBrief.executive_summary}
                </p>
              </article>
            ) : (
              <p className="empty-state p-5 text-sm">No weekly briefs yet.</p>
            )}
          </section>
        </div>
      </div>
    </section>
  );
}
