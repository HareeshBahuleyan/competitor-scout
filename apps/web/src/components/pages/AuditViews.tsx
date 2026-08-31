"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { EvidenceList } from "@/components/EvidenceList";
import { FindingCard } from "@/components/FindingCard";
import { RunTimeline, type RunTimelineStep } from "@/components/RunTimeline";
import { apiGetClient } from "@/lib/api";
import {
  agentTaskPageSchema,
  findingEvidencePageSchema,
  findingPageSchema,
  findingSchema,
  runPageSchema,
  runSchema,
  runUsageSchema,
  type Run,
} from "@/lib/schemas";

export type FindingFilters = {
  category?: string;
  competitor_id?: string;
  confidence_min?: string;
  published_from?: string;
  published_to?: string;
  significance?: string;
};

function errorText(error: unknown) {
  return error instanceof Error ? error.message : "Something went wrong.";
}

function queryString(filters: FindingFilters) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (!value) continue;
    if (key === "published_from" && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
      params.set(key, `${value}T00:00:00Z`);
    } else if (key === "published_to" && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
      params.set(key, `${value}T23:59:59.999Z`);
    } else {
      params.set(key, value);
    }
  }
  const encoded = params.toString();
  return encoded ? `?${encoded}` : "";
}

const categories = ["", "pricing", "product", "feature", "positioning", "integration", "customer_win", "partnership", "leadership", "hiring", "market_expansion", "other"];
const significance = ["", "low", "medium", "high", "critical"];

export function FindingsListView({ initialFilters }: { initialFilters: FindingFilters }) {
  const suffix = queryString(initialFilters);
  const query = useQuery({
    queryKey: ["findings", suffix],
    queryFn: () => apiGetClient(`/api/v1/findings${suffix}`, findingPageSchema),
  });

  return (
    <section className="space-y-6">
      <div><h1 className="text-3xl font-bold">Findings</h1><p className="mt-1 text-slate-600">Evidence-backed competitive changes.</p></div>
      <form action="/findings" className="grid gap-3 rounded-xl border border-slate-200 bg-white p-4 sm:grid-cols-3" method="get">
        <label className="text-sm font-medium">Competitor ID
          <input className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2" defaultValue={initialFilters.competitor_id ?? ""} name="competitor_id" type="text" />
        </label>
        <label className="text-sm font-medium">Category
          <select className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2" defaultValue={initialFilters.category ?? ""} name="category">
            {categories.map((value) => <option key={value} value={value}>{value ? value.replaceAll("_", " ") : "All categories"}</option>)}
          </select>
        </label>
        <label className="text-sm font-medium">Significance
          <select className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2" defaultValue={initialFilters.significance ?? ""} name="significance">
            {significance.map((value) => <option key={value} value={value}>{value || "All levels"}</option>)}
          </select>
        </label>
        <label className="text-sm font-medium">Minimum confidence
          <input className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2" defaultValue={initialFilters.confidence_min ?? ""} max="1" min="0" name="confidence_min" step="0.05" type="number" />
        </label>
        <label className="text-sm font-medium">Published from
          <input className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2" defaultValue={initialFilters.published_from ?? ""} name="published_from" type="date" />
        </label>
        <label className="text-sm font-medium">Published to
          <input className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2" defaultValue={initialFilters.published_to ?? ""} name="published_to" type="date" />
        </label>
        <button className="rounded-lg bg-slate-950 px-4 py-2 font-medium text-white sm:col-span-3 sm:justify-self-start" type="submit">Apply filters</button>
      </form>
      {query.isPending ? <p role="status">Loading findings…</p> : null}
      {query.isError ? <p className="text-red-700" role="alert">{errorText(query.error)}</p> : null}
      {query.data?.items.length === 0 ? <p className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-slate-600">No findings match these filters.</p> : null}
      {query.data?.items.length ? <div className="space-y-4">{query.data.items.map((finding) => <FindingCard finding={finding} key={finding.id} />)}</div> : null}
    </section>
  );
}

export function FindingDetailView({ findingId }: { findingId: string }) {
  const finding = useQuery({ queryKey: ["finding", findingId], queryFn: () => apiGetClient(`/api/v1/findings/${findingId}`, findingSchema) });
  const evidence = useQuery({ queryKey: ["finding-evidence", findingId], queryFn: () => apiGetClient(`/api/v1/findings/${findingId}/evidence`, findingEvidencePageSchema) });
  if (finding.isPending || evidence.isPending) return <p role="status">Loading finding…</p>;
  if (finding.isError || evidence.isError) return <p className="text-red-700" role="alert">{errorText(finding.error ?? evidence.error)}</p>;
  return (
    <article className="space-y-8">
      <header className="space-y-3">
        <p className="text-sm font-semibold uppercase tracking-wide text-slate-500">{finding.data.category.replaceAll("_", " ")} · {finding.data.significance_level}</p>
        <h1 className="text-3xl font-bold">{finding.data.title}</h1>
        <p className="text-lg text-slate-700">{finding.data.summary}</p>
        <p className="text-sm text-slate-600">Confidence: {Math.round(finding.data.confidence * 100)}%</p>
      </header>
      <section className="rounded-xl border border-slate-200 bg-white p-5" aria-labelledby="significance-heading">
        <h2 className="text-xl font-semibold" id="significance-heading">Why it matters</h2>
        <p className="mt-2 text-slate-700">{finding.data.significance_explanation}</p>
        <h3 className="mt-4 font-semibold">Decision rationale</h3><p className="mt-1 text-sm text-slate-600">{finding.data.decision_rationale}</p>
        <Link className="mt-4 inline-block text-sm font-medium text-blue-700 hover:underline" href={`/runs/${finding.data.originating_scout_run_id}`}>Originating run</Link>
      </section>
      {evidence.data.items.length ? <EvidenceList evidence={evidence.data.items} /> : <p>No evidence is available.</p>}
    </article>
  );
}

function runLabel(value: string) { return value.replaceAll("_", " "); }

export function RunsListView() {
  const query = useQuery({ queryKey: ["runs"], queryFn: () => apiGetClient("/api/v1/runs", runPageSchema) });
  return (
    <section className="space-y-6">
      <div><h1 className="text-3xl font-bold">Runs</h1><p className="mt-1 text-slate-600">Scout execution history and audit status.</p></div>
      {query.isPending ? <p role="status">Loading runs…</p> : null}
      {query.isError ? <p className="text-red-700" role="alert">{errorText(query.error)}</p> : null}
      {query.data?.items.length === 0 ? <p className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-slate-600">No runs yet.</p> : null}
      {query.data?.items.length ? <ul className="space-y-3">{query.data.items.map((run) => (
        <li className="rounded-xl border border-slate-200 bg-white p-5" key={run.id}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <Link className="font-semibold capitalize hover:underline" href={`/runs/${run.id}`}>{runLabel(run.run_type)} run</Link>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-sm capitalize">{run.status}</span>
          </div>
          <time className="mt-2 block text-sm text-slate-500" dateTime={run.created_at}>{new Date(run.created_at).toLocaleString("en-US", { timeZone: "UTC" })}</time>
        </li>
      ))}</ul> : null}
    </section>
  );
}

function lifecycle(run: Run): RunTimelineStep[] {
  if (run.lifecycle?.length) return run.lifecycle;
  const steps: RunTimelineStep[] = [{ state: "queued", occurred_at: run.created_at }];
  if (run.started_at) steps.push({ state: "planning", occurred_at: run.started_at });
  if (run.completed_at) steps.push({ state: run.status, occurred_at: run.completed_at });
  return steps;
}

export function RunDetailView({ runId }: { runId: string }) {
  const run = useQuery({ queryKey: ["run", runId], queryFn: () => apiGetClient(`/api/v1/runs/${runId}`, runSchema) });
  const tasks = useQuery({ queryKey: ["run-tasks", runId], queryFn: () => apiGetClient(`/api/v1/runs/${runId}/tasks`, agentTaskPageSchema) });
  const usage = useQuery({ queryKey: ["run-usage", runId], queryFn: () => apiGetClient(`/api/v1/runs/${runId}/usage`, runUsageSchema) });
  if (run.isPending || tasks.isPending || usage.isPending) return <p role="status">Loading run…</p>;
  if (run.isError || tasks.isError || usage.isError) return <p className="text-red-700" role="alert">{errorText(run.error ?? tasks.error ?? usage.error)}</p>;
  const retries = tasks.data.items.reduce((total, task) => total + Math.max(0, task.attempt_count - 1), 0);
  return (
    <article className="space-y-8">
      <header><p className="text-sm font-semibold uppercase tracking-wide text-slate-500">{run.data.status}</p><h1 className="mt-2 text-3xl font-bold capitalize">{runLabel(run.data.run_type)} run</h1></header>
      <RunTimeline failure_reason={run.data.failure_summary} partial_reasons={run.data.partial_reasons} retry_count={retries} status={run.data.status} steps={lifecycle(run.data)} usage={usage.data} />
      <section aria-labelledby="tasks-heading" className="space-y-3">
        <h2 className="text-xl font-semibold" id="tasks-heading">Agent tasks</h2>
        {tasks.data.items.length === 0 ? <p>No task records are available.</p> : <ul className="space-y-3">{tasks.data.items.map((task) => (
          <li className="rounded-xl border border-slate-200 bg-white p-5" id={`task-${task.id}`} key={task.id}>
            <div className="flex flex-wrap justify-between gap-2"><h3 className="font-semibold">{task.objective}</h3><span className="text-sm capitalize text-slate-600">{task.status}</span></div>
            <p className="mt-2 text-sm text-slate-600">{task.role.replaceAll("_", " ")} · Attempts: {task.attempt_count}</p>
            {task.source_scope.length ? <ul className="mt-3 list-disc pl-5 text-sm text-slate-600">{task.source_scope.map((source) => <li key={source}>{source}</li>)}</ul> : null}
            {task.validated_output ? <pre className="mt-3 overflow-auto rounded-lg bg-slate-100 p-3 text-xs">{JSON.stringify(task.validated_output, null, 2)}</pre> : null}
            {task.error_summary ? <p className="mt-3 text-sm text-red-700">{task.error_summary}</p> : null}
          </li>
        ))}</ul>}
      </section>
    </article>
  );
}
