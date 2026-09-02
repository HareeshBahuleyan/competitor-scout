import Link from "next/link";

import { formatUserDateTime } from "@/lib/dates";
import type { Finding } from "@/lib/schemas";

export function FindingCard({
  finding,
  timeZone = "UTC",
}: {
  finding: Finding;
  timeZone?: string;
}) {
  return (
    <article className="surface surface-interactive card-target group p-5">
      <div className="flex items-start gap-4">
        <span
          aria-hidden="true"
          className={`mt-1.5 size-2.5 shrink-0 rounded-full ${
            finding.significance_level === "critical"
              ? "bg-[var(--color-danger)]"
              : finding.significance_level === "high"
                ? "bg-[#d34d50]"
                : finding.significance_level === "medium"
                  ? "bg-amber-500"
                  : "bg-slate-300"
          }`}
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">
            <span>{finding.category.replaceAll("_", " ")}</span>
            <span aria-hidden="true" className="text-slate-300">
              /
            </span>
            <span>{finding.significance_level} significance</span>
          </div>
          <h2 className="mt-1.5 text-[17px] font-semibold leading-snug">
            <Link
              className="card-link transition-colors group-hover:text-[var(--color-accent-strong)]"
              href={`/findings/${finding.id}`}
            >
              {finding.title}
            </Link>
          </h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">{finding.summary}</p>
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-500">
            <span className="rounded-full bg-slate-100 px-2 py-1 font-medium">
              {Math.round(finding.confidence * 100)}% confidence
            </span>
            <time dateTime={finding.published_at}>
              {formatUserDateTime(finding.published_at, timeZone)}
            </time>
            <span className="ml-auto font-semibold text-[var(--color-accent-strong)]">
              View update
              <span
                aria-hidden="true"
                className="ml-1 inline-block transition-transform group-hover:translate-x-0.5"
              >
                →
              </span>
            </span>
          </div>
        </div>
      </div>
    </article>
  );
}
