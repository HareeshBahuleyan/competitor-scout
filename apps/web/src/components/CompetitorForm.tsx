"use client";

import { useState, type FormEvent } from "react";

export type CompetitorFormValues = {
  name: string;
  primary_domain: string;
  description: string;
  daily_run_time_local: string;
};

type CompetitorFormProps = {
  initialValues?: Partial<CompetitorFormValues>;
  isSubmitting?: boolean;
  onSubmit: (values: CompetitorFormValues) => Promise<void> | void;
};

type FormErrors = Partial<Record<"name" | "primary_domain", string>>;

const domainPattern =
  /^(?=.{3,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/i;

function normalizePrimaryDomain(value: string): string | null {
  const stripped = value.trim();
  if (!stripped) return null;

  try {
    const url = new URL(stripped.includes("://") ? stripped : `https://${stripped}`);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.port) {
      return null;
    }
    const hostname = url.hostname.replace(/\.$/, "").toLowerCase();
    return domainPattern.test(hostname) ? hostname : null;
  } catch {
    return null;
  }
}

export function CompetitorForm({
  initialValues,
  isSubmitting = false,
  onSubmit,
}: CompetitorFormProps) {
  const [values, setValues] = useState({
    name: initialValues?.name ?? "",
    primary_domain: initialValues?.primary_domain ?? "",
    description: initialValues?.description ?? "",
    daily_run_time_local: (initialValues?.daily_run_time_local ?? "08:00:00").slice(0, 5),
  });
  const [errors, setErrors] = useState<FormErrors>({});

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const name = values.name.trim();
    const primaryDomain = normalizePrimaryDomain(values.primary_domain);
    const nextErrors: FormErrors = {};
    if (!name) {
      nextErrors.name = "Competitor name is required.";
    }
    if (primaryDomain === null) {
      nextErrors.primary_domain = "Enter a valid domain or website URL.";
    }
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0 || primaryDomain === null) {
      return;
    }

    void onSubmit({
      name,
      primary_domain: primaryDomain,
      description: values.description.trim(),
      daily_run_time_local: `${values.daily_run_time_local}:00`,
    });
  }

  return (
    <form aria-label="Competitor details" className="space-y-5" noValidate onSubmit={submit}>
      <div>
        <label className="block text-sm font-medium text-slate-800" htmlFor="competitor-name">
          Competitor name
        </label>
        <input
          aria-describedby={errors.name ? "competitor-name-error" : undefined}
          aria-invalid={Boolean(errors.name)}
          className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 disabled:bg-slate-100"
          disabled={isSubmitting}
          id="competitor-name"
          maxLength={200}
          name="name"
          onChange={(event) => setValues({ ...values, name: event.target.value })}
          type="text"
          value={values.name}
        />
        {errors.name ? (
          <p className="mt-1 text-sm text-red-700" id="competitor-name-error">
            {errors.name}
          </p>
        ) : null}
      </div>

      <div>
        <label className="block text-sm font-medium text-slate-800" htmlFor="primary-domain">
          Primary domain
        </label>
        <input
          aria-describedby={errors.primary_domain ? "primary-domain-error" : undefined}
          aria-invalid={Boolean(errors.primary_domain)}
          autoCapitalize="none"
          className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 disabled:bg-slate-100"
          disabled={isSubmitting}
          id="primary-domain"
          inputMode="url"
          maxLength={2048}
          placeholder="example.com or https://example.com"
          name="primary_domain"
          onChange={(event) => setValues({ ...values, primary_domain: event.target.value })}
          spellCheck={false}
          type="text"
          value={values.primary_domain}
        />
        {errors.primary_domain ? (
          <p className="mt-1 text-sm text-red-700" id="primary-domain-error">
            {errors.primary_domain}
          </p>
        ) : null}
      </div>

      <div>
        <label className="block text-sm font-medium text-slate-800" htmlFor="description">
          Description
        </label>
        <textarea
          className="mt-2 min-h-28 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 disabled:bg-slate-100"
          disabled={isSubmitting}
          id="description"
          maxLength={2000}
          name="description"
          onChange={(event) => setValues({ ...values, description: event.target.value })}
          value={values.description}
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-slate-800" htmlFor="daily-run-time">
          Daily run time
        </label>
        <input
          className="mt-2 rounded-lg border border-slate-300 bg-white px-3 py-2 disabled:bg-slate-100"
          disabled={isSubmitting}
          id="daily-run-time"
          name="daily_run_time_local"
          onChange={(event) => setValues({ ...values, daily_run_time_local: event.target.value })}
          required
          type="time"
          value={values.daily_run_time_local}
        />
      </div>

      <button
        className="rounded-lg bg-slate-950 px-4 py-2.5 font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-400"
        disabled={isSubmitting}
        type="submit"
      >
        {isSubmitting ? "Saving competitor…" : "Save competitor"}
      </button>
    </form>
  );
}
