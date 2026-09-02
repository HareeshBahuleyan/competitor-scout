"use client";

import { AlertDialog } from "@heroui/react";
import { useState, type FormEvent } from "react";

import type { Competitor } from "@/lib/schemas";

type EditableMonitor = Pick<Competitor, "daily_run_time_local" | "description" | "name">;

type MonitorSettingsProps = {
  competitor: Competitor;
  hasApprovedSource: boolean;
  isPending?: boolean;
  onArchive: () => Promise<void>;
  onSave: (values: EditableMonitor) => Promise<void>;
  onStatusChange: (status: "active" | "paused") => Promise<void>;
};

export function monitorLabel(status: Competitor["status"], hasApprovedSource: boolean) {
  if (!hasApprovedSource) return "Needs a monitored source";
  if (status === "active") return "Monitoring daily";
  if (status === "paused") return "Paused";
  return "Ready to monitor";
}

export function MonitorSettings({
  competitor,
  hasApprovedSource,
  isPending = false,
  onArchive,
  onSave,
  onStatusChange,
}: MonitorSettingsProps) {
  const [name, setName] = useState(competitor.name);
  const [description, setDescription] = useState(competitor.description);
  const [dailyTime, setDailyTime] = useState(competitor.daily_run_time_local.slice(0, 5));

  async function save(event: FormEvent) {
    event.preventDefault();
    await onSave({
      daily_run_time_local: `${dailyTime}:00`,
      description: description.trim(),
      name: name.trim(),
    });
  }

  return (
    <section aria-labelledby="monitor-settings-heading" className="surface space-y-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="eyebrow">Monitor status</p>
          <h2 className="mt-1 text-xl font-semibold" id="monitor-settings-heading">
            {monitorLabel(competitor.status, hasApprovedSource)}
          </h2>
        </div>
        {competitor.status === "active" ? (
          <button
            className="min-h-10 rounded-lg border border-slate-300 px-4 py-2 font-medium disabled:text-slate-400"
            disabled={isPending}
            onClick={() => void onStatusChange("paused")}
            type="button"
          >
            Pause monitoring
          </button>
        ) : (
          <button
            className="min-h-10 rounded-lg bg-slate-950 px-4 py-2 font-medium text-white disabled:bg-slate-400"
            disabled={!hasApprovedSource || isPending}
            onClick={() => void onStatusChange("active")}
            type="button"
          >
            Resume monitoring
          </button>
        )}
      </div>

      <form className="grid gap-4 sm:grid-cols-2" onSubmit={save}>
        <label className="field-label">
          Monitor name
          <input
            className="mt-1 block min-h-10 w-full rounded-lg border border-slate-300 px-3 py-2"
            maxLength={200}
            onChange={(event) => setName(event.target.value)}
            required
            value={name}
          />
        </label>
        <label className="field-label">
          Daily scan time
          <input
            className="mt-1 block min-h-10 w-full rounded-lg border border-slate-300 px-3 py-2"
            onChange={(event) => setDailyTime(event.target.value)}
            required
            type="time"
            value={dailyTime}
          />
        </label>
        <label className="field-label sm:col-span-2">
          Description
          <textarea
            className="mt-1 block min-h-24 w-full rounded-lg border border-slate-300 px-3 py-2"
            maxLength={2000}
            onChange={(event) => setDescription(event.target.value)}
            value={description}
          />
        </label>
        <div className="sm:col-span-2">
          <button
            className="min-h-10 rounded-lg bg-slate-950 px-4 py-2 font-medium text-white disabled:bg-slate-400"
            disabled={!name.trim() || isPending}
            type="submit"
          >
            {isPending ? "Saving…" : "Save monitor"}
          </button>
        </div>
      </form>

      <div className="border-t border-slate-200 pt-5">
        {isPending ? (
          <button className="min-h-10 font-medium text-slate-400" disabled type="button">
            Archive monitor
          </button>
        ) : (
          <AlertDialog>
            <AlertDialog.Trigger className="inline-flex min-h-10 cursor-pointer items-center font-medium text-[var(--color-danger)] underline-offset-4 hover:underline">
              Archive monitor
            </AlertDialog.Trigger>
            <AlertDialog.Backdrop isKeyboardDismissDisabled={false}>
              <AlertDialog.Container placement="center" size="md">
                <AlertDialog.Dialog>
                  <AlertDialog.Header>
                    <AlertDialog.Icon status="danger" />
                    <AlertDialog.Heading>
                      Archive {name.trim() || competitor.name}?
                    </AlertDialog.Heading>
                  </AlertDialog.Header>
                  <AlertDialog.Body>
                    Scheduled monitoring will stop and this competitor will leave the active
                    workspace. Existing updates and scan history will be retained.
                  </AlertDialog.Body>
                  <AlertDialog.Footer>
                    <AlertDialog.CloseTrigger>Keep monitor</AlertDialog.CloseTrigger>
                    <button
                      className="min-h-10 rounded-lg bg-[var(--color-danger)] px-4 py-2 font-medium text-white"
                      onClick={() => void onArchive()}
                      type="button"
                    >
                      Archive {name.trim() || competitor.name}
                    </button>
                  </AlertDialog.Footer>
                </AlertDialog.Dialog>
              </AlertDialog.Container>
            </AlertDialog.Backdrop>
          </AlertDialog>
        )}
        <p className="mt-1 text-sm text-slate-500">
          Stops monitoring while retaining existing updates and scan history.
        </p>
      </div>
    </section>
  );
}
