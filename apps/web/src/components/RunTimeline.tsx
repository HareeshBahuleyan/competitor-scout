import { formatUserDateTime } from "@/lib/dates";
import { partialReasonLabels } from "@/lib/runs";

export type RunStatus =
  "queued" | "planning" | "gathering" | "synthesizing" | "completed" | "partial" | "failed";

export type RunTimelineStep = {
  state: RunStatus;
  occurred_at: string;
};

export type RunUsage = {
  input_tokens?: number | null;
  output_tokens?: number | null;
  latency_ms?: number | null;
  settled_cost_usd?: string | null;
};

type RunTimelineProps = {
  failure_reason?: string | null;
  partial_reasons?: readonly string[];
  partial_summaries?: readonly string[];
  retry_count: number;
  status: RunStatus;
  steps: readonly RunTimelineStep[];
  usage?: RunUsage | null;
  timeZone?: string;
};

function humanize(value: string) {
  const words = value.replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function knownNumber(value: number | null | undefined) {
  return value == null ? "Unknown" : value.toLocaleString("en-US");
}

function knownCost(value: string | null | undefined) {
  if (value == null) {
    return "Unknown";
  }
  const amount = Number(value);
  return Number.isFinite(amount)
    ? new Intl.NumberFormat("en-US", { currency: "USD", style: "currency" }).format(amount)
    : "Unknown";
}

export function RunTimeline({
  failure_reason: failureReason,
  partial_reasons: partialReasons = [],
  partial_summaries: partialSummaries = [],
  retry_count: retryCount,
  status,
  steps,
  timeZone = "UTC",
  usage,
}: RunTimelineProps) {
  const orderedSteps = [...steps].sort(
    (first, second) => Date.parse(first.occurred_at) - Date.parse(second.occurred_at),
  );
  const latency = usage?.latency_ms == null ? "Unknown" : `${knownNumber(usage.latency_ms)} ms`;

  return (
    <section aria-labelledby="run-timeline-heading" className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold" id="run-timeline-heading">
          Scan timeline
        </h2>
        <span
          className={`rounded-full px-3 py-1 text-sm font-medium ${
            status === "failed"
              ? "bg-red-50 text-red-700"
              : status === "partial"
                ? "bg-amber-50 text-amber-800"
                : status === "completed"
                  ? "bg-emerald-50 text-emerald-700"
                  : "bg-slate-100 text-slate-700"
          }`}
        >
          {humanize(status)}
        </span>
      </div>

      <ol aria-label="Scan lifecycle" className="space-y-3 border-l-2 border-slate-200 pl-5">
        {orderedSteps.map((step, index) => (
          <li className="relative" key={`${step.state}-${step.occurred_at}-${index}`}>
            <span
              aria-hidden="true"
              className="absolute -left-[1.65rem] top-1.5 size-3 rounded-full bg-[var(--color-accent)]"
            />
            <p className="font-medium text-slate-950">{humanize(step.state)}</p>
            <time className="text-sm text-slate-500" dateTime={step.occurred_at}>
              {formatUserDateTime(step.occurred_at, timeZone)}
            </time>
          </li>
        ))}
      </ol>

      {partialReasons.length > 0 ? (
        <div>
          <h3 className="font-semibold">Partial scan reasons</h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
            {partialReasonLabels(partialReasons, partialSummaries).map((label) => (
              <li key={label}>{label}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {failureReason ? (
        <div>
          <h3 className="font-semibold">Failure reason</h3>
          <p className="mt-2 text-sm text-slate-700">{failureReason}</p>
        </div>
      ) : null}

      <details className="surface p-4">
        <summary className="cursor-pointer font-semibold text-slate-700">Usage details</summary>
        <div className="mt-4 grid gap-2 text-sm text-slate-700 sm:grid-cols-2 lg:grid-cols-3">
          <p>
            Retries<span>: {retryCount.toLocaleString("en-US")}</span>
          </p>
          <p>
            Input tokens<span>: {knownNumber(usage?.input_tokens)}</span>
          </p>
          <p>
            Output tokens<span>: {knownNumber(usage?.output_tokens)}</span>
          </p>
          <p>
            Latency<span>: {latency}</span>
          </p>
          <p>
            Settled cost<span>: {knownCost(usage?.settled_cost_usd)}</span>
          </p>
        </div>
      </details>
    </section>
  );
}
