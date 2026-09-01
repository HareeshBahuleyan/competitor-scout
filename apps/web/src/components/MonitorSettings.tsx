"use client";

import { useRef, useState, type FormEvent } from "react";

import type { Competitor } from "@/lib/schemas";

type EditableMonitor = Pick<Competitor, "daily_run_time_local" | "description" | "name">;

type MonitorSettingsProps = {
  competitor: Competitor;
  hasApprovedSource: boolean;
  isPending?: boolean;
  onAddSource: (url: string) => Promise<void>;
  onArchive: () => Promise<void>;
  onSave: (values: EditableMonitor) => Promise<void>;
  onStatusChange: (status: "active" | "paused") => Promise<void>;
};

export function monitorLabel(status: Competitor["status"], hasIssue: boolean) {
  if (hasIssue) return "Needs attention";
  if (status === "active") return "Monitoring daily";
  if (status === "paused") return "Paused";
  return "Needs sources";
}

export function MonitorSettings({
  competitor,
  hasApprovedSource,
  isPending = false,
  onAddSource,
  onArchive,
  onSave,
  onStatusChange,
}: MonitorSettingsProps) {
  const [name, setName] = useState(competitor.name);
  const [description, setDescription] = useState(competitor.description);
  const [dailyTime, setDailyTime] = useState(competitor.daily_run_time_local.slice(0, 5));
  const [sourceUrl, setSourceUrl] = useState("");
  const [archiveOpen, setArchiveOpen] = useState(false);
  const archiveButton = useRef<HTMLButtonElement>(null);

  async function save(event: FormEvent) {
    event.preventDefault();
    await onSave({
      daily_run_time_local: `${dailyTime}:00`,
      description: description.trim(),
      name: name.trim(),
    });
  }

  async function addSource(event: FormEvent) {
    event.preventDefault();
    await onAddSource(sourceUrl.trim());
    setSourceUrl("");
  }

  function closeArchive() {
    setArchiveOpen(false);
    requestAnimationFrame(() => archiveButton.current?.focus());
  }

  return (
    <section aria-labelledby="monitor-settings-heading" className="surface space-y-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="eyebrow">Monitor status</p>
          <h2 className="mt-1 text-xl font-semibold" id="monitor-settings-heading">
            {monitorLabel(competitor.status, !hasApprovedSource)}
          </h2>
        </div>
        {competitor.status === "active" ? (
          <button
            className="rounded-lg border border-slate-300 px-4 py-2 font-medium disabled:text-slate-400"
            disabled={isPending}
            onClick={() => void onStatusChange("paused")}
            type="button"
          >
            Pause monitoring
          </button>
        ) : (
          <button
            className="rounded-lg bg-slate-950 px-4 py-2 font-medium text-white disabled:bg-slate-400"
            disabled={!hasApprovedSource || isPending}
            onClick={() => void onStatusChange("active")}
            type="button"
          >
            Resume monitoring
          </button>
        )}
      </div>

      <form className="grid gap-4 sm:grid-cols-2" onSubmit={save}>
        <label className="text-sm font-medium">
          Monitor name
          <input
            className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2"
            onChange={(event) => setName(event.target.value)}
            required
            value={name}
          />
        </label>
        <label className="text-sm font-medium">
          Daily run time
          <input
            className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2"
            onChange={(event) => setDailyTime(event.target.value)}
            required
            type="time"
            value={dailyTime}
          />
        </label>
        <label className="text-sm font-medium sm:col-span-2">
          Description
          <textarea
            className="mt-1 block min-h-24 w-full rounded-lg border border-slate-300 px-3 py-2"
            onChange={(event) => setDescription(event.target.value)}
            value={description}
          />
        </label>
        <div className="sm:col-span-2">
          <button
            className="rounded-lg bg-slate-950 px-4 py-2 font-medium text-white disabled:bg-slate-400"
            disabled={isPending}
            type="submit"
          >
            Save monitor
          </button>
        </div>
      </form>

      <form className="border-t border-slate-200 pt-5" onSubmit={addSource}>
        <label className="text-sm font-medium">
          Add first-party source
          <span className="mt-1 flex flex-col gap-2 sm:flex-row">
            <input
              className="min-w-0 flex-1 rounded-lg border border-slate-300 px-3 py-2"
              onChange={(event) => setSourceUrl(event.target.value)}
              placeholder={`https://${competitor.primary_domain}/pricing`}
              required
              type="url"
              value={sourceUrl}
            />
            <button
              className="rounded-lg border border-slate-300 px-4 py-2 font-medium disabled:text-slate-400"
              disabled={isPending}
              type="submit"
            >
              Add source
            </button>
          </span>
        </label>
      </form>

      <div className="border-t border-slate-200 pt-5">
        <button
          className="font-medium text-red-700 hover:underline"
          onClick={() => setArchiveOpen(true)}
          ref={archiveButton}
          type="button"
        >
          Archive monitor
        </button>
        <p className="mt-1 text-sm text-slate-500">
          Stops monitoring and removes this competitor from your active workspace.
        </p>
      </div>

      {archiveOpen ? (
        <div
          aria-labelledby="archive-monitor-heading"
          aria-modal="true"
          className="fixed inset-0 z-50 grid place-items-center bg-slate-950/40 p-4"
          role="dialog"
        >
          <div className="surface max-w-md space-y-4 p-6">
            <h2 className="text-xl font-semibold" id="archive-monitor-heading">
              Archive {competitor.name}?
            </h2>
            <p className="text-sm text-slate-600">
              Scheduled monitoring will stop. Existing findings and run history are retained for
              audit purposes.
            </p>
            <div className="flex justify-end gap-2">
              <button
                autoFocus
                className="rounded-lg border border-slate-300 px-4 py-2 font-medium"
                onClick={closeArchive}
                type="button"
              >
                Keep monitor
              </button>
              <button
                className="rounded-lg bg-red-700 px-4 py-2 font-medium text-white"
                disabled={isPending}
                onClick={() => void onArchive()}
                type="button"
              >
                Archive {competitor.name}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
