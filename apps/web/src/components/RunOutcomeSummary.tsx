import { formatUserDateTime } from "@/lib/dates";
import type { Run } from "@/lib/schemas";

const runTypeLabels: Record<Run["run_type"], string> = {
  daily_scout: "Daily scan",
  manual_scout: "Manual scan",
  source_discovery: "Source discovery",
  weekly_brief: "Weekly brief",
};

const failureCopy: Record<string, { action?: string; summary: string }> = {
  competitor_inactive: {
    action: "Review monitor settings.",
    summary: "This monitor is not active.",
  },
  daily_cost_limit: {
    summary: "The daily usage limit was reached before this scan could finish.",
  },
  no_valid_evidence: {
    action: "Review the monitored sources and try again.",
    summary: "The scan could not verify any usable evidence.",
  },
};

export function runTypeLabel(runType: Run["run_type"]): string {
  return runTypeLabels[runType];
}

function humanize(value: string) {
  const words = value.replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function RunOutcomeSummary({ run, timeZone }: { run: Run; timeZone: string }) {
  const failure = run.failure_code ? failureCopy[run.failure_code] : undefined;
  const findingLabel = `${run.finding_count} finding${run.finding_count === 1 ? "" : "s"} published`;

  return (
    <section aria-labelledby="run-outcome-heading" className="surface space-y-4 p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="eyebrow">{run.competitor_name ?? "Account-wide"}</p>
          <h1 className="mt-1 text-4xl font-semibold" id="run-outcome-heading">
            {runTypeLabel(run.run_type)}
          </h1>
        </div>
        <span className="rounded-full bg-slate-100 px-3 py-1 text-sm font-semibold capitalize">
          {run.status}
        </span>
      </div>
      <dl className="grid gap-3 text-sm sm:grid-cols-2">
        <div>
          <dt className="font-medium text-slate-500">Started</dt>
          <dd>
            <time dateTime={run.scheduled_for}>
              {formatUserDateTime(run.scheduled_for, timeZone)}
            </time>
          </dd>
        </div>
        <div>
          <dt className="font-medium text-slate-500">Outcome</dt>
          <dd>{findingLabel}</dd>
        </div>
      </dl>
      {failure ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-900">
          <p className="font-semibold">{failure.summary}</p>
          {failure.action ? <p className="mt-1">{failure.action}</p> : null}
        </div>
      ) : run.partial_reasons.length ? (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
          <p className="font-semibold">The scan completed with some limitations.</p>
          <ul className="mt-2 list-disc pl-5">
            {run.partial_reasons.map((reason) => (
              <li key={reason}>{humanize(reason)}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
