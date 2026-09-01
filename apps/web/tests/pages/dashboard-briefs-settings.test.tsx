import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BriefDetailView, BriefsListView } from "@/components/pages/BriefViews";
import { DashboardView } from "@/components/pages/DashboardView";
import { SettingsView } from "@/components/pages/SettingsView";
import { apiGetClient, apiMutate } from "@/lib/api";
import { renderWithQuery } from "../query-test-utils";

vi.mock("@/lib/api", () => ({ apiGetClient: vi.fn(), apiMutate: vi.fn() }));
const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));

const competitor = {
  id: "11111111-1111-4111-8111-111111111111",
  name: "Acme",
  primary_domain: "acme.example",
  description: "Analytics",
  status: "active",
  daily_run_time_local: "08:30:00",
  created_at: "2026-08-01T08:00:00Z",
  updated_at: "2026-08-21T08:00:00Z",
};
const finding = {
  id: "55555555-5555-4555-8555-555555555555",
  competitor_id: competitor.id,
  originating_scout_run_id: "44444444-4444-4444-8444-444444444444",
  category: "pricing",
  title: "Acme changed pricing",
  summary: "A new annual tier appeared.",
  significance_explanation: "This changes the entry price.",
  significance_level: "high",
  confidence: 0.91,
  decision_rationale: "First-party evidence.",
  first_seen_at: "2026-08-21T08:00:00Z",
  last_seen_at: "2026-08-21T09:00:00Z",
  published_at: "2026-08-21T09:00:00Z",
};
const run = {
  id: finding.originating_scout_run_id,
  competitor_id: competitor.id,
  competitor_name: competitor.name,
  finding_count: 1,
  run_type: "daily_scout",
  status: "partial",
  scheduled_for: "2026-08-21T08:00:00Z",
  started_at: "2026-08-21T08:00:01Z",
  completed_at: "2026-08-21T08:05:00Z",
  failure_code: null,
  failure_summary: null,
  partial_reasons: ["One source timed out"],
  input_tokens: 100,
  output_tokens: 20,
  tool_calls: null,
  settled_cost_usd: null,
  created_at: "2026-08-21T08:00:00Z",
};
const brief = {
  id: "88888888-8888-4888-8888-888888888888",
  scout_run_id: "99999999-9999-4999-8999-999999999999",
  period_start: "2026-08-10",
  period_end: "2026-08-16",
  title: "Weekly competitor brief",
  executive_summary: "Acme introduced an annual tier.",
  published_at: "2026-08-17T08:00:00Z",
  created_at: "2026-08-17T08:00:00Z",
  sections: [
    {
      heading: "Pricing",
      narrative: "Acme introduced a new annual tier.",
      references: [{ finding_id: finding.id, statement: "The annual tier is now public." }],
    },
  ],
};
const me = {
  id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  email: "founder@example.com",
  display_name: "Founder",
  avatar_url: null,
  timezone: "Europe/Berlin",
  csrf_token: "csrf-token",
};
const settings = {
  display_name: "Founder",
  timezone: "Europe/Berlin",
  default_daily_time: "08:30:00",
  email_findings_enabled: false,
  email_weekly_brief_enabled: false,
  email_delivery_available: true,
};
const usage = {
  items: [
    {
      date: "2026-08-21",
      model: "competitor-scout-main",
      input_tokens: 100,
      output_tokens: 20,
      tool_calls: null,
      settled_cost_usd: null,
    },
  ],
};

function mockDashboard(data?: {
  competitors?: unknown[];
  findings?: unknown[];
  runs?: unknown[];
  briefs?: unknown[];
}) {
  vi.mocked(apiGetClient).mockImplementation(async (path) => {
    if (path === "/api/v1/me") return me as never;
    if (path.startsWith("/api/v1/competitors"))
      return { items: data?.competitors ?? [competitor], next_cursor: null } as never;
    if (path.startsWith("/api/v1/findings")) {
      const allFindings = data?.findings ?? [finding];
      const requestedLevel = new URL(path, "https://example.invalid").searchParams.get(
        "significance",
      );
      return {
        items: requestedLevel
          ? allFindings.filter(
              (item) =>
                typeof item === "object" &&
                item !== null &&
                "significance_level" in item &&
                item.significance_level === requestedLevel,
            )
          : allFindings,
        next_cursor: null,
      } as never;
    }
    if (path.startsWith("/api/v1/runs"))
      return { items: data?.runs ?? [run], next_cursor: null } as never;
    if (path.startsWith("/api/v1/briefs"))
      return { items: data?.briefs ?? [brief], next_cursor: null } as never;
    throw new Error(`Unexpected path ${path}`);
  });
}

afterEach(() => {
  vi.clearAllMocks();
  replace.mockClear();
});

describe("dashboard", () => {
  it("shows material findings, active competitors with latest status, run warnings, brief, and limit use", async () => {
    mockDashboard({
      findings: [
        finding,
        {
          ...finding,
          id: "77777777-7777-4777-8777-777777777777",
          title: "Critical signal",
          significance_level: "critical",
        },
        {
          ...finding,
          id: "66666666-6666-4666-8666-666666666666",
          title: "Low signal",
          significance_level: "low",
        },
      ],
    });
    renderWithQuery(<DashboardView />);
    expect(await screen.findByRole("heading", { name: "Overview" })).toBeInTheDocument();
    expect(screen.getByText("Intelligence overview")).toBeInTheDocument();
    expect(screen.getByText("Monitoring")).toBeInTheDocument();
    expect(screen.getByText("Recent important changes")).toBeInTheDocument();
    expect(screen.getByText("Monitoring issues")).toBeInTheDocument();
    expect(screen.queryByText("Live")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Add competitor" })).toHaveAttribute(
      "href",
      "/competitors/new",
    );
    expect(screen.getByRole("link", { name: "Acme changed pricing" })).toHaveAttribute(
      "href",
      `/findings/${finding.id}`,
    );
    expect(screen.getByRole("link", { name: "Critical signal" })).toHaveAttribute(
      "href",
      "/findings/77777777-7777-4777-8777-777777777777",
    );
    expect(screen.queryByText("Low signal")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Acme" })).toHaveAttribute(
      "href",
      `/competitors/${competitor.id}`,
    );
    expect(screen.getAllByText("partial").length).toBeGreaterThan(0);
    expect(screen.getByRole("alert")).toHaveTextContent("One source timed out");
    expect(screen.getByRole("link", { name: brief.title })).toHaveAttribute(
      "href",
      `/briefs/${brief.id}`,
    );
    expect(screen.getByText("1 of 10 competitor slots used")).toBeInTheDocument();
    expect(apiGetClient).toHaveBeenCalledWith(
      "/api/v1/findings?significance=critical&limit=5",
      expect.anything(),
    );
    expect(apiGetClient).toHaveBeenCalledWith(
      "/api/v1/findings?significance=high&limit=5",
      expect.anything(),
    );
    expect(apiGetClient).toHaveBeenCalledWith(
      "/api/v1/findings?significance=medium&limit=5",
      expect.anything(),
    );
  });

  it("has explicit loading, empty, and error states", async () => {
    const pending = new Promise<never>(() => undefined);
    vi.mocked(apiGetClient).mockReturnValue(pending);
    const loading = renderWithQuery(<DashboardView />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading dashboard");
    loading.unmount();

    mockDashboard({ competitors: [], findings: [], runs: [], briefs: [] });
    const empty = renderWithQuery(<DashboardView />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/competitors/new"));
    expect(screen.getByText("Taking you to guided setup…")).toBeInTheDocument();
    empty.unmount();

    vi.mocked(apiGetClient).mockRejectedValue(new Error("dashboard unavailable"));
    renderWithQuery(<DashboardView />);
    expect(await screen.findByRole("alert")).toHaveTextContent("dashboard unavailable");
  });
});

describe("weekly briefs", () => {
  it("lists historical briefs and renders grounded references to finding evidence", async () => {
    vi.mocked(apiGetClient).mockResolvedValueOnce({ items: [brief], next_cursor: null } as never);
    const list = renderWithQuery(<BriefsListView />);
    expect(await screen.findByRole("link", { name: brief.title })).toHaveAttribute(
      "href",
      `/briefs/${brief.id}`,
    );
    expect(screen.getByText(/Aug 10, 2026/)).toBeInTheDocument();
    list.unmount();

    vi.mocked(apiGetClient).mockResolvedValueOnce(brief as never);
    renderWithQuery(<BriefDetailView briefId={brief.id} />);
    expect(await screen.findByRole("heading", { name: "Pricing" })).toBeInTheDocument();
    expect(screen.getByText("The annual tier is now public.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View finding and evidence" })).toHaveAttribute(
      "href",
      `/findings/${finding.id}`,
    );
  });

  it("renders an honest empty week without fabricated references and exposes empty/error states", async () => {
    vi.mocked(apiGetClient).mockResolvedValueOnce({
      ...brief,
      title: "Weekly brief: no material changes",
      executive_summary: "No accepted material changes were published during this weekly period.",
      sections: [],
    } as never);
    const detail = renderWithQuery(<BriefDetailView briefId={brief.id} />);
    expect(
      await screen.findByText(
        "No accepted material changes were published during this weekly period.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /finding and evidence/i })).not.toBeInTheDocument();
    detail.unmount();

    vi.mocked(apiGetClient).mockResolvedValueOnce({ items: [], next_cursor: null } as never);
    const empty = renderWithQuery(<BriefsListView />);
    expect(await screen.findByText("No weekly briefs yet.")).toBeInTheDocument();
    empty.unmount();

    vi.mocked(apiGetClient).mockRejectedValueOnce(new Error("briefs unavailable"));
    renderWithQuery(<BriefsListView />);
    expect(await screen.findByRole("alert")).toHaveTextContent("briefs unavailable");
  });
});

describe("settings and usage", () => {
  function mockSettings() {
    vi.mocked(apiGetClient).mockImplementation(async (path) => {
      if (path === "/api/v1/me") return me as never;
      if (path === "/api/v1/settings") return settings as never;
      if (path === "/api/v1/usage/summary") return usage as never;
      throw new Error(`Unexpected path ${path}`);
    });
  }

  it("updates only public settings with CSRF and renders unknown aggregate usage honestly", async () => {
    mockSettings();
    vi.mocked(apiMutate).mockResolvedValue(settings as never);
    renderWithQuery(<SettingsView />);
    expect(await screen.findByLabelText("Display name")).toHaveValue("Founder");
    expect(screen.getByRole("heading", { name: "Profile" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Default schedule" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Notifications" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Usage" })).toBeInTheDocument();
    expect(screen.getByLabelText("Timezone")).toHaveValue("Europe/Berlin");
    expect(screen.getByLabelText("Default daily run time")).toHaveValue("08:30");
    expect(screen.getByLabelText("Important finding emails")).not.toBeChecked();
    expect(screen.getByLabelText("Weekly brief emails")).not.toBeChecked();
    expect(screen.getByText("competitor-scout-main")).toBeInTheDocument();
    expect(screen.getAllByText("Unknown")).toHaveLength(2);
    expect(screen.queryByLabelText(/model|budget|tool/i)).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Display name"), { target: { value: "New Founder" } });
    fireEvent.change(screen.getByLabelText("Timezone"), { target: { value: "UTC" } });
    fireEvent.change(screen.getByLabelText("Default daily run time"), {
      target: { value: "09:15" },
    });
    fireEvent.click(screen.getByLabelText("Important finding emails"));
    fireEvent.click(screen.getByRole("button", { name: "Save settings" }));
    await waitFor(() =>
      expect(apiMutate).toHaveBeenCalledWith(
        "/api/v1/settings",
        {
          body: {
            display_name: "New Founder",
            timezone: "UTC",
            default_daily_time: "09:15:00",
            email_findings_enabled: true,
            email_weekly_brief_enabled: false,
          },
          csrfToken: "csrf-token",
          method: "PATCH",
        },
        expect.anything(),
      ),
    );
    expect(await screen.findByRole("status")).toHaveTextContent("Settings saved");
  });

  it("explains and disables email preferences when delivery is unavailable", async () => {
    vi.mocked(apiGetClient).mockImplementation(async (path) => {
      if (path === "/api/v1/me") return me as never;
      if (path === "/api/v1/settings")
        return { ...settings, email_delivery_available: false } as never;
      if (path === "/api/v1/usage/summary") return usage as never;
      throw new Error(`Unexpected path ${path}`);
    });
    renderWithQuery(<SettingsView />);

    expect(
      await screen.findByText("Email delivery is not available for this workspace yet."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Important finding emails")).toBeDisabled();
    expect(screen.getByLabelText("Weekly brief emails")).toBeDisabled();
  });

  it("rejects invalid IANA timezones and disables submission while pending", async () => {
    mockSettings();
    let settle!: (value: typeof settings) => void;
    vi.mocked(apiMutate).mockReturnValue(
      new Promise((resolve) => {
        settle = resolve;
      }) as never,
    );
    renderWithQuery(<SettingsView />);
    const timezone = await screen.findByLabelText("Timezone");
    fireEvent.change(timezone, { target: { value: "Mars/Olympus" } });
    fireEvent.click(screen.getByRole("button", { name: "Save settings" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("valid IANA timezone");
    expect(apiMutate).not.toHaveBeenCalled();

    fireEvent.change(timezone, { target: { value: "America/New_York" } });
    fireEvent.click(screen.getByRole("button", { name: "Save settings" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled());
    await act(async () => settle(settings));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Save settings" })).toBeEnabled(),
    );
  });

  it("shows loading and errors without exposing controls prematurely", async () => {
    vi.mocked(apiGetClient).mockReturnValue(new Promise<never>(() => undefined));
    const loading = renderWithQuery(<SettingsView />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading settings");
    loading.unmount();
    vi.mocked(apiGetClient).mockRejectedValue(new Error("settings unavailable"));
    renderWithQuery(<SettingsView />);
    expect(await screen.findByRole("alert")).toHaveTextContent("settings unavailable");
  });
});
