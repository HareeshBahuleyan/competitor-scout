import Link from "next/link";

import type { WeeklyBrief } from "@/lib/schemas";

type Coverage = WeeklyBrief["coverage"];

export function MonitoringCoverageReceipt({ coverage }: { coverage: Coverage }) {
  if (!coverage) {
    return (
      <section aria-labelledby="monitoring-coverage-heading" className="surface p-5">
        <p className="eyebrow">Coverage receipt</p>
        <h2 className="mt-1 font-semibold" id="monitoring-coverage-heading">
          Monitoring coverage
        </h2>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          Coverage details were not recorded for this historical digest. Current monitoring data is
          not used to reconstruct old results.
        </p>
      </section>
    );
  }

  return (
    <section aria-labelledby="monitoring-coverage-heading" className="surface p-5">
      <details>
        <summary className="cursor-pointer list-none">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="eyebrow">Coverage receipt</p>
              <h2 className="mt-1 font-semibold" id="monitoring-coverage-heading">
                Monitoring coverage
              </h2>
            </div>
            <p
              className={
                coverage.coverage_complete
                  ? "text-sm font-semibold text-emerald-700"
                  : "text-sm font-semibold text-amber-800"
              }
            >
              {coverage.coverage_complete ? "Complete coverage" : "Incomplete coverage"}
            </p>
          </div>
          {!coverage.coverage_complete ? (
            <p className="mt-3 text-sm leading-6 text-amber-900">
              Partial or failed scans mean this digest may not cover every monitored source.
            </p>
          ) : null}
        </summary>
        <div className="mt-4 space-y-5 border-t border-slate-100 pt-4">
          <p className="text-sm leading-6 text-slate-600">
            This immutable receipt records completed work when the digest was published. Inspected
            sources count URLs found in validated output from successful research tasks, not planned
            scope.
          </p>
          <dl className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-xl bg-slate-50 p-3">
              <dt className="text-xs font-medium text-slate-500">Completed scans</dt>
              <dd className="mt-1 text-xl font-semibold">{coverage.completed_scan_count}</dd>
            </div>
            <div className="rounded-xl bg-slate-50 p-3">
              <dt className="text-xs font-medium text-slate-500">Sources inspected</dt>
              <dd className="mt-1 text-xl font-semibold">{coverage.inspected_source_count}</dd>
            </div>
            <div className="rounded-xl bg-slate-50 p-3">
              <dt className="text-xs font-medium text-slate-500">Partial scans</dt>
              <dd className="mt-1 text-xl font-semibold">{coverage.partial_scan_count}</dd>
            </div>
            <div className="rounded-xl bg-slate-50 p-3">
              <dt className="text-xs font-medium text-slate-500">Failed scans</dt>
              <dd className="mt-1 text-xl font-semibold">{coverage.failed_scan_count}</dd>
            </div>
          </dl>
          <div>
            <h3 className="text-sm font-semibold">Competitors covered</h3>
            {coverage.competitors.length ? (
              <ul className="mt-2 flex flex-wrap gap-2">
                {coverage.competitors.map((competitor) => (
                  <li key={competitor.competitor_id}>
                    <Link
                      className="inline-flex rounded-full bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-200"
                      href={`/competitors/${competitor.competitor_id}#starting-snapshot`}
                    >
                      {competitor.competitor_name}
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-2 text-sm text-slate-600">No qualifying scans were recorded.</p>
            )}
          </div>
        </div>
      </details>
    </section>
  );
}
