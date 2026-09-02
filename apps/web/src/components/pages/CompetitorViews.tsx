"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { CompetitorForm, type CompetitorFormValues } from "@/components/CompetitorForm";
import { FindingCard } from "@/components/FindingCard";
import { SetupStepper } from "@/components/SetupStepper";
import { SourceManagementList } from "@/components/SourceManagementList";
import { SourceSelectionList } from "@/components/SourceSelectionList";
import { LoadingState } from "@/components/ui/LoadingState";
import { WorkingIndicator } from "@/components/ui/WorkingIndicator";
import { apiGetClient, apiMutate } from "@/lib/api";
import { partialReasonLabels } from "@/lib/runs";
import {
  competitorPageSchema,
  competitorSchema,
  findingPageSchema,
  meSchema,
  runPageSchema,
  runSchema,
  settingsSchema,
  sourceDiscoveryResponseSchema,
  sourcePageSchema,
  sourceSchema,
  startMonitoringResponseSchema,
  type Competitor,
  type CursorPage,
  type Source,
} from "@/lib/schemas";

function errorText(error: unknown) {
  if (typeof error === "object" && error && "detail" in error) {
    const detail = error.detail;
    if (detail === "competitor limit reached") {
      return "Competitor limit reached. Remove a competitor before adding another.";
    }
    if (typeof detail === "string" && detail) return detail;
  }
  return error instanceof Error ? error.message : "Something went wrong.";
}

export function CompetitorsListView() {
  const query = useQuery({
    queryKey: ["competitors"],
    queryFn: () => apiGetClient("/api/v1/competitors", competitorPageSchema),
  });
  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="eyebrow">Monitoring</p>
          <h1 className="mt-1 text-4xl font-semibold">Competitors</h1>
          <p className="mt-2 text-slate-600">Companies monitored by your scout.</p>
        </div>
        <Link
          className="inline-flex min-h-10 items-center rounded-xl bg-slate-950 px-4 py-2 font-semibold text-white"
          href="/competitors/new"
        >
          Add competitor
        </Link>
      </div>
      {query.isPending ? <LoadingState label="Loading competitors…" rows={4} /> : null}
      {query.isError ? (
        <p className="text-red-700" role="alert">
          {errorText(query.error)}
        </p>
      ) : null}
      {query.data?.items.length === 0 ? (
        <p className="empty-state p-8 text-center">No competitors yet.</p>
      ) : null}
      {query.data?.items.length ? (
        <ul className="grid gap-4 md:grid-cols-2">
          {query.data.items.map((item) => (
            <li className="surface surface-interactive p-5" key={item.id}>
              <div className="flex justify-between gap-3">
                <h2 className="font-semibold">
                  <Link className="hover:underline" href={`/competitors/${item.id}`}>
                    {item.name}
                  </Link>
                </h2>
                <span className="text-sm capitalize text-slate-500">{item.status}</span>
              </div>
              <p className="mt-2 text-sm text-slate-600">
                {item.description || item.primary_domain}
              </p>
              {item.status === "discovering" ? (
                <Link
                  className="mt-3 inline-flex text-sm font-semibold text-blue-700 hover:underline"
                  href={`/competitors/${item.id}`}
                >
                  Finish setup →
                </Link>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

type NewCompetitorViewProps = { pollIntervalMs?: number };
const terminalStatuses = new Set(["completed", "partial", "failed"]);
const discoveryMessages = [
  "Casing the joint for official pages…",
  "Reading their pricing page so you don't have to…",
  "Digging through the changelog…",
  "Sniffing out the blog feed…",
  "Checking whether the roadmap is public…",
  "Skipping the marketing fluff…",
  "Double-checking every URL is first-party…",
];
const firstScanMessages = [
  "Fetching the sources you approved…",
  "Comparing today against yesterday…",
  "Ignoring cosmetic copy tweaks…",
  "Deciding what actually matters…",
  "Collecting evidence for every claim…",
  "Almost there — writing up the findings…",
];

export function NewCompetitorView({ pollIntervalMs = 1_000 }: NewCompetitorViewProps) {
  const client = useQueryClient();
  const searchParams = useSearchParams();
  const isFirstSetup = searchParams?.get("first") === "1";
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [created, setCreated] = useState<Competitor | null>(null);
  const [discoveryRunId, setDiscoveryRunId] = useState<string | null>(null);
  const [firstScanRunId, setFirstScanRunId] = useState<string | null>(null);
  const [manualSourceUrl, setManualSourceUrl] = useState("");
  const [manualSourceAdded, setManualSourceAdded] = useState(false);
  const [deselectedSourceIds, setDeselectedSourceIds] = useState<Set<string>>(new Set());
  const me = useQuery({ queryKey: ["me"], queryFn: () => apiGetClient("/api/v1/me", meSchema) });
  const settings = useQuery({
    queryKey: ["settings"],
    queryFn: () => apiGetClient("/api/v1/settings", settingsSchema),
  });
  const discovery = useMutation({
    mutationFn: async (competitorId: string) => {
      if (!me.data) throw new Error("Account information is unavailable.");
      const result = await apiMutate(
        `/api/v1/competitors/${competitorId}/discover-sources`,
        {
          csrfToken: me.data.csrf_token,
          method: "POST",
        },
        sourceDiscoveryResponseSchema,
      );
      if (!result) throw new Error("The discovery response was empty.");
      return result;
    },
    onSuccess: (result) => setDiscoveryRunId(result.run_id),
  });
  const create = useMutation({
    mutationFn: async (values: CompetitorFormValues) => {
      if (!me.data) throw new Error("Account information is unavailable.");
      const result = await apiMutate(
        "/api/v1/competitors",
        {
          body: values,
          csrfToken: me.data.csrf_token,
          method: "POST",
        },
        competitorSchema,
      );
      if (!result) throw new Error("The competitor response was empty.");
      return result;
    },
    onSuccess: (result) => {
      setCreated(result);
      setStep(2);
      void client.invalidateQueries({ queryKey: ["competitors"] });
      discovery.mutate(result.id);
    },
  });
  const discoveryRun = useQuery({
    enabled: Boolean(discoveryRunId),
    queryKey: ["run", discoveryRunId],
    queryFn: () => apiGetClient(`/api/v1/runs/${discoveryRunId}`, runSchema),
    refetchInterval: (query) =>
      terminalStatuses.has(query.state.data?.status ?? "")
        ? false
        : Math.min(pollIntervalMs * 2 ** query.state.dataUpdateCount, 10_000),
  });
  const canLoadSources = Boolean(
    created &&
    (manualSourceAdded ||
      discoveryRun.data?.status === "completed" ||
      discoveryRun.data?.status === "partial"),
  );
  const sources = useQuery({
    enabled: canLoadSources,
    queryKey: ["competitor-sources", created?.id],
    queryFn: () => apiGetClient(`/api/v1/competitors/${created?.id}/sources`, sourcePageSchema),
  });
  const selectedSourceIds = new Set(
    (sources.data?.items ?? [])
      .filter((source) => !deselectedSourceIds.has(source.id))
      .map((source) => source.id),
  );

  const addSource = useMutation({
    mutationFn: async () => {
      if (!created || !me.data) throw new Error("Account information is unavailable.");
      const result = await apiMutate(
        `/api/v1/competitors/${created.id}/sources`,
        {
          body: { url: manualSourceUrl.trim() },
          csrfToken: me.data.csrf_token,
          method: "POST",
        },
        sourceSchema,
      );
      if (!result) throw new Error("The source response was empty.");
      return result;
    },
    onSuccess: async (source) => {
      setManualSourceAdded(true);
      setManualSourceUrl("");
      setDeselectedSourceIds((current) => {
        const next = new Set(current);
        next.delete(source.id);
        return next;
      });
      await sources.refetch();
    },
  });
  const startMonitoring = useMutation({
    mutationFn: async (sourceIds: string[]) => {
      if (!created || !me.data) throw new Error("Account information is unavailable.");
      const result = await apiMutate(
        `/api/v1/competitors/${created.id}/start-monitoring`,
        {
          body: { source_ids: sourceIds, run_initial_scan: true },
          csrfToken: me.data.csrf_token,
          method: "POST",
        },
        startMonitoringResponseSchema,
      );
      if (!result) throw new Error("The monitoring response was empty.");
      return result;
    },
    onSuccess: (result) => {
      setCreated(result.competitor);
      setFirstScanRunId(result.run?.id ?? null);
      setStep(3);
      void client.invalidateQueries({ queryKey: ["competitors"] });
    },
  });
  const firstScan = useQuery({
    enabled: Boolean(firstScanRunId),
    queryKey: ["run", firstScanRunId],
    queryFn: () => apiGetClient(`/api/v1/runs/${firstScanRunId}`, runSchema),
    refetchInterval: (query) =>
      terminalStatuses.has(query.state.data?.status ?? "") ? false : pollIntervalMs,
  });

  function toggleSource(sourceId: string) {
    setDeselectedSourceIds((current) => {
      const next = new Set(current);
      if (next.has(sourceId)) next.delete(sourceId);
      else next.add(sourceId);
      return next;
    });
  }

  if (me.isPending || settings.isPending) return <LoadingState label="Loading account…" rows={3} />;
  if (me.isError || settings.isError)
    return (
      <p className="text-red-700" role="alert">
        {errorText(me.error ?? settings.error)}
      </p>
    );
  return (
    <section className="space-y-8">
      <div>
        <p className="eyebrow">{isFirstSetup ? "Welcome" : "New monitor"}</p>
        <h1 className="mt-1 text-4xl font-semibold">
          {isFirstSetup ? "Let's set up your first competitor in 3 steps" : "Add competitor"}
        </h1>
        <p className="mt-2 text-slate-600">
          {isFirstSetup
            ? "Tell us who to watch, confirm the sources we should trust, and we'll run the first scan for you. Takes about two minutes."
            : "Choose a competitor, confirm trusted sources, and run an initial scan."}
        </p>
      </div>
      <SetupStepper currentStep={step} />
      {step === 1 ? (
        <div className="surface max-w-2xl p-6">
          <CompetitorForm
            initialValues={{ daily_run_time_local: settings.data.default_daily_time }}
            isSubmitting={create.isPending}
            onSubmit={(values) => create.mutateAsync(values).then(() => undefined)}
            submitLabel="Continue to sources"
          />
        </div>
      ) : null}
      {create.isError ? (
        <p className="text-red-700" role="alert">
          {errorText(create.error)}
        </p>
      ) : null}
      {step === 2 ? (
        <div className="space-y-6">
          <div>
            <h2 className="text-2xl font-semibold">Choose trusted sources</h2>
            <p className="mt-1 text-slate-600">
              We only monitor first-party pages you select. You can change these later.
            </p>
          </div>
          {discovery.isPending ||
          (discoveryRunId && !terminalStatuses.has(discoveryRun.data?.status ?? "")) ? (
            <WorkingIndicator
              hint="This usually takes under a minute"
              label="Finding first-party sources…"
              messages={discoveryMessages}
            />
          ) : null}
          {discovery.isError ? (
            <div className="space-y-3 text-red-700" role="alert">
              <p>{errorText(discovery.error)}</p>
              <button
                className="rounded-lg border border-red-300 px-4 py-2 font-medium"
                onClick={() => created && discovery.mutate(created.id)}
                type="button"
              >
                Retry source discovery
              </button>
            </div>
          ) : null}
          {discoveryRun.isError ? (
            <p className="text-red-700" role="alert">
              {errorText(discoveryRun.error)}
            </p>
          ) : null}
          {discoveryRun.data?.status === "failed" ? (
            <p className="text-red-700" role="alert">
              {discoveryRun.data.failure_summary || "Source discovery failed."}
            </p>
          ) : null}
          {canLoadSources && sources.isPending ? (
            <LoadingState label="Loading suggested sources…" rows={2} />
          ) : null}
          {sources.isError ? (
            <p className="text-red-700" role="alert">
              {errorText(sources.error)}
            </p>
          ) : null}
          {sources.data?.items.length ? (
            <SourceSelectionList
              disabled={startMonitoring.isPending}
              onToggle={toggleSource}
              selectedSourceIds={selectedSourceIds}
              sources={sources.data.items}
            />
          ) : canLoadSources && !sources.isPending ? (
            <p className="empty-state p-5">No sources were found. Add a trusted URL below.</p>
          ) : null}
          <form
            className="surface flex flex-col gap-3 p-4 sm:flex-row sm:items-end"
            onSubmit={(event) => {
              event.preventDefault();
              if (manualSourceUrl.trim()) addSource.mutate();
            }}
          >
            <label className="min-w-0 flex-1 text-sm font-medium">
              Add a first-party source
              <input
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                disabled={addSource.isPending}
                onChange={(event) => setManualSourceUrl(event.target.value)}
                placeholder={`https://${created?.primary_domain ?? "example.com"}/pricing`}
                type="url"
                value={manualSourceUrl}
              />
            </label>
            <button
              className="rounded-lg border border-slate-300 px-4 py-2 font-semibold disabled:text-slate-400"
              disabled={!manualSourceUrl.trim() || addSource.isPending}
              type="submit"
            >
              {addSource.isPending ? "Adding…" : "Add source"}
            </button>
          </form>
          {addSource.isError ? (
            <p className="text-red-700" role="alert">
              {errorText(addSource.error)}
            </p>
          ) : null}
          <button
            className="rounded-xl bg-slate-950 px-5 py-3 font-semibold text-white disabled:bg-slate-400"
            disabled={!selectedSourceIds.size || startMonitoring.isPending}
            onClick={() => startMonitoring.mutate([...selectedSourceIds])}
            type="button"
          >
            {startMonitoring.isPending
              ? "Starting monitoring…"
              : "Start monitoring & run first scan"}
          </button>
          {startMonitoring.isError ? (
            <p className="text-red-700" role="alert">
              {errorText(startMonitoring.error)}
            </p>
          ) : null}
        </div>
      ) : null}
      {step === 3 ? (
        <div className="surface max-w-2xl space-y-4 p-6">
          <h2 className="text-2xl font-semibold">Your monitor is active</h2>
          {firstScanRunId && !terminalStatuses.has(firstScan.data?.status ?? "") ? (
            <WorkingIndicator
              hint="You can leave this page — the scan keeps running"
              label="Running the first scan…"
              messages={firstScanMessages}
            />
          ) : null}
          {firstScan.data?.status === "completed" || firstScan.data?.status === "partial" ? (
            <p role="status">First scan complete.</p>
          ) : null}
          {firstScan.data?.status === "failed" || firstScan.isError ? (
            <p className="text-red-700" role="alert">
              {firstScan.data?.failure_summary ||
                errorText(firstScan.error) ||
                "First scan failed."}
            </p>
          ) : null}
          <div className="flex flex-wrap gap-3">
            <Link className="rounded-lg bg-slate-950 px-4 py-2 font-semibold text-white" href="/">
              Go to dashboard
            </Link>
            {firstScanRunId ? (
              <Link
                className="rounded-lg border border-slate-300 px-4 py-2 font-semibold"
                href={`/runs/${firstScanRunId}`}
              >
                View scan details
              </Link>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}

export function CompetitorDetailView({ competitorId }: { competitorId: string }) {
  const client = useQueryClient();
  const [pendingSourceId, setPendingSourceId] = useState<string | null>(null);
  const [manualSourceUrl, setManualSourceUrl] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [discoveryRunId, setDiscoveryRunId] = useState<string | null>(null);
  const me = useQuery({ queryKey: ["me"], queryFn: () => apiGetClient("/api/v1/me", meSchema) });
  const competitor = useQuery({
    queryKey: ["competitor", competitorId],
    queryFn: () => apiGetClient(`/api/v1/competitors/${competitorId}`, competitorSchema),
  });
  const sources = useQuery({
    queryKey: ["competitor-sources", competitorId],
    queryFn: () => apiGetClient(`/api/v1/competitors/${competitorId}/sources`, sourcePageSchema),
  });
  const findings = useQuery({
    queryKey: ["competitor-findings", competitorId],
    queryFn: () =>
      apiGetClient(`/api/v1/findings?competitor_id=${competitorId}`, findingPageSchema),
  });
  const recentRuns = useQuery({
    queryKey: ["competitor-runs", competitorId],
    queryFn: () => apiGetClient(`/api/v1/runs?competitor_id=${competitorId}`, runPageSchema),
  });
  const discovery = useMutation({
    mutationFn: async () => {
      if (!me.data) throw new Error("Account information is unavailable.");
      const result = await apiMutate(
        `/api/v1/competitors/${competitorId}/discover-sources`,
        { csrfToken: me.data.csrf_token, method: "POST" },
        sourceDiscoveryResponseSchema,
      );
      if (!result) throw new Error("The discovery response was empty.");
      return result;
    },
    onSuccess: (result) => {
      setNotice("Source discovery queued.");
      setDiscoveryRunId(result.run_id);
    },
  });
  const discoveryRun = useQuery({
    enabled: Boolean(discoveryRunId),
    queryKey: ["run", discoveryRunId],
    queryFn: () => apiGetClient(`/api/v1/runs/${discoveryRunId}`, runSchema),
    refetchInterval: (query) =>
      terminalStatuses.has(query.state.data?.status ?? "") ? false : 1_000,
  });
  const discoveryFinished = terminalStatuses.has(discoveryRun.data?.status ?? "");
  const discoveryNotice = discoveryFinished
    ? discoveryRun.data?.status === "failed"
      ? discoveryRun.data.failure_summary || "Source discovery failed."
      : "Source discovery completed."
    : null;
  useEffect(() => {
    if (!discoveryRunId || !discoveryFinished) return;
    void client.invalidateQueries({ queryKey: ["competitor-sources", competitorId] });
    void client.invalidateQueries({ queryKey: ["competitor-runs", competitorId] });
  }, [client, competitorId, discoveryFinished, discoveryRunId]);
  const sourceUpdate = useMutation({
    mutationFn: async ({
      sourceId,
      approval_status,
    }: {
      sourceId: string;
      approval_status: "approved" | "rejected";
    }) => {
      if (!me.data) throw new Error("Account information is unavailable.");
      setPendingSourceId(sourceId);
      return apiMutate(
        `/api/v1/competitors/${competitorId}/sources/${sourceId}`,
        { body: { approval_status }, csrfToken: me.data.csrf_token, method: "PATCH" },
        sourceSchema,
      );
    },
    onSuccess: (updated) => {
      if (updated) {
        client.setQueryData<CursorPage<Source>>(["competitor-sources", competitorId], (current) =>
          current
            ? {
                ...current,
                items: current.items.map((item) => (item.id === updated.id ? updated : item)),
              }
            : current,
        );
      }
      void client.invalidateQueries({ queryKey: ["competitor", competitorId] });
    },
    onSettled: () => setPendingSourceId(null),
  });
  const addSource = useMutation({
    mutationFn: async () => {
      if (!me.data) throw new Error("Account information is unavailable.");
      return apiMutate(
        `/api/v1/competitors/${competitorId}/sources`,
        {
          body: { url: manualSourceUrl.trim() },
          csrfToken: me.data.csrf_token,
          method: "POST",
        },
        sourceSchema,
      );
    },
    onSuccess: async () => {
      setManualSourceUrl("");
      setNotice("Source added. Monitor it to include it in scans.");
      await sources.refetch();
    },
  });
  const activate = useMutation({
    mutationFn: async () => {
      if (!me.data) throw new Error("Account information is unavailable.");
      return apiMutate(
        `/api/v1/competitors/${competitorId}`,
        { body: { status: "active" }, csrfToken: me.data.csrf_token, method: "PATCH" },
        competitorSchema,
      );
    },
    onSuccess: (updated) => {
      if (updated) client.setQueryData<Competitor>(["competitor", competitorId], updated);
      setNotice("Daily monitoring activated.");
    },
  });
  const runNow = useMutation({
    mutationFn: async () => {
      if (!me.data) throw new Error("Account information is unavailable.");
      return apiMutate(
        `/api/v1/competitors/${competitorId}/runs`,
        { csrfToken: me.data.csrf_token, method: "POST" },
        runSchema,
      );
    },
    onSuccess: () => setNotice("Scout run queued. An existing recent run may have been reused."),
  });
  if (
    me.isPending ||
    competitor.isPending ||
    sources.isPending ||
    findings.isPending ||
    recentRuns.isPending
  )
    return <LoadingState label="Loading competitor…" rows={5} />;
  if (me.isError || competitor.isError || sources.isError || findings.isError || recentRuns.isError)
    return (
      <p className="text-red-700" role="alert">
        {errorText(
          me.error ?? competitor.error ?? sources.error ?? findings.error ?? recentRuns.error,
        )}
      </p>
    );
  const hasApproved = sources.data.items.some((item) => item.approval_status === "approved");
  return (
    <article className="space-y-10">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="eyebrow">{competitor.data.status}</p>
          <h1 className="mt-1 text-4xl font-semibold">{competitor.data.name}</h1>
          <p className="mt-2 text-slate-600">{competitor.data.description}</p>
          <a
            className="section-link mt-2 inline-block"
            href={`https://${competitor.data.primary_domain}`}
            rel="noopener noreferrer"
            target="_blank"
          >
            {competitor.data.primary_domain}
          </a>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            className="rounded-lg border border-slate-300 px-4 py-2 font-medium disabled:text-slate-400"
            disabled={!hasApproved || competitor.data.status !== "active" || runNow.isPending}
            onClick={() => runNow.mutate()}
            type="button"
          >
            Run now
          </button>
          <button
            className="rounded-lg bg-slate-950 px-4 py-2 font-medium text-white disabled:bg-slate-400"
            disabled={!hasApproved || competitor.data.status === "active" || activate.isPending}
            onClick={() => activate.mutate()}
            type="button"
          >
            Activate monitoring
          </button>
        </div>
      </header>
      {discoveryNotice || notice ? <p role="status">{discoveryNotice || notice}</p> : null}
      {sourceUpdate.isError || activate.isError || runNow.isError || discovery.isError ? (
        <p className="text-red-700" role="alert">
          {errorText(sourceUpdate.error ?? activate.error ?? runNow.error ?? discovery.error)}
        </p>
      ) : null}
      {sources.data.items.length ? (
        <div className="space-y-6">
          <SourceManagementList
            disabled={sourceUpdate.isPending}
            onUpdate={(sourceId, approval_status) =>
              sourceUpdate.mutateAsync({ sourceId, approval_status }).then(() => undefined)
            }
            pendingSourceId={pendingSourceId}
            sources={sources.data.items}
          />
          <form
            aria-label="Add a source"
            className="surface flex flex-col gap-3 p-4 sm:flex-row sm:items-end"
            onSubmit={(event) => {
              event.preventDefault();
              if (manualSourceUrl.trim()) addSource.mutate();
            }}
          >
            <label className="field-label min-w-0 flex-1">
              Add a first-party source
              <input
                aria-describedby="add-source-help"
                className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2"
                disabled={addSource.isPending}
                onChange={(event) => setManualSourceUrl(event.target.value)}
                placeholder={`https://${competitor.data.primary_domain}/changelog`}
                type="url"
                value={manualSourceUrl}
              />
            </label>
            <button
              className="rounded-lg border border-slate-300 px-4 py-2 font-medium disabled:text-slate-400"
              disabled={!manualSourceUrl.trim() || addSource.isPending}
              type="submit"
            >
              {addSource.isPending ? "Adding…" : "Add source"}
            </button>
          </form>
          <p className="text-sm text-slate-600" id="add-source-help">
            A new source waits under Awaiting review until you monitor it.
          </p>
          {addSource.isError ? (
            <p className="text-red-700" role="alert">
              {errorText(addSource.error)}
            </p>
          ) : null}
        </div>
      ) : (
        <div className="space-y-3">
          <p>No sources have been discovered.</p>
          <button
            className="rounded-lg border border-slate-300 px-4 py-2 font-medium disabled:text-slate-400"
            disabled={discovery.isPending || (Boolean(discoveryRunId) && !discoveryFinished)}
            onClick={() => discovery.mutate()}
            type="button"
          >
            Retry source discovery
          </button>
        </div>
      )}
      <section className="space-y-4" aria-labelledby="recent-findings-heading">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-xl font-semibold" id="recent-findings-heading">
            Recent updates
          </h2>
          <Link className="section-link" href={`/findings?competitor_id=${competitorId}`}>
            View all updates
          </Link>
        </div>
        <form
          action="/findings"
          aria-label="Filter competitor updates"
          className="surface grid gap-3 p-4 sm:grid-cols-4"
          method="get"
        >
          <input name="competitor_id" type="hidden" value={competitorId} />
          <label className="text-sm font-medium">
            Category
            <input
              className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2"
              name="category"
              type="text"
            />
          </label>
          <label className="text-sm font-medium">
            Significance
            <select className="select-control mt-1" name="significance">
              <option value="">All levels</option>
              <option value="high">High</option>
              <option value="critical">Critical</option>
            </select>
          </label>
          <label className="text-sm font-medium">
            Published from
            <input
              className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2"
              name="published_from"
              type="date"
            />
          </label>
          <button
            className="self-end rounded-lg bg-slate-950 px-4 py-2 font-medium text-white"
            type="submit"
          >
            Filter updates
          </button>
        </form>
        {findings.data.items.length ? (
          <div className="space-y-3">
            {findings.data.items.map((finding) => (
              <FindingCard finding={finding} key={finding.id} />
            ))}
          </div>
        ) : (
          <p className="text-sm text-slate-600">No updates for this competitor yet.</p>
        )}
      </section>
      <section className="space-y-4" aria-labelledby="recent-runs-heading">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-xl font-semibold" id="recent-runs-heading">
            Recent scans
          </h2>
          <Link className="section-link" href={`/runs?competitor_id=${competitorId}`}>
            View all scans
          </Link>
        </div>
        {recentRuns.data.items.length ? (
          <ul className="space-y-2">
            {recentRuns.data.items.map((run) => (
              <li className="surface surface-interactive p-4" key={run.id}>
                <Link className="font-medium capitalize hover:underline" href={`/runs/${run.id}`}>
                  {run.run_type.replaceAll("_", " ")}
                </Link>
                <span className="ml-3 text-sm capitalize text-slate-500">{run.status}</span>
                {run.partial_reasons.length ? (
                  <p className="mt-2 text-sm text-amber-700">
                    {partialReasonLabels(run.partial_reasons, run.partial_summaries).join("; ")}
                  </p>
                ) : null}
                {run.failure_summary ? (
                  <p className="mt-2 text-sm text-red-700">{run.failure_summary}</p>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-600">No scans for this competitor yet.</p>
        )}
      </section>
    </article>
  );
}
