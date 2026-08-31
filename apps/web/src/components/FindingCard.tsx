import Link from "next/link";

import type { Finding } from "@/lib/schemas";

export function FindingCard({ finding }: { finding: Finding }) {
  return (
    <article className="rounded-xl border border-slate-200 bg-white p-5">
      <div className="flex flex-wrap gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
        <span>{finding.category.replaceAll("_", " ")}</span>
        <span aria-hidden="true">·</span>
        <span>{finding.significance_level} significance</span>
        <span aria-hidden="true">·</span>
        <span>{Math.round(finding.confidence * 100)}% confidence</span>
      </div>
      <h2 className="mt-2 text-lg font-semibold">
        <Link className="hover:underline" href={`/findings/${finding.id}`}>{finding.title}</Link>
      </h2>
      <p className="mt-2 text-sm leading-6 text-slate-600">{finding.summary}</p>
      <time className="mt-3 block text-xs text-slate-500" dateTime={finding.published_at}>
        {new Date(finding.published_at).toLocaleString("en-US", { timeZone: "UTC" })}
      </time>
    </article>
  );
}
