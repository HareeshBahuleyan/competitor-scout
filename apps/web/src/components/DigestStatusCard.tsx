import Link from "next/link";

import { formatUserDateTime } from "@/lib/dates";
import type { DigestOverview } from "@/lib/schemas";

export function DigestStatusCard({
  overview,
  timeZone,
}: {
  overview: DigestOverview;
  timeZone: string;
}) {
  if (overview.state === "archive_available" && overview.latest_brief) {
    const latest = overview.latest_brief;
    return (
      <article className="surface surface-interactive card-target group p-5">
        <p className="eyebrow">Current digest</p>
        <h3 className="mt-2 leading-snug">
          <Link
            className="card-link font-semibold transition-colors group-hover:text-[var(--color-accent-strong)]"
            href={`/briefs/${latest.id}`}
          >
            {latest.title}
          </Link>
        </h3>
        <p className="mt-2 line-clamp-4 text-sm leading-6 text-slate-600">
          {latest.executive_summary}
        </p>
        {overview.next_digest_at ? (
          <p className="mt-3 text-xs text-slate-500">
            Next scheduled:{" "}
            <time dateTime={overview.next_digest_at}>
              {formatUserDateTime(overview.next_digest_at, timeZone)}
            </time>
          </p>
        ) : null}
      </article>
    );
  }

  if (overview.state === "setup_required") {
    return (
      <article className="surface p-5">
        <p className="eyebrow">Setup required</p>
        <h3 className="mt-2 font-semibold">Set up your first competitor</h3>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          Choose who to watch and which first-party sources Scout should trust.
        </p>
        <Link
          className="mt-4 inline-block font-semibold text-blue-700 hover:underline"
          href="/competitors/new"
        >
          Set up a competitor
        </Link>
      </article>
    );
  }

  if (overview.state === "setup_incomplete") {
    const competitor = overview.incomplete_competitor;
    const paused = competitor?.status === "paused";
    return (
      <article className="surface p-5">
        <p className="eyebrow">Setup incomplete</p>
        <h3 className="mt-2 font-semibold">
          {paused ? "Monitoring is paused" : "Finish setup to start Weekly Digests"}
        </h3>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          {paused
            ? "No future digest is scheduled until monitoring resumes. Published history remains available."
            : "Weekly Digests begin after at least one competitor has approved sources and active monitoring."}
        </p>
        {competitor ? (
          <Link
            className="mt-4 inline-block font-semibold text-blue-700 hover:underline"
            href={`/competitors/${competitor.competitor_id}`}
          >
            {paused
              ? `Resume ${competitor.competitor_name}`
              : `Finish ${competitor.competitor_name} setup`}
          </Link>
        ) : null}
      </article>
    );
  }

  if (overview.state === "initial_scan_running" && overview.running_scan) {
    return (
      <article className="surface p-5" role="status">
        <p className="eyebrow">First scan in progress</p>
        <h3 className="mt-2 font-semibold">
          Scout is reviewing {overview.running_scan.competitor_name}
        </h3>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          This scan establishes the Starting Snapshot. The first Weekly Digest will summarize later
          changes against that baseline.
        </p>
        <Link
          className="mt-4 inline-block font-semibold text-blue-700 hover:underline"
          href={`/runs/${overview.running_scan.run_id}`}
        >
          View scan progress
        </Link>
      </article>
    );
  }

  return (
    <article className="surface p-5">
      <p className="eyebrow">Monitoring is active</p>
      <h3 className="mt-2 font-semibold">Your first Weekly Digest is scheduled</h3>
      <p className="mt-2 text-sm leading-6 text-slate-600">
        Scout is monitoring {overview.active_competitor_count}{" "}
        {overview.active_competitor_count === 1 ? "competitor" : "competitors"} across{" "}
        {overview.approved_source_count} approved{" "}
        {overview.approved_source_count === 1 ? "source" : "sources"}.
      </p>
      {overview.next_digest_at ? (
        <p className="mt-3 text-sm font-semibold text-slate-800">
          Expected{" "}
          <time dateTime={overview.next_digest_at}>
            {formatUserDateTime(overview.next_digest_at, timeZone)}
          </time>
        </p>
      ) : null}
      {overview.monitoring_issue_count ? (
        <p className="mt-3 text-sm text-amber-900">
          {overview.monitoring_issue_count} monitoring{" "}
          {overview.monitoring_issue_count === 1 ? "issue may" : "issues may"} reduce first-digest
          coverage.
        </p>
      ) : null}
      {overview.snapshots.length ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {overview.snapshots.map((snapshot) => (
            <Link
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold hover:bg-slate-50"
              href={`/competitors/${snapshot.competitor_id}#starting-snapshot`}
              key={snapshot.snapshot_id}
            >
              View {snapshot.competitor_name} snapshot
            </Link>
          ))}
        </div>
      ) : (
        <Link
          className="mt-4 inline-block font-semibold text-blue-700 hover:underline"
          href="/competitors"
        >
          View competitors
        </Link>
      )}
    </article>
  );
}
