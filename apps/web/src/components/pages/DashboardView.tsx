"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { CompetitorFavicon } from "@/components/CompetitorFavicon";
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
  const router = useRouter();
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
  useEffect(() => {
    if (competitors.data?.items.length === 0) {
      router.replace("/competitors/new?first=1");
    }
  }, [competitors.data?.items.length, router]);

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
  if (competitorPage.items.length === 0) {
    return <p role="status">Taking you to guided setup…</p>;
  }

  const activeCompetitors = competitorPage.items.filter((item) => item.status === "active");
  const materialFindings = [
    ...criticalFindingPage.items,
    ...highFindingPage.items,
    ...mediumFindingPage.items,
  ]
    .sort((left, right) => right.published_at.localeCompare(left.published_at))
    .slice(0, 10);
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

      <div className="grid items-start gap-7 lg:grid-cols-[minmax(0,1.7fr)_minmax(16rem,0.8fr)]">
        <section aria-labelledby="latest-findings-heading" className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="eyebrow">Signal feed</p>
              <h2 className="mt-1 text-xl font-semibold" id="latest-findings-heading">
                Latest updates
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
            <p className="empty-state p-6">No material updates yet.</p>
          )}
        </section>

        <div className="space-y-6">
          <section aria-labelledby="active-competitors-heading" className="surface overflow-hidden">
            <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
              <h2 className="font-semibold" id="active-competitors-heading">
                Watching
              </h2>
              <Link className="section-link" href="/competitors">
                Manage <span aria-hidden="true">→</span>
              </Link>
            </div>
            {activeCompetitors.length ? (
              <ul className="divide-y divide-slate-100">
                {activeCompetitors.map((competitor) => {
                  const latestRun = latestRunFor(competitor.id, runPage.items);
                  return (
                    <li
                      className="card-target group px-5 py-3.5 transition-colors hover:bg-[var(--color-accent-soft)]/40"
                      key={competitor.id}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="flex min-w-0 items-center gap-2.5">
                          <CompetitorFavicon
                            domain={competitor.primary_domain}
                            name={competitor.name}
                            size="sm"
                          />
                          <Link
                            className="card-link min-w-0 truncate text-sm font-semibold transition-colors group-hover:text-[var(--color-accent-strong)]"
                            href={`/competitors/${competitor.id}`}
                          >
                            {competitor.name}
                          </Link>
                        </div>
                        <span className="inline-flex shrink-0 items-center gap-1.5 text-[11px] capitalize text-slate-500">
                          <span className="size-1.5 rounded-full bg-[var(--color-success)]" />
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
                Weekly Digest
              </h2>
              <Link className="section-link" href="/briefs">
                Archive <span aria-hidden="true">→</span>
              </Link>
            </div>
            {latestBrief ? (
              <article className="surface surface-interactive card-target group p-5">
                <p className="eyebrow">Latest edition</p>
                <h3 className="mt-2 leading-snug">
                  <Link
                    className="card-link font-semibold transition-colors group-hover:text-[var(--color-accent-strong)]"
                    href={`/briefs/${latestBrief.id}`}
                  >
                    {latestBrief.title}
                  </Link>
                </h3>
                <p className="mt-2 line-clamp-4 text-sm leading-6 text-slate-600">
                  {latestBrief.executive_summary}
                </p>
                <p className="mt-3 text-xs font-semibold text-[var(--color-accent-strong)]">
                  Read the digest
                  <span
                    aria-hidden="true"
                    className="ml-1 inline-block transition-transform group-hover:translate-x-0.5"
                  >
                    →
                  </span>
                </p>
              </article>
            ) : (
              <p className="empty-state p-5 text-sm">No Weekly Digest yet.</p>
            )}
          </section>
        </div>
      </div>
    </section>
  );
}
