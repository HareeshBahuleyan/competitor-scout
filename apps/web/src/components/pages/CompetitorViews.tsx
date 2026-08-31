"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { CompetitorForm, type CompetitorFormValues } from "@/components/CompetitorForm";
import { FindingCard } from "@/components/FindingCard";
import { SourceApprovalList } from "@/components/SourceApprovalList";
import { apiGetClient, apiMutate } from "@/lib/api";
import {
  competitorPageSchema, competitorSchema, findingPageSchema, meSchema, runPageSchema, runSchema,
  sourceDiscoveryResponseSchema, sourcePageSchema, sourceSchema, type Competitor,
  type CursorPage, type Source,
} from "@/lib/schemas";

function errorText(error: unknown) {
  if (typeof error === "object" && error && "status" in error && (error.status === 409 || error.status === 422)) {
    return "Competitor limit reached. Remove a competitor before adding another.";
  }
  return error instanceof Error ? error.message : "Something went wrong.";
}

export function CompetitorsListView() {
  const query = useQuery({ queryKey: ["competitors"], queryFn: () => apiGetClient("/api/v1/competitors", competitorPageSchema) });
  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div><h1 className="text-3xl font-bold">Competitors</h1><p className="mt-1 text-slate-600">Companies monitored by your scout.</p></div>
        <Link className="rounded-lg bg-slate-950 px-4 py-2 font-medium text-white" href="/competitors/new">Add competitor</Link>
      </div>
      {query.isPending ? <p role="status">Loading competitors…</p> : null}
      {query.isError ? <p className="text-red-700" role="alert">{errorText(query.error)}</p> : null}
      {query.data?.items.length === 0 ? <p className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-slate-600">No competitors yet.</p> : null}
      {query.data?.items.length ? <ul className="grid gap-4 md:grid-cols-2">{query.data.items.map((item) => (
        <li className="rounded-xl border border-slate-200 bg-white p-5" key={item.id}>
          <div className="flex justify-between gap-3"><h2 className="font-semibold"><Link className="hover:underline" href={`/competitors/${item.id}`}>{item.name}</Link></h2><span className="text-sm capitalize text-slate-500">{item.status}</span></div>
          <p className="mt-2 text-sm text-slate-600">{item.description || item.primary_domain}</p>
        </li>
      ))}</ul> : null}
    </section>
  );
}

type NewCompetitorViewProps = { pollIntervalMs?: number };
const terminalStatuses = new Set(["completed", "partial", "failed"]);

export function NewCompetitorView({ pollIntervalMs = 1_000 }: NewCompetitorViewProps) {
  const client = useQueryClient();
  const [created, setCreated] = useState<Competitor | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [pendingSourceId, setPendingSourceId] = useState<string | null>(null);
  const [sourceError, setSourceError] = useState<unknown>(null);
  const me = useQuery({ queryKey: ["me"], queryFn: () => apiGetClient("/api/v1/me", meSchema) });
  const discovery = useMutation({
    mutationFn: async (competitorId: string) => {
      if (!me.data) throw new Error("Account information is unavailable.");
      const result = await apiMutate(`/api/v1/competitors/${competitorId}/discover-sources`, {
        csrfToken: me.data.csrf_token,
        method: "POST",
      }, sourceDiscoveryResponseSchema);
      if (!result) throw new Error("The discovery response was empty.");
      return result;
    },
    onSuccess: (result) => setRunId(result.run_id),
  });
  const create = useMutation({
    mutationFn: async (values: CompetitorFormValues) => {
      if (!me.data) throw new Error("Account information is unavailable.");
      const result = await apiMutate("/api/v1/competitors", {
        body: values,
        csrfToken: me.data.csrf_token,
        method: "POST",
      }, competitorSchema);
      if (!result) throw new Error("The competitor response was empty.");
      return result;
    },
    onSuccess: (result) => {
      setCreated(result);
      void client.invalidateQueries({ queryKey: ["competitors"] });
      discovery.mutate(result.id);
    },
  });
  const run = useQuery({
    enabled: Boolean(runId), queryKey: ["run", runId],
    queryFn: () => apiGetClient(`/api/v1/runs/${runId}`, runSchema),
    refetchInterval: (query) => terminalStatuses.has(query.state.data?.status ?? "")
      ? false : Math.min(pollIntervalMs * 2 ** query.state.dataUpdateCount, 10_000),
  });
  const canLoadSources = Boolean(created && run.data && (run.data.status === "completed" || run.data.status === "partial"));
  const sources = useQuery({
    enabled: canLoadSources, queryKey: ["competitor-sources", created?.id],
    queryFn: () => apiGetClient(`/api/v1/competitors/${created?.id}/sources`, sourcePageSchema),
  });
  const activate = useMutation({
    mutationFn: async () => {
      if (!created || !me.data) throw new Error("Account information is unavailable.");
      return apiMutate(`/api/v1/competitors/${created.id}`, { body: { status: "active" }, csrfToken: me.data.csrf_token, method: "PATCH" }, competitorSchema);
    },
    onSuccess: (updated) => {
      if (updated) setCreated(updated);
    },
  });
  async function updateSource(sourceId: string, approval_status: "approved" | "rejected") {
    if (!created || !me.data) return;
    setPendingSourceId(sourceId);
    setSourceError(null);
    try {
      await apiMutate(`/api/v1/competitors/${created.id}/sources/${sourceId}`, { body: { approval_status }, csrfToken: me.data.csrf_token, method: "PATCH" }, sourceSchema);
      await sources.refetch();
    } catch (error) {
      setSourceError(error);
    } finally { setPendingSourceId(null); }
  }

  if (me.isPending) return <p role="status">Loading account…</p>;
  if (me.isError) return <p className="text-red-700" role="alert">{errorText(me.error)}</p>;
  return (
    <section className="space-y-8">
      <div><h1 className="text-3xl font-bold">Add competitor</h1><p className="mt-1 text-slate-600">Create a profile, then review its discovered sources.</p></div>
      {!created ? <div className="max-w-2xl rounded-xl border border-slate-200 bg-white p-6"><CompetitorForm isSubmitting={create.isPending} onSubmit={(values) => create.mutateAsync(values).then(() => undefined)} /></div> : null}
      {create.isError ? <p className="text-red-700" role="alert">{errorText(create.error)}</p> : null}
      {discovery.isPending || (runId && run.isPending) ? <p role="status">Discovering sources…</p> : null}
      {discovery.isError ? <div className="space-y-3" role="alert"><p>{errorText(discovery.error)}</p><button className="rounded-lg border border-slate-300 px-4 py-2 font-medium" onClick={() => created && discovery.mutate(created.id)} type="button">Retry source discovery</button></div> : null}
      {run.isError ? <p className="text-red-700" role="alert">{errorText(run.error)}</p> : null}
      {run.data?.status === "failed" ? <p className="text-red-700" role="alert">{run.data.failure_summary || "Source discovery failed."}</p> : null}
      {run.data?.status === "completed" ? <p role="status">Discovery completed.</p> : null}
      {run.data?.status === "partial" ? <p role="status">Discovery completed with partial results: {run.data.partial_reasons.join("; ") || "some sources were unavailable"}.</p> : null}
      {canLoadSources && sources.isPending ? <p role="status">Loading discovered sources…</p> : null}
      {sources.isError ? <p className="text-red-700" role="alert">{errorText(sources.error)}</p> : null}
      {sourceError ? <p className="text-red-700" role="alert">{errorText(sourceError)}</p> : null}
      {sources.data?.items.length === 0 ? <p>No sources were discovered.</p> : null}
      {sources.data?.items.length ? <SourceApprovalList onUpdate={updateSource} pendingSourceId={pendingSourceId} sources={sources.data.items} /> : null}
      {canLoadSources ? <button className="rounded-lg bg-slate-950 px-4 py-2 font-medium text-white disabled:bg-slate-400" disabled={!sources.data?.items.some((item) => item.approval_status === "approved") || activate.isPending} onClick={() => activate.mutate()} type="button">Activate daily monitoring</button> : null}
      {activate.isSuccess ? <p role="status">Daily monitoring activated.</p> : null}
      {activate.isError ? <p className="text-red-700" role="alert">{errorText(activate.error)}</p> : null}
    </section>
  );
}

export function CompetitorDetailView({ competitorId }: { competitorId: string }) {
  const client = useQueryClient();
  const [pendingSourceId, setPendingSourceId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const me = useQuery({ queryKey: ["me"], queryFn: () => apiGetClient("/api/v1/me", meSchema) });
  const competitor = useQuery({ queryKey: ["competitor", competitorId], queryFn: () => apiGetClient(`/api/v1/competitors/${competitorId}`, competitorSchema) });
  const sources = useQuery({ queryKey: ["competitor-sources", competitorId], queryFn: () => apiGetClient(`/api/v1/competitors/${competitorId}/sources`, sourcePageSchema) });
  const findings = useQuery({ queryKey: ["competitor-findings", competitorId], queryFn: () => apiGetClient(`/api/v1/findings?competitor_id=${competitorId}`, findingPageSchema) });
  const recentRuns = useQuery({ queryKey: ["competitor-runs", competitorId], queryFn: () => apiGetClient(`/api/v1/runs?competitor_id=${competitorId}`, runPageSchema) });
  const sourceUpdate = useMutation({ mutationFn: async ({ sourceId, approval_status }: { sourceId: string; approval_status: "approved" | "rejected" }) => {
    if (!me.data) throw new Error("Account information is unavailable.");
    setPendingSourceId(sourceId);
    return apiMutate(`/api/v1/competitors/${competitorId}/sources/${sourceId}`, { body: { approval_status }, csrfToken: me.data.csrf_token, method: "PATCH" }, sourceSchema);
  }, onSuccess: (updated) => {
    if (updated) {
      client.setQueryData<CursorPage<Source>>(["competitor-sources", competitorId], (current) => current ? {
        ...current,
        items: current.items.map((item) => item.id === updated.id ? updated : item),
      } : current);
    }
    void client.invalidateQueries({ queryKey: ["competitor", competitorId] });
  }, onSettled: () => setPendingSourceId(null) });
  const activate = useMutation({ mutationFn: async () => {
    if (!me.data) throw new Error("Account information is unavailable.");
    return apiMutate(`/api/v1/competitors/${competitorId}`, { body: { status: "active" }, csrfToken: me.data.csrf_token, method: "PATCH" }, competitorSchema);
  }, onSuccess: (updated) => {
    if (updated) client.setQueryData<Competitor>(["competitor", competitorId], updated);
    setNotice("Daily monitoring activated.");
  } });
  const runNow = useMutation({ mutationFn: async () => {
    if (!me.data) throw new Error("Account information is unavailable.");
    return apiMutate(`/api/v1/competitors/${competitorId}/runs`, { csrfToken: me.data.csrf_token, method: "POST" }, runSchema);
  }, onSuccess: () => setNotice("Scout run queued. An existing recent run may have been reused.") });
  if (me.isPending || competitor.isPending || sources.isPending || findings.isPending || recentRuns.isPending) return <p role="status">Loading competitor…</p>;
  if (me.isError || competitor.isError || sources.isError || findings.isError || recentRuns.isError) return <p className="text-red-700" role="alert">{errorText(me.error ?? competitor.error ?? sources.error ?? findings.error ?? recentRuns.error)}</p>;
  const hasApproved = sources.data.items.some((item) => item.approval_status === "approved");
  return (
    <article className="space-y-8">
      <header className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-sm font-semibold uppercase tracking-wide text-slate-500">{competitor.data.status}</p><h1 className="mt-1 text-3xl font-bold">{competitor.data.name}</h1><p className="mt-2 text-slate-600">{competitor.data.description}</p><a className="mt-2 inline-block text-sm text-blue-700 hover:underline" href={`https://${competitor.data.primary_domain}`} rel="noopener noreferrer" target="_blank">{competitor.data.primary_domain}</a></div>
        <div className="flex flex-wrap gap-2"><button className="rounded-lg border border-slate-300 px-4 py-2 font-medium disabled:text-slate-400" disabled={runNow.isPending} onClick={() => runNow.mutate()} type="button">Run now</button><button className="rounded-lg bg-slate-950 px-4 py-2 font-medium text-white disabled:bg-slate-400" disabled={!hasApproved || competitor.data.status === "active" || activate.isPending} onClick={() => activate.mutate()} type="button">Activate monitoring</button></div>
      </header>
      {notice ? <p role="status">{notice}</p> : null}
      {sourceUpdate.isError || activate.isError || runNow.isError ? <p className="text-red-700" role="alert">{errorText(sourceUpdate.error ?? activate.error ?? runNow.error)}</p> : null}
      {sources.data.items.length ? <SourceApprovalList disabled={sourceUpdate.isPending} onUpdate={(sourceId, approval_status) => sourceUpdate.mutateAsync({ sourceId, approval_status }).then(() => undefined)} pendingSourceId={pendingSourceId} sources={sources.data.items} /> : <p>No sources have been discovered.</p>}
      <section className="space-y-4" aria-labelledby="recent-findings-heading">
        <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-xl font-semibold" id="recent-findings-heading">Recent findings</h2><Link className="text-sm font-medium text-blue-700 hover:underline" href={`/findings?competitor_id=${competitorId}`}>View all findings</Link></div>
        <form action="/findings" aria-label="Filter competitor findings" className="grid gap-3 rounded-xl border border-slate-200 bg-white p-4 sm:grid-cols-4" method="get">
          <input name="competitor_id" type="hidden" value={competitorId} />
          <label className="text-sm font-medium">Category<input className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2" name="category" type="text" /></label>
          <label className="text-sm font-medium">Significance<select className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2" name="significance"><option value="">All levels</option><option value="high">High</option><option value="critical">Critical</option></select></label>
          <label className="text-sm font-medium">Published from<input className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2" name="published_from" type="date" /></label>
          <button className="self-end rounded-lg bg-slate-950 px-4 py-2 font-medium text-white" type="submit">Filter findings</button>
        </form>
        {findings.data.items.length ? <div className="space-y-3">{findings.data.items.map((finding) => <FindingCard finding={finding} key={finding.id} />)}</div> : <p className="text-sm text-slate-600">No findings for this competitor yet.</p>}
      </section>
      <section className="space-y-4" aria-labelledby="recent-runs-heading">
        <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-xl font-semibold" id="recent-runs-heading">Recent runs</h2><Link className="text-sm font-medium text-blue-700 hover:underline" href={`/runs?competitor_id=${competitorId}`}>View all runs</Link></div>
        {recentRuns.data.items.length ? <ul className="space-y-2">{recentRuns.data.items.map((run) => <li className="rounded-xl border border-slate-200 bg-white p-4" key={run.id}><Link className="font-medium capitalize hover:underline" href={`/runs/${run.id}`}>{run.run_type.replaceAll("_", " ")}</Link><span className="ml-3 text-sm capitalize text-slate-500">{run.status}</span>{run.partial_reasons.length ? <p className="mt-2 text-sm text-amber-700">{run.partial_reasons.join("; ")}</p> : null}{run.failure_summary ? <p className="mt-2 text-sm text-red-700">{run.failure_summary}</p> : null}</li>)}</ul> : <p className="text-sm text-slate-600">No runs for this competitor yet.</p>}
      </section>
    </article>
  );
}
