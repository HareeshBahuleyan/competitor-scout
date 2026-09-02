import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
  partial_reasons: ["child_task_failed"],
  partial_summaries: ["Some research tasks could not complete."],
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
  coverage: {
    competitors: [
      {
        competitor_id: competitor.id,
        competitor_name: competitor.name,
      },
    ],
    completed_scan_count: 5,
    partial_scan_count: 0,
    failed_scan_count: 0,
    inspected_source_count: 4,
    coverage_complete: true,
  },
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
};
const usage = {
  items: [
    {
      date: "2026-08-21",
      model: "competitor-scout-main",
      input_tokens: 100,
      output_tokens: 20,
      settled_cost_usd: null,
    },
  ],
};

function digestOverview(briefs: unknown[] = [brief]) {
  const latest = briefs[0] ?? null;
  return {
    state: latest ? "archive_available" : "awaiting_first_digest",
    next_digest_at: "2026-08-24T06:00:00Z",
    active_competitor_count: 1,
    approved_source_count: 4,
    incomplete_competitor: null,
    running_scan: null,
    snapshots: [
      {
        snapshot_id: "99999999-9999-4999-8999-999999999998",
        competitor_id: competitor.id,
        competitor_name: competitor.name,
      },
    ],
    monitoring_issue_count: 0,
    latest_brief: latest,
  };
}

function mockBriefList(items: unknown[], overview: unknown = digestOverview(items)) {
  vi.mocked(apiGetClient).mockImplementation(async (path) => {
    if (path === "/api/v1/me") return me as never;
    if (path === "/api/v1/briefs") return { items, next_cursor: null } as never;
    if (path === "/api/v1/briefs/overview") return overview as never;
    throw new Error(`Unexpected path ${path}`);
  });
}

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
    if (path === "/api/v1/briefs/overview") return digestOverview(data?.briefs ?? [brief]) as never;
    throw new Error(`Unexpected path ${path}`);
  });
}

afterEach(() => {
  vi.clearAllMocks();
  replace.mockClear();
});

describe("dashboard", () => {
  it("shows material findings, active competitors with latest status, run warnings, and brief", async () => {
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
    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
    expect(screen.getByText("Intelligence overview")).toBeInTheDocument();
    expect(screen.queryByText("Active monitors")).not.toBeInTheDocument();
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
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: brief.title })).toHaveAttribute(
      "href",
      `/briefs/${brief.id}`,
    );
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

  it("shows digest readiness before the first edition exists", async () => {
    mockDashboard({ briefs: [] });
    renderWithQuery(<DashboardView />);

    expect(await screen.findByText("Your first Weekly Digest is scheduled")).toBeInTheDocument();
    expect(
      screen.getByText(/monitoring 1 competitor across 4 approved sources/i),
    ).toBeInTheDocument();
    expect(screen.queryByText("No Weekly Digest yet.")).not.toBeInTheDocument();
  });

  it("has explicit loading, empty, and error states", async () => {
    const pending = new Promise<never>(() => undefined);
    vi.mocked(apiGetClient).mockReturnValue(pending);
    const loading = renderWithQuery(<DashboardView />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading dashboard");
    loading.unmount();

    mockDashboard({ competitors: [], findings: [], runs: [], briefs: [] });
    const empty = renderWithQuery(<DashboardView />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/competitors/new?first=1"));
    expect(screen.getByText("Taking you to guided setup…")).toBeInTheDocument();
    empty.unmount();

    vi.mocked(apiGetClient).mockRejectedValue(new Error("dashboard unavailable"));
    renderWithQuery(<DashboardView />);
    expect(await screen.findByRole("alert")).toHaveTextContent("dashboard unavailable");
  });
});

describe("weekly briefs", () => {
  it("renders setup-required, setup-incomplete, and first-scan-running states", async () => {
    const baseOverview = {
      ...digestOverview([]),
      next_digest_at: null,
      active_competitor_count: 0,
      approved_source_count: 0,
      snapshots: [],
    };
    mockBriefList([], { ...baseOverview, state: "setup_required" });
    const required = renderWithQuery(<BriefsListView />);
    expect(await screen.findByRole("link", { name: "Set up a competitor" })).toHaveAttribute(
      "href",
      "/competitors/new",
    );
    required.unmount();

    mockBriefList([], {
      ...baseOverview,
      state: "setup_incomplete",
      incomplete_competitor: {
        competitor_id: competitor.id,
        competitor_name: competitor.name,
        status: "discovering",
      },
    });
    const incomplete = renderWithQuery(<BriefsListView />);
    expect(await screen.findByRole("link", { name: "Finish Acme setup" })).toHaveAttribute(
      "href",
      `/competitors/${competitor.id}`,
    );
    incomplete.unmount();

    mockBriefList([], {
      ...baseOverview,
      state: "initial_scan_running",
      active_competitor_count: 1,
      running_scan: {
        run_id: run.id,
        competitor_id: competitor.id,
        competitor_name: competitor.name,
        status: "gathering",
      },
    });
    renderWithQuery(<BriefsListView />);
    expect(await screen.findByRole("link", { name: "View scan progress" })).toHaveAttribute(
      "href",
      `/runs/${run.id}`,
    );
  });

  it("separates the current digest from archive history and renders grounded references", async () => {
    const olderBrief = {
      ...brief,
      id: "77777777-7777-4777-8777-777777777777",
      title: "Earlier pricing movement",
      period_start: "2026-08-03",
      period_end: "2026-08-09",
      published_at: "2026-08-10T08:00:00Z",
      created_at: "2026-08-10T08:00:00Z",
    };
    mockBriefList([brief, olderBrief]);
    const list = renderWithQuery(<BriefsListView />);
    expect(await screen.findByRole("link", { name: brief.title })).toHaveAttribute(
      "href",
      `/briefs/${brief.id}`,
    );
    expect(screen.getByRole("link", { name: olderBrief.title })).toHaveAttribute(
      "href",
      `/briefs/${olderBrief.id}`,
    );
    expect(screen.getByText(/Aug 3, 2026/)).toBeInTheDocument();
    list.unmount();

    vi.mocked(apiGetClient).mockResolvedValue(brief as never);
    renderWithQuery(<BriefDetailView briefId={brief.id} />);
    expect(await screen.findByRole("heading", { name: "Pricing" })).toBeInTheDocument();
    expect(screen.getByText("The annual tier is now public.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View the update and its evidence" })).toHaveAttribute(
      "href",
      `/findings/${finding.id}`,
    );
    await userEvent.click(screen.getByText("Monitoring coverage"));
    expect(screen.getByText("Completed scans")).toBeVisible();
  });

  it("renders an honest quiet week and a readiness state instead of a false empty report", async () => {
    vi.mocked(apiGetClient).mockResolvedValue({
      ...brief,
      title: "No important changes found this week",
      executive_summary: "No accepted material changes were published during this weekly period.",
      sections: [],
      coverage: {
        ...brief.coverage,
        completed_scan_count: 4,
        partial_scan_count: 1,
        coverage_complete: false,
      },
    } as never);
    const detail = renderWithQuery(<BriefDetailView briefId={brief.id} />);
    expect(
      await screen.findByText(
        "No accepted material changes were published during this weekly period.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/monitoring result, not a missing report/i)).toBeInTheDocument();
    expect(screen.getByText(/may not cover every monitored source/i)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /finding and evidence/i })).not.toBeInTheDocument();
    detail.unmount();

    vi.mocked(apiGetClient).mockResolvedValue({ ...brief, coverage: null } as never);
    const historical = renderWithQuery(<BriefDetailView briefId={brief.id} />);
    expect(await screen.findByText(/not recorded for this historical digest/i)).toBeInTheDocument();
    expect(screen.queryByText("Completed scans")).not.toBeInTheDocument();
    historical.unmount();

    mockBriefList([]);
    const empty = renderWithQuery(<BriefsListView />);
    expect(await screen.findByText("Your first Weekly Digest is scheduled")).toBeInTheDocument();
    expect(screen.getByText(/archive will begin/i)).toBeInTheDocument();
    expect(screen.queryByText("No Weekly Digest yet.")).not.toBeInTheDocument();
    empty.unmount();

    vi.mocked(apiGetClient).mockRejectedValue(new Error("briefs unavailable"));
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
    expect(screen.getByRole("heading", { name: "Usage" })).toBeInTheDocument();
    const timezone = screen.getByRole("button", { name: /Timezone/ });
    expect(timezone).toHaveTextContent("Berlin — Central European Time");
    expect(screen.getByLabelText("Default daily run time")).toHaveValue("08:30");
    expect(screen.getByText("competitor-scout-main")).toBeInTheDocument();
    expect(screen.getAllByText("Unknown")).toHaveLength(1);
    expect(screen.queryByLabelText(/model|budget|tool/i)).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Display name"), { target: { value: "New Founder" } });
    const user = userEvent.setup();
    await user.click(timezone);
    await user.click(screen.getByRole("option", { name: /Coordinated Universal Time/ }));
    fireEvent.change(screen.getByLabelText("Default daily run time"), {
      target: { value: "09:15" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save settings" }));
    await waitFor(() =>
      expect(apiMutate).toHaveBeenCalledWith(
        "/api/v1/settings",
        {
          body: {
            display_name: "New Founder",
            timezone: "Etc/UTC",
            default_daily_time: "09:15:00",
          },
          csrfToken: "csrf-token",
          method: "PATCH",
        },
        expect.anything(),
      ),
    );
    expect(await screen.findByRole("status")).toHaveTextContent("Settings saved");
  });

  it("only offers real timezones grouped by region and disables submission while pending", async () => {
    mockSettings();
    let settle!: (value: typeof settings) => void;
    vi.mocked(apiMutate).mockReturnValue(
      new Promise((resolve) => {
        settle = resolve;
      }) as never,
    );
    const user = userEvent.setup();
    renderWithQuery(<SettingsView />);
    await user.click(await screen.findByRole("button", { name: /Timezone/ }));

    const labels = () => screen.getAllByRole("option").map((option) => option.textContent ?? "");
    // The default list stays short; the full database is one click away.
    expect(labels().length).toBeLessThan(50);
    expect(labels().join("|")).not.toContain("Colombo");
    expect(screen.getAllByRole("group").map((group) => group.textContent?.slice(0, 20))).toEqual([
      expect.stringContaining("Universal"),
      expect.stringContaining("Americas"),
      expect.stringContaining("Europe"),
      expect.stringContaining("Africa & Middle East"),
      expect.stringContaining("Asia"),
      expect.stringContaining("Pacific"),
    ]);
    await user.keyboard("{Escape}");

    await user.click(screen.getByRole("button", { name: "Show all timezones" }));
    await user.click(screen.getByRole("button", { name: /Timezone/ }));
    expect(labels().length).toBeGreaterThan(300);
    expect(labels().join("|")).toContain("Colombo");
    await user.keyboard("{Escape}");
    await user.click(screen.getByRole("button", { name: "Show common timezones" }));

    await user.click(screen.getByRole("button", { name: /Timezone/ }));
    await user.click(screen.getByRole("option", { name: /New York — Eastern Time/ }));
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
