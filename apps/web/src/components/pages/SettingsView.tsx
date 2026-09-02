"use client";

import { Button } from "@heroui/react";
import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { type FormEvent, useState } from "react";

import { LoadingState } from "@/components/ui/LoadingState";
import { browserTimezone, canonicalTimezone, TimezoneSelect } from "@/components/ui/TimezoneSelect";
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

  const detectedTimezone = browserTimezone();
  const detectedCanonical = detectedTimezone ? canonicalTimezone(detectedTimezone) : null;

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
      setValidationError("Choose a timezone from the list.");
      return;
    }
    setValidationError(null);
    update.mutate();
  }

  if (me.isPending || settings.isPending || usage.isPending) {
    return <LoadingState label="Loading settings…" rows={4} />;
  }
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
        <p className="eyebrow">Preferences</p>
        <h1 className="mt-1 text-4xl font-semibold">Settings</h1>
        <p className="mt-2 text-slate-600">Update your profile and default local schedule.</p>
      </header>
      <form className="surface max-w-2xl space-y-6 p-6" onSubmit={submit}>
        <section aria-labelledby="profile-heading" className="space-y-4">
          <div>
            <h2 className="text-lg font-semibold" id="profile-heading">
              Profile
            </h2>
            <p className="mt-1 text-sm text-slate-500">How your account is identified.</p>
          </div>
          <label className="block text-sm font-medium">
            Display name
            <input
              className="mt-1 block min-h-10 w-full rounded-xl border px-3 py-2"
              maxLength={200}
              onChange={(event) => setDisplayName(event.target.value)}
              required
              type="text"
              value={resolvedDisplayName}
            />
          </label>
          <TimezoneSelect
            action={
              detectedTimezone && canonicalTimezone(resolvedTimezone) !== detectedCanonical ? (
                <button
                  className="section-link"
                  onClick={() => setTimezone(detectedTimezone)}
                  type="button"
                >
                  Use my current region
                </button>
              ) : null
            }
            description="Pick your region and nearest city. Scans and run times follow it."
            label="Timezone"
            onChange={setTimezone}
            value={resolvedTimezone}
          />
        </section>

        <section
          aria-labelledby="schedule-heading"
          className="space-y-4 border-t border-slate-100 pt-6"
        >
          <div>
            <h2 className="text-lg font-semibold" id="schedule-heading">
              Default schedule
            </h2>
            <p className="mt-1 text-sm text-slate-500">When new monitors run by default.</p>
          </div>
          <label className="block text-sm font-medium">
            Default daily run time
            <input
              className="mt-1 block min-h-10 rounded-xl border px-3 py-2"
              onChange={(event) => setDefaultDailyTime(event.target.value)}
              required
              type="time"
              value={resolvedDefaultDailyTime}
            />
          </label>
        </section>
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
        <Button
          className="bg-[#d34d50] px-4 font-semibold text-white"
          isDisabled={update.isPending}
          type="submit"
        >
          {update.isPending ? "Saving…" : "Save settings"}
        </Button>
      </form>

      <section aria-labelledby="usage-heading" className="space-y-4">
        <div>
          <p className="eyebrow">Usage summary</p>
          <h2 className="mt-1 text-xl font-semibold" id="usage-heading">
            Usage
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

      <section aria-labelledby="advanced-heading" className="space-y-3">
        <div>
          <p className="eyebrow">Advanced</p>
          <h2 className="mt-1 text-xl font-semibold" id="advanced-heading">
            Troubleshooting
          </h2>
        </div>
        <div className="surface max-w-2xl space-y-2 p-6">
          <h3 className="font-semibold">Scan activity</h3>
          <p className="text-sm text-slate-600">
            Execution history for every scan, including per-task detail and audit status. Open this
            when an expected update is missing or a scan reports a problem.
          </p>
          <Link className="section-link inline-block" href="/runs">
            View scan activity
          </Link>
        </div>
      </section>
    </section>
  );
}
