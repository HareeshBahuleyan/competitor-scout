"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";

import { apiGetClient, apiMutate } from "@/lib/api";
import { meSchema, settingsSchema, usageSummarySchema } from "@/lib/schemas";

function errorText(error: unknown) {
  return error instanceof Error ? error.message : "Something went wrong.";
}

function validIanaTimezone(value: string) {
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: value }).format();
    return true;
  } catch {
    return false;
  }
}

function displayCost(value: string | null) {
  return value === null ? "Unknown" : `$${value}`;
}

export function SettingsView() {
  const [displayName, setDisplayName] = useState<string | null>(null);
  const [timezone, setTimezone] = useState<string | null>(null);
  const [defaultDailyTime, setDefaultDailyTime] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const me = useQuery({ queryKey: ["me"], queryFn: () => apiGetClient("/api/v1/me", meSchema) });
  const settings = useQuery({
    queryKey: ["settings"],
    queryFn: () => apiGetClient("/api/v1/settings", settingsSchema),
  });
  const usage = useQuery({
    queryKey: ["usage-summary"],
    queryFn: () => apiGetClient("/api/v1/usage/summary", usageSummarySchema),
  });

  const resolvedDisplayName = displayName ?? settings.data?.display_name ?? "";
  const resolvedTimezone = timezone ?? settings.data?.timezone ?? "";
  const resolvedDefaultDailyTime =
    defaultDailyTime ?? settings.data?.default_daily_time.slice(0, 5) ?? "";

  const update = useMutation({
    mutationFn: async () => {
      if (!me.data) throw new Error("Account information is unavailable.");
      const updated = await apiMutate(
        "/api/v1/settings",
        {
          body: {
            default_daily_time: `${resolvedDefaultDailyTime}:00`,
            display_name: resolvedDisplayName.trim(),
            timezone: resolvedTimezone,
          },
          csrfToken: me.data.csrf_token,
          method: "PATCH",
        },
        settingsSchema,
      );
      if (!updated) throw new Error("The settings response was empty.");
      return updated;
    },
    onSuccess: (updated) => {
      setDisplayName(updated.display_name);
      setTimezone(updated.timezone);
      setDefaultDailyTime(updated.default_daily_time.slice(0, 5));
      setSaved(true);
    },
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaved(false);
    if (!resolvedDisplayName.trim()) {
      setValidationError("Display name is required.");
      return;
    }
    if (!validIanaTimezone(resolvedTimezone)) {
      setValidationError("Enter a valid IANA timezone, such as Europe/Berlin or America/New_York.");
      return;
    }
    setValidationError(null);
    update.mutate();
  }

  if (me.isPending || settings.isPending || usage.isPending)
    return <p role="status">Loading settings…</p>;
  if (me.isError || settings.isError || usage.isError) {
    return (
      <p className="text-red-700" role="alert">
        {errorText(me.error ?? settings.error ?? usage.error)}
      </p>
    );
  }

  return (
    <section className="space-y-8">
      <header>
        <h1 className="text-3xl font-bold">Settings</h1>
        <p className="mt-1 text-slate-600">Update your profile and default local schedule.</p>
      </header>
      <form
        className="max-w-2xl space-y-5 rounded-xl border border-slate-200 bg-white p-6"
        onSubmit={submit}
      >
        <label className="block text-sm font-medium">
          Display name
          <input
            className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2"
            maxLength={200}
            onChange={(event) => setDisplayName(event.target.value)}
            required
            type="text"
            value={resolvedDisplayName}
          />
        </label>
        <label className="block text-sm font-medium">
          Timezone
          <input
            aria-describedby="timezone-help"
            className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2"
            maxLength={64}
            onChange={(event) => setTimezone(event.target.value)}
            required
            type="text"
            value={resolvedTimezone}
          />
        </label>
        <p className="text-sm text-slate-500" id="timezone-help">
          Use an IANA timezone, for example Europe/Berlin.
        </p>
        <label className="block text-sm font-medium">
          Default daily run time
          <input
            className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2"
            onChange={(event) => setDefaultDailyTime(event.target.value)}
            required
            type="time"
            value={resolvedDefaultDailyTime}
          />
        </label>
        {validationError ? (
          <p className="text-sm text-red-700" role="alert">
            {validationError}
          </p>
        ) : null}
        {update.isError ? (
          <p className="text-sm text-red-700" role="alert">
            {errorText(update.error)}
          </p>
        ) : null}
        {saved ? (
          <p className="text-sm text-green-700" role="status">
            Settings saved.
          </p>
        ) : null}
        <button
          className="rounded-lg bg-slate-950 px-4 py-2 font-medium text-white disabled:bg-slate-400"
          disabled={update.isPending}
          type="submit"
        >
          {update.isPending ? "Saving…" : "Save settings"}
        </button>
      </form>

      <section aria-labelledby="usage-heading" className="space-y-4">
        <div>
          <h2 className="text-xl font-semibold" id="usage-heading">
            Usage summary
          </h2>
          <p className="mt-1 text-sm text-slate-600">
            Informational totals grouped by date and configured model.
          </p>
        </div>
        {usage.data.items.length ? (
          <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
            <table className="w-full border-collapse text-left text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className="p-3">Date</th>
                  <th className="p-3">Model</th>
                  <th className="p-3">Input tokens</th>
                  <th className="p-3">Output tokens</th>
                  <th className="p-3">Tool calls</th>
                  <th className="p-3">Settled cost</th>
                </tr>
              </thead>
              <tbody>
                {usage.data.items.map((row) => (
                  <tr className="border-t border-slate-200" key={`${row.date}-${row.model}`}>
                    <td className="p-3">{row.date}</td>
                    <td className="p-3">{row.model}</td>
                    <td className="p-3">{row.input_tokens.toLocaleString()}</td>
                    <td className="p-3">{row.output_tokens.toLocaleString()}</td>
                    <td className="p-3">{row.tool_calls ?? "Unknown"}</td>
                    <td className="p-3">{displayCost(row.settled_cost_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="rounded-xl border border-dashed border-slate-300 p-6 text-slate-600">
            No usage has been recorded yet.
          </p>
        )}
      </section>
    </section>
  );
}
