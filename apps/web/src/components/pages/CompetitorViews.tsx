"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { CompetitorFavicon } from "@/components/CompetitorFavicon";
import { CompetitorForm, type CompetitorFormValues } from "@/components/CompetitorForm";
import { FindingCard } from "@/components/FindingCard";
import { MonitorSettings } from "@/components/MonitorSettings";
import { runTypeLabel } from "@/components/RunOutcomeSummary";
import { SetupStepper } from "@/components/SetupStepper";
import { SourceManagementList } from "@/components/SourceManagementList";
import { StartingSnapshot } from "@/components/StartingSnapshot";
import { SourceSelectionList } from "@/components/SourceSelectionList";
import { CollapsibleSection } from "@/components/ui/CollapsibleSection";
import { LoadingState } from "@/components/ui/LoadingState";
import { SelectField, type SelectFieldOption } from "@/components/ui/SelectField";
import { WorkingIndicator } from "@/components/ui/WorkingIndicator";
import { apiGetClient, apiMutate } from "@/lib/api";
import { meQueryOptions } from "@/lib/current-user";
import { partialReasonLabels } from "@/lib/runs";
import {
  competitorPageSchema,
  competitorSchema,
  findingCategorySchema,
  findingPageSchema,
  runPageSchema,
  runSchema,
  settingsSchema,
  sourceDiscoveryResponseSchema,
  sourcePageSchema,
  sourceSchema,
  startMonitoringResponseSchema,
  startingSnapshotSchema,
  type Competitor,
  type CursorPage,
  type Source,
} from "@/lib/schemas";

const COMPETITOR_LIMIT = 10;

const findingCategoryOptions: SelectFieldOption[] = [
  { label: "All categories", value: "" },
  ...findingCategorySchema.options.map((value) => ({
    label: value.replaceAll("_", " "),
    value,
  })),
];

const findingSignificanceOptions: SelectFieldOption[] = [
  { label: "All levels", value: "" },
  { label: "High", value: "high" },
  { label: "Critical", value: "critical" },
];

const competitorStatusStyles: Record<string, string> = {
  active: "bg-emerald-50 text-emerald-700",
  discovering: "bg-amber-50 text-amber-800",
  paused: "bg-slate-100 text-slate-700",
};

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
  const competitorCount = query.data?.items.length ?? 0;
  return (
    <section className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="eyebrow">Monitoring</p>
          <h1 className="mt-1 text-4xl font-semibold">Competitors</h1>
          <p className="mt-2 text-slate-600">Companies monitored by your scout.</p>
        </div>
        <div className="flex flex-col items-end gap-3">
          <div className="w-44">
            <div className="flex items-center justify-between text-xs text-slate-500">
              <span>Competitors</span>
              <span>
                {competitorCount} of {COMPETITOR_LIMIT}
              </span>
            </div>
            <progress
              aria-label="Competitor slots used"
              className="mt-1.5 w-full"
              max={COMPETITOR_LIMIT}
              value={competitorCount}
            />
            <p className="sr-only">
              {competitorCount} of {COMPETITOR_LIMIT} competitor slots used
            </p>
          </div>
          <Link
            className="inline-flex min-h-10 items-center rounded-xl bg-slate-950 px-4 py-2 font-semibold text-white"
            href="/competitors/new"
          >
            Add competitor
          </Link>
        </div>
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
            <li className="surface surface-interactive card-target p-5" key={item.id}>
              <div className="flex justify-between gap-3">
                <div className="flex items-center gap-3 min-w-0">
                  <CompetitorFavicon domain={item.primary_domain} name={item.name} size="md" />
                  <h2 className="font-semibold truncate">
                    <Link className="card-link" href={`/competitors/${item.id}`}>
                      {item.name}
                    </Link>
                  </h2>
                </div>
                <span
                  className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium capitalize ${
                    competitorStatusStyles[item.status] ?? "bg-slate-100 text-slate-700"
                  }`}
                >
                  {item.status}
                </span>
              </div>
              <p className="mt-2 text-sm text-slate-600">
                {item.description || item.primary_domain}
              </p>
              {item.status === "discovering" ? (
                <p className="mt-3 text-sm font-semibold text-[var(--color-accent-strong)]">
                  Finish setup <span aria-hidden="true">→</span>
                </p>
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
  const me = useQuery(meQueryOptions);
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
  const firstSnapshot = useQuery({
    enabled: Boolean(
      created && (firstScan.data?.status === "completed" || firstScan.data?.status === "partial"),
    ),
    queryKey: ["starting-snapshot", created?.id],
    queryFn: () =>
      apiGetClient(`/api/v1/competitors/${created?.id}/starting-snapshot`, startingSnapshotSchema),
    retry: false,
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
            <h2 className="text-xl font-semibold">Choose trusted sources</h2>
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
            <>
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
              <SourceSelectionList
                disabled={startMonitoring.isPending}
                onToggle={toggleSource}
                selectedSourceIds={selectedSourceIds}
                sources={sources.data.items}
              />
            </>
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
        </div>
      ) : null}
      {step === 3 ? (
        <div className="max-w-2xl space-y-4">
          {!firstSnapshot.data ? (
            <div className="surface space-y-4 p-6">
              <h2 className="text-xl font-semibold">Your monitor is active</h2>
              {firstScanRunId && !terminalStatuses.has(firstScan.data?.status ?? "") ? (
                <WorkingIndicator
                  hint="You can leave this page — the scan keeps running"
                  label="Running the first scan…"
                  messages={firstScanMessages}
                />
              ) : null}
              {firstSnapshot.isPending &&
              (firstScan.data?.status === "completed" || firstScan.data?.status === "partial") ? (
                <p aria-live="polite" role="status">
                  Preparing your Starting Snapshot…
                </p>
              ) : null}
              {firstScan.data?.status === "failed" || firstScan.isError ? (
                <p className="text-red-700" role="alert">
                  {firstScan.data?.failure_summary ||
                    errorText(firstScan.error) ||
                    "First scan failed."}
                </p>
              ) : null}
              {firstSnapshot.isError ? (
                <p className="text-amber-800" role="alert">
                  The scan ended before a Starting Snapshot was available. Monitoring remains
                  active; run another scan from the competitor page to retry.
                </p>
              ) : null}
            </div>
          ) : (
            <>
              <p className="text-lg font-semibold" role="status">
                Your Starting Snapshot is ready
              </p>
              <StartingSnapshot
                snapshot={firstSnapshot.data}
                timeZone={me.data.timezone}
                variant="preview"
              />
            </>
          )}
          <div className="flex flex-wrap gap-3">
            <Link className="rounded-lg border border-slate-300 px-4 py-2 font-semibold" href="/">
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
  const router = useRouter();
  const [competitorInfoOpen, setCompetitorInfoOpen] = useState(false);
  const [pendingSourceId, setPendingSourceId] = useState<string | null>(null);
  const [manualSourceUrl, setManualSourceUrl] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [discoveryRunId, setDiscoveryRunId] = useState<string | null>(null);
  const me = useQuery(meQueryOptions);
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
  const snapshot = useQuery({
    enabled: Boolean(competitor.data?.starting_snapshot_requested_at),
    queryKey: ["starting-snapshot", competitorId],
    queryFn: () =>
      apiGetClient(`/api/v1/competitors/${competitorId}/starting-snapshot`, startingSnapshotSchema),
    retry: false,
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
  const updateMonitor = useMutation({
    mutationFn: async (body: {
      daily_run_time_local?: string;
      description?: string;
      name?: string;
      status?: "active" | "paused";
    }) => {
      if (!me.data) throw new Error("Account information is unavailable.");
      return apiMutate(
        `/api/v1/competitors/${competitorId}`,
        { body, csrfToken: me.data.csrf_token, method: "PATCH" },
        competitorSchema,
      );
    },
    onSuccess: (updated) => {
      if (updated) client.setQueryData<Competitor>(["competitor", competitorId], updated);
      void client.invalidateQueries({ queryKey: ["competitors"] });
      void client.invalidateQueries({ queryKey: ["dashboard"] });
      setNotice("Monitor updated.");
    },
  });
  const archiveMonitor = useMutation({
    mutationFn: async () => {
      if (!me.data) throw new Error("Account information is unavailable.");
      await apiMutate(`/api/v1/competitors/${competitorId}`, {
        csrfToken: me.data.csrf_token,
        method: "DELETE",
      });
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["competitors"] });
      void client.invalidateQueries({ queryKey: ["dashboard"] });
      router.push("/competitors");
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
    onSuccess: () => setNotice("Scan queued. An existing recent scan may have been reused."),
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
  const monitoredSourceCount = sources.data.items.filter(
    (item) => item.approval_status === "approved",
  ).length;
  const hasApproved = monitoredSourceCount > 0;
  const snapshotMissing =
    snapshot.error instanceof Error && "status" in snapshot.error && snapshot.error.status === 404;
  const snapshotUnavailable = snapshot.isError && !snapshotMissing;
  const latestSnapshotRun = recentRuns.data.items.find((run) =>
    ["daily_scout", "manual_scout"].includes(run.run_type),
  );
  return (
    <article className="space-y-10">
      <header>
        <p className="eyebrow">{competitor.data.status}</p>
        <div className="mt-1 flex items-center gap-3">
          <CompetitorFavicon
            domain={competitor.data.primary_domain}
            name={competitor.data.name}
            size="lg"
          />
          <h1 className="text-4xl font-semibold">{competitor.data.name}</h1>
        </div>
        <div className="mt-2 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <p className="min-w-0 flex-1 text-slate-600">{competitor.data.description}</p>
          <div className="flex shrink-0 flex-wrap gap-2">
            {competitor.data.status === "deleted" ? (
              <p className="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-600">
                Archived · read only
              </p>
            ) : (
              <>
                <button
                  className="rounded-lg border border-slate-300 px-4 py-2 font-medium disabled:text-slate-400"
                  disabled={!hasApproved || competitor.data.status !== "active" || runNow.isPending}
                  onClick={() => runNow.mutate()}
                  type="button"
                >
                  Run scan now
                </button>
                <button
                  aria-controls="competitor-info-settings"
                  aria-expanded={competitorInfoOpen}
                  className="rounded-lg border border-slate-300 px-4 py-2 font-medium"
                  onClick={() => setCompetitorInfoOpen((open) => !open)}
                  type="button"
                >
                  {competitorInfoOpen ? "Hide competitor info" : "Edit competitor info"}
                </button>
              </>
            )}
          </div>
        </div>
        <a
          className="section-link mt-2 inline-block"
          href={`https://${competitor.data.primary_domain}`}
          rel="noopener noreferrer"
          target="_blank"
        >
          {competitor.data.primary_domain}
        </a>
      </header>
      {discoveryNotice || notice ? <p role="status">{discoveryNotice || notice}</p> : null}
      {sourceUpdate.isError ||
      updateMonitor.isError ||
      archiveMonitor.isError ||
      runNow.isError ||
      discovery.isError ? (
        <p className="text-red-700" role="alert">
          {errorText(
            sourceUpdate.error ??
              updateMonitor.error ??
              archiveMonitor.error ??
              runNow.error ??
              discovery.error,
          )}
        </p>
      ) : null}
      {competitorInfoOpen ? (
        <div id="competitor-info-settings">
          <MonitorSettings
            competitor={competitor.data}
            hasApprovedSource={hasApproved}
            isPending={updateMonitor.isPending || archiveMonitor.isPending}
            onArchive={async () => {
              await archiveMonitor.mutateAsync();
            }}
            onSave={async (values) => {
              await updateMonitor.mutateAsync(values);
            }}
            onStatusChange={async (status) => {
              await updateMonitor.mutateAsync({ status });
            }}
          />
        </div>
      ) : null}
      {snapshot.data ? (
        <StartingSnapshot snapshot={snapshot.data} timeZone={me.data.timezone} />
      ) : null}
      {competitor.data.starting_snapshot_requested_at && !snapshot.data && !snapshotUnavailable ? (
        <section className="surface p-5" aria-labelledby="snapshot-pending-title">
          <p className="eyebrow">Starting Snapshot</p>
          <h2 className="mt-1 text-xl font-semibold" id="snapshot-pending-title">
            {competitor.data.status === "paused"
              ? "Snapshot generation is paused"
              : latestSnapshotRun &&
                  ["queued", "planning", "gathering", "synthesizing"].includes(
                    latestSnapshotRun.status,
                  )
                ? "The first scan is in progress"
                : "Snapshot generation is pending"}
          </h2>
          <p className="mt-2 text-slate-600">
            {latestSnapshotRun?.status === "failed"
              ? "The last scan could not produce a snapshot. Run another scan to retry."
              : competitor.data.status === "paused"
                ? "Resume monitoring and run a scan to create the requested snapshot."
                : "Scout will publish the snapshot after a qualifying scan completes with valid evidence."}
          </p>
          {latestSnapshotRun ? (
            <Link className="section-link mt-3 inline-block" href={`/runs/${latestSnapshotRun.id}`}>
              View scan progress
            </Link>
          ) : null}
        </section>
      ) : null}
      {snapshotUnavailable ? (
        <p className="text-red-700" role="alert">
          The Starting Snapshot could not be loaded. Other competitor information remains available.
        </p>
      ) : null}
      <CollapsibleSection defaultOpen id="recent-findings" title="Recent updates">
        <div className="flex justify-end">
          <Link className="section-link" href={`/findings?competitor_id=${competitorId}`}>
            View all updates
          </Link>
        </div>
        <form
          action="/findings"
          aria-label="Filter competitor updates"
          className="surface grid gap-4 p-4 sm:grid-cols-3"
          method="get"
        >
          <input name="competitor_id" type="hidden" value={competitorId} />
          <SelectField
            id="competitor-category-filter"
            label="Category"
            name="category"
            options={findingCategoryOptions}
          />
          <SelectField
            id="competitor-significance-filter"
            label="Significance"
            name="significance"
            options={findingSignificanceOptions}
          />
          <label className="text-sm font-medium">
            Published from
            <input
              className="mt-1 block min-h-10 w-full rounded-lg border border-slate-300 px-3 py-2"
              name="published_from"
              type="date"
            />
          </label>
          <button
            className="rounded-lg bg-slate-950 px-4 py-2 font-medium text-white sm:col-span-3 sm:justify-self-start"
            type="submit"
          >
            Filter updates
          </button>
        </form>
        {findings.data.items.length ? (
          <div className="space-y-3">
            {findings.data.items.map((finding) => (
              <FindingCard finding={finding} key={finding.id} timeZone={me.data.timezone} />
            ))}
          </div>
        ) : (
          <p className="text-sm text-slate-600">No updates for this competitor yet.</p>
        )}
      </CollapsibleSection>
      {competitor.data.status !== "deleted" ? (
        <CollapsibleSection id="competitor-sources" title="Sources">
          <p className="text-sm text-slate-600" role="status">
            {monitoredSourceCount
              ? `Scans use ${monitoredSourceCount} monitored ${monitoredSourceCount === 1 ? "source" : "sources"}.`
              : "Monitor at least one trusted source before activating monitoring."}
          </p>
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
        </CollapsibleSection>
      ) : null}
      <CollapsibleSection id="recent-runs" title="Recent scans">
        <div className="flex justify-end">
          <Link className="section-link" href={`/runs?competitor_id=${competitorId}`}>
            View all scans
          </Link>
        </div>
        {recentRuns.data.items.length ? (
          <ul className="space-y-2">
            {recentRuns.data.items.map((run) => (
              <li className="surface surface-interactive p-4" key={run.id}>
                <Link className="font-medium capitalize hover:underline" href={`/runs/${run.id}`}>
                  {runTypeLabel(run.run_type)}
                </Link>
                <span className="ml-3 text-sm capitalize text-slate-500">{run.status}</span>
                <span className="ml-3 text-sm text-slate-500">
                  {run.finding_count} update{run.finding_count === 1 ? "" : "s"}
                </span>
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
      </CollapsibleSection>
    </article>
  );
}
