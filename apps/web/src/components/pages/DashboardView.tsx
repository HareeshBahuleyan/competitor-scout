"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { FindingCard } from "@/components/FindingCard";
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

  const queries = [competitors, highFindings, mediumFindings, runs, briefs];
  if (queries.some((query) => query.isPending)) return <p role="status">Loading dashboard…</p>;
  const failed = queries.find((query) => query.isError);
  if (failed)
    return (
      <p className="text-red-700" role="alert">
        {errorText(failed.error)}
      </p>
    );

  const competitorPage = competitors.data;
  const highFindingPage = highFindings.data;
  const mediumFindingPage = mediumFindings.data;
  const runPage = runs.data;
  const briefPage = briefs.data;
  if (!competitorPage || !highFindingPage || !mediumFindingPage || !runPage || !briefPage) {
    return (
      <p className="text-red-700" role="alert">
        Dashboard data is unavailable.
      </p>
    );
  }

  const activeCompetitors = competitorPage.items.filter((item) => item.status === "active");
  const materialFindings = [...highFindingPage.items, ...mediumFindingPage.items]
    .sort((left, right) => right.published_at.localeCompare(left.published_at))
    .slice(0, 10);
  const unhealthyRuns = runPage.items.filter(
    (run) => run.status === "partial" || run.status === "failed",
  );
  const latestBrief = briefPage.items[0];

  return (
    <section className="space-y-8">
      <header>
        <h1 className="text-3xl font-bold">Dashboard</h1>
        <p className="mt-1 text-slate-600">Your latest evidence-backed competitor intelligence.</p>
      </header>

      {unhealthyRuns.length ? (
        <section
          aria-labelledby="run-warnings-heading"
          className="rounded-xl border border-amber-300 bg-amber-50 p-5"
          role="alert"
        >
          <h2 className="font-semibold text-amber-950" id="run-warnings-heading">
            Run health needs attention
          </h2>
          <ul className="mt-2 space-y-2 text-sm text-amber-900">
            {unhealthyRuns.map((run) => (
              <li key={run.id}>
                <Link className="font-medium capitalize underline" href={`/runs/${run.id}`}>
                  {run.status} run
                </Link>
                {run.failure_summary ? `: ${run.failure_summary}` : null}
                {run.partial_reasons.length ? `: ${run.partial_reasons.join("; ")}` : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-3">
        <section aria-labelledby="active-competitors-heading" className="space-y-4 lg:col-span-2">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-xl font-semibold" id="active-competitors-heading">
              Active competitors
            </h2>
            <Link className="text-sm font-medium text-blue-700 hover:underline" href="/competitors">
              Manage competitors
            </Link>
          </div>
          {activeCompetitors.length ? (
            <ul className="grid gap-3 sm:grid-cols-2">
              {activeCompetitors.map((competitor) => {
                const latestRun = latestRunFor(competitor.id, runPage.items);
                return (
                  <li
                    className="rounded-xl border border-slate-200 bg-white p-4"
                    key={competitor.id}
                  >
                    <Link
                      className="font-semibold hover:underline"
                      href={`/competitors/${competitor.id}`}
                    >
                      {competitor.name}
                    </Link>
                    <p className="mt-2 text-sm text-slate-600">
                      Latest run:{" "}
                      <span className="capitalize">{latestRun?.status ?? "Not run yet"}</span>
                    </p>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="rounded-xl border border-dashed border-slate-300 p-6 text-slate-600">
              No active competitors yet.
            </p>
          )}
        </section>

        <aside
          aria-labelledby="capacity-heading"
          className="rounded-xl border border-slate-200 bg-white p-5"
        >
          <h2 className="text-xl font-semibold" id="capacity-heading">
            Monitoring capacity
          </h2>
          <p className="mt-3 text-slate-700">
            {competitorPage.items.length} of {COMPETITOR_LIMIT} competitor slots used
          </p>
          <progress
            aria-label="Competitor slots used"
            className="mt-4 w-full"
            max={COMPETITOR_LIMIT}
            value={competitorPage.items.length}
          />
        </aside>
      </div>

      <section aria-labelledby="latest-findings-heading" className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-xl font-semibold" id="latest-findings-heading">
            Latest high and medium findings
          </h2>
          <Link className="text-sm font-medium text-blue-700 hover:underline" href="/findings">
            View all findings
          </Link>
        </div>
        {materialFindings.length ? (
          <div className="space-y-3">
            {materialFindings.map((item) => (
              <FindingCard finding={item} key={item.id} />
            ))}
          </div>
        ) : (
          <p className="rounded-xl border border-dashed border-slate-300 p-6 text-slate-600">
            No material findings yet.
          </p>
        )}
      </section>

      <section aria-labelledby="latest-brief-heading" className="space-y-3">
        <h2 className="text-xl font-semibold" id="latest-brief-heading">
          Latest weekly brief
        </h2>
        {latestBrief ? (
          <article className="rounded-xl border border-slate-200 bg-white p-5">
            <h3>
              <Link className="font-semibold hover:underline" href={`/briefs/${latestBrief.id}`}>
                {latestBrief.title}
              </Link>
            </h3>
            <p className="mt-2 text-slate-600">{latestBrief.executive_summary}</p>
          </article>
        ) : (
          <p className="rounded-xl border border-dashed border-slate-300 p-6 text-slate-600">
            No weekly briefs yet.
          </p>
        )}
      </section>
    </section>
  );
}
