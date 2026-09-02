import { formatUserDateTime } from "@/lib/dates";
import { partialReasonLabels } from "@/lib/runs";
import type { Run } from "@/lib/schemas";

const runTypeLabels: Record<Run["run_type"], string> = {
  daily_scout: "Daily scan",
  manual_scout: "Manual scan",
  source_discovery: "Source discovery",
  weekly_brief: "Weekly Digest",
};

const failureActions: Record<string, string> = {
  competitor_inactive: "Review the monitor settings before trying again.",
  no_valid_evidence: "Review the monitored sources before trying again.",
};

export function runTypeLabel(runType: Run["run_type"]): string {
  return runTypeLabels[runType];
}

export function RunOutcomeSummary({ run, timeZone }: { run: Run; timeZone: string }) {
  const failureAction = run.failure_code ? failureActions[run.failure_code] : undefined;
  const partialLabels = partialReasonLabels(run.partial_reasons, run.partial_summaries);
  const findingLabel = `${run.finding_count} update${run.finding_count === 1 ? "" : "s"} published`;
  const outcomeTime = run.started_at ?? run.scheduled_for;

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
          <dt className="font-medium text-slate-500">{run.started_at ? "Started" : "Scheduled"}</dt>
          <dd>
            <time dateTime={outcomeTime}>{formatUserDateTime(outcomeTime, timeZone)}</time>
          </dd>
        </div>
        <div>
          <dt className="font-medium text-slate-500">Outcome</dt>
          <dd>{findingLabel}</dd>
        </div>
      </dl>
      {run.failure_summary ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-900">
          <p className="font-semibold">{run.failure_summary}</p>
          {failureAction ? <p className="mt-1">{failureAction}</p> : null}
        </div>
      ) : partialLabels.length ? (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
          <p className="font-semibold">The scan completed with some limitations.</p>
          <ul className="mt-2 list-disc pl-5">
            {partialLabels.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
