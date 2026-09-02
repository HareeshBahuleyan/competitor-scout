import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  CompetitorDetailView,
  CompetitorsListView,
  NewCompetitorView,
} from "@/components/pages/CompetitorViews";
import { apiGetClient, apiMutate } from "@/lib/api";
import { renderWithQuery } from "../query-test-utils";

vi.mock("@/lib/api", () => ({ apiGetClient: vi.fn(), apiMutate: vi.fn() }));
const searchParams = { current: new URLSearchParams() };
vi.mock("next/navigation", () => ({ useSearchParams: () => searchParams.current }));

const competitor = {
  id: "11111111-1111-4111-8111-111111111111",
  name: "Acme",
  primary_domain: "acme.example",
  description: "Widgets",
  status: "discovering",
  daily_run_time_local: "08:00:00",
  created_at: "2026-08-21T08:00:00Z",
  updated_at: "2026-08-21T08:00:00Z",
};
const source = {
  id: "22222222-2222-4222-8222-222222222222",
  url: "https://acme.example/pricing",
  source_category: "pricing",
  title: "Pricing",
  discovery_reason: "Official pricing page",
  approval_status: "approved",
  created_at: "2026-08-21T08:00:00Z",
  updated_at: "2026-08-21T08:00:00Z",
};
const me = {
  id: "33333333-3333-4333-8333-333333333333",
  email: "owner@example.com",
  display_name: "Owner",
  avatar_url: null,
  timezone: "Europe/Berlin",
  csrf_token: "csrf",
};
const settings = {
  display_name: "Owner",
  timezone: "Europe/Berlin",
  default_daily_time: "06:45:00",
};
const run = (status: string, failure_summary: string | null = null) => ({
  id: "44444444-4444-4444-8444-444444444444",
  competitor_id: competitor.id,
  run_type: "source_discovery",
  status,
  scheduled_for: "2026-08-21T08:00:00Z",
  started_at: status === "failed" ? null : "2026-08-21T08:00:01Z",
  completed_at: "2026-08-21T08:00:02Z",
  failure_code: status === "failed" ? "provider_error" : null,
  failure_summary,
  partial_reasons: [],
  input_tokens: 1,
  output_tokens: 2,
  tool_calls: 1,
  settled_cost_usd: "0.01",
  created_at: "2026-08-21T08:00:00Z",
});

afterEach(() => {
  vi.clearAllMocks();
  searchParams.current = new URLSearchParams();
});

describe("competitor pages", () => {
  it("renders loading, empty, success, and error list states", async () => {
    let resolve!: (value: unknown) => void;
    vi.mocked(apiGetClient).mockReturnValueOnce(new Promise((done) => (resolve = done)) as never);
    const first = renderWithQuery(<CompetitorsListView />);
    expect(screen.getByText("Loading competitors…")).toBeInTheDocument();
    resolve({ items: [], next_cursor: null });
    expect(await screen.findByText("No competitors yet.")).toBeInTheDocument();
    first.unmount();

    vi.mocked(apiGetClient).mockResolvedValueOnce({
      items: [competitor],
      next_cursor: null,
    } as never);
    const second = renderWithQuery(<CompetitorsListView />);
    expect(await screen.findByRole("link", { name: "Acme" })).toHaveAttribute(
      "href",
      `/competitors/${competitor.id}`,
    );
    second.unmount();

    vi.mocked(apiGetClient).mockRejectedValueOnce(new Error("network unavailable"));
    renderWithQuery(<CompetitorsListView />);
    expect(await screen.findByRole("alert")).toHaveTextContent("network unavailable");
  });

  it("does not mislabel non-capacity API errors as competitor limits", async () => {
    vi.mocked(apiGetClient).mockRejectedValueOnce(
      Object.assign(new Error("invalid cursor"), {
        detail: "invalid cursor",
        status: 422,
      }),
    );

    renderWithQuery(<CompetitorsListView />);

    expect(await screen.findByRole("alert")).toHaveTextContent("invalid cursor");
    expect(screen.getByRole("alert")).not.toHaveTextContent("Competitor limit reached");
  });

  it("frames the first run as a three-step setup and shows background progress", async () => {
    searchParams.current = new URLSearchParams("first=1");
    vi.mocked(apiGetClient).mockImplementation(async (path) => {
      if (path === "/api/v1/me") return me as never;
      if (path === "/api/v1/settings") return settings as never;
      if (path.includes("/runs/")) return run("running") as never;
      throw new Error(`unexpected GET ${path}`);
    });
    vi.mocked(apiMutate)
      .mockResolvedValueOnce(competitor as never)
      .mockResolvedValueOnce({ run_id: run("running").id } as never);

    renderWithQuery(<NewCompetitorView pollIntervalMs={50} />);

    expect(
      await screen.findByRole("heading", {
        name: "Let's set up your first competitor in 3 steps",
      }),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Competitor name"), { target: { value: "Acme" } });
    fireEvent.change(screen.getByLabelText("Primary domain"), {
      target: { value: "acme.example" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Continue to sources" }));

    const progress = await screen.findByTestId("working-indicator");
    expect(progress).toHaveTextContent("Finding first-party sources…");
    expect(progress).toHaveTextContent("This usually takes under a minute");
  });

  it("keeps the standard header when adding a later competitor", async () => {
    vi.mocked(apiGetClient).mockImplementation(async (path) => {
      if (path === "/api/v1/me") return me as never;
      if (path === "/api/v1/settings") return settings as never;
      throw new Error(`unexpected GET ${path}`);
    });

    renderWithQuery(<NewCompetitorView pollIntervalMs={50} />);

    expect(await screen.findByRole("heading", { name: "Add competitor" })).toBeInTheDocument();
  });

  it("guides setup from details through source selection and the first scan", async () => {
    const firstScan = {
      ...run("completed"),
      id: "55555555-5555-4555-8555-555555555555",
      run_type: "manual_scout",
    };
    vi.mocked(apiGetClient).mockImplementation(async (path) => {
      if (path === "/api/v1/me") return me as never;
      if (path === "/api/v1/settings") return settings as never;
      if (path === `/api/v1/runs/${firstScan.id}`) return firstScan as never;
      if (path.includes("/runs/")) return run("completed") as never;
      if (path.includes("/sources")) return { items: [source], next_cursor: null } as never;
      throw new Error(`unexpected GET ${path}`);
    });
    vi.mocked(apiMutate)
      .mockResolvedValueOnce(competitor as never)
      .mockResolvedValueOnce({ run_id: run("completed").id } as never)
      .mockResolvedValueOnce({
        competitor: { ...competitor, status: "active" },
        run: firstScan,
      } as never);

    renderWithQuery(<NewCompetitorView pollIntervalMs={1} />);
    expect(await screen.findByText("1. Details")).toBeInTheDocument();
    expect(screen.getByText("2. Sources")).toBeInTheDocument();
    expect(screen.getByText("3. First scan")).toBeInTheDocument();
    await screen.findByLabelText("Competitor name");
    expect(screen.getByLabelText("Daily run time")).toHaveValue("06:45");
    fireEvent.change(screen.getByLabelText("Competitor name"), { target: { value: "Acme" } });
    fireEvent.change(screen.getByLabelText("Primary domain"), {
      target: { value: "acme.example" },
    });
    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Widgets" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue to sources" }));

    expect(
      await screen.findByRole("heading", { name: "Choose trusted sources" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("Pricing")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Monitor Pricing" })).toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: "Start monitoring & run first scan" }));
    expect(apiMutate).toHaveBeenNthCalledWith(
      1,
      "/api/v1/competitors",
      expect.objectContaining({ csrfToken: "csrf", method: "POST" }),
      expect.anything(),
    );
    expect(apiMutate).toHaveBeenNthCalledWith(
      2,
      `/api/v1/competitors/${competitor.id}/discover-sources`,
      expect.objectContaining({ csrfToken: "csrf", method: "POST" }),
      expect.anything(),
    );
    await waitFor(() =>
      expect(apiMutate).toHaveBeenNthCalledWith(
        3,
        `/api/v1/competitors/${competitor.id}/start-monitoring`,
        expect.objectContaining({
          body: { source_ids: [source.id], run_initial_scan: true },
          csrfToken: "csrf",
          method: "POST",
        }),
        expect.anything(),
      ),
    );
    expect(await screen.findByText("First scan complete.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to dashboard" })).toHaveAttribute("href", "/");
  });

  it("allows a trusted first-party URL to be added when discovery misses it", async () => {
    const manualSource = { ...source, approval_status: "suggested" };
    let sources: { items: (typeof manualSource)[]; next_cursor: null } = {
      items: [],
      next_cursor: null,
    };
    vi.mocked(apiGetClient).mockImplementation(async (path) => {
      if (path === "/api/v1/me") return me as never;
      if (path === "/api/v1/settings") return settings as never;
      if (path.includes("/runs/")) return run("completed") as never;
      if (path.includes("/sources")) return sources as never;
      throw new Error(`unexpected GET ${path}`);
    });
    vi.mocked(apiMutate)
      .mockResolvedValueOnce(competitor as never)
      .mockResolvedValueOnce({ run_id: run("completed").id } as never)
      .mockImplementationOnce(async () => {
        sources = { items: [manualSource], next_cursor: null };
        return manualSource as never;
      });

    renderWithQuery(<NewCompetitorView pollIntervalMs={1} />);
    await screen.findByLabelText("Competitor name");
    fireEvent.change(screen.getByLabelText("Competitor name"), { target: { value: "Acme" } });
    fireEvent.change(screen.getByLabelText("Primary domain"), {
      target: { value: "acme.example" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Continue to sources" }));
    await screen.findByRole("heading", { name: "Choose trusted sources" });
    fireEvent.change(screen.getByLabelText("Add a first-party source"), {
      target: { value: source.url },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add source" }));

    await waitFor(() =>
      expect(apiMutate).toHaveBeenNthCalledWith(
        3,
        `/api/v1/competitors/${competitor.id}/sources`,
        expect.objectContaining({ body: { url: source.url }, method: "POST" }),
        expect.anything(),
      ),
    );
    expect(await screen.findByRole("checkbox", { name: "Monitor Pricing" })).toBeChecked();
  });

  it("keeps a created competitor recoverable when discovery cannot be started", async () => {
    vi.mocked(apiGetClient).mockImplementation(async (path) => {
      if (path === "/api/v1/me") return me as never;
      if (path === "/api/v1/settings") return settings as never;
      if (path.includes("/runs/")) return run("completed") as never;
      if (path.includes("/sources")) return { items: [source], next_cursor: null } as never;
      throw new Error(`unexpected GET ${path}`);
    });
    vi.mocked(apiMutate)
      .mockResolvedValueOnce(competitor as never)
      .mockRejectedValueOnce(new Error("discovery unavailable"))
      .mockResolvedValueOnce({ run_id: run("completed").id } as never);

    renderWithQuery(<NewCompetitorView pollIntervalMs={1} />);
    await screen.findByLabelText("Competitor name");
    fireEvent.change(screen.getByLabelText("Competitor name"), { target: { value: "Acme" } });
    fireEvent.change(screen.getByLabelText("Primary domain"), {
      target: { value: "acme.example" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Continue to sources" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("discovery unavailable");
    expect(screen.queryByLabelText("Competitor name")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry source discovery" }));
    expect(await screen.findByRole("checkbox", { name: "Monitor Pricing" })).toBeChecked();
    expect(apiMutate).toHaveBeenNthCalledWith(
      3,
      `/api/v1/competitors/${competitor.id}/discover-sources`,
      expect.objectContaining({ csrfToken: "csrf", method: "POST" }),
      expect.anything(),
    );
  });

  it("renders discovery failure without requesting sources", async () => {
    vi.mocked(apiGetClient).mockImplementation(async (path) => {
      if (path === "/api/v1/me") return me as never;
      if (path === "/api/v1/settings") return settings as never;
      if (path.includes("/runs/")) return run("failed", "Provider unavailable") as never;
      throw new Error(`unexpected GET ${path}`);
    });
    vi.mocked(apiMutate)
      .mockResolvedValueOnce(competitor as never)
      .mockResolvedValueOnce({ run_id: run("failed").id } as never);
    renderWithQuery(<NewCompetitorView pollIntervalMs={1} />);
    await screen.findByLabelText("Competitor name");
    fireEvent.change(screen.getByLabelText("Competitor name"), { target: { value: "Acme" } });
    fireEvent.change(screen.getByLabelText("Primary domain"), {
      target: { value: "acme.example" },
    });
    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Widgets" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue to sources" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Provider unavailable");
    expect(vi.mocked(apiGetClient).mock.calls.some(([path]) => path.includes("/sources"))).toBe(
      false,
    );
  });

  it("retries failed source discovery from the competitor detail page", async () => {
    let sourceRequests = 0;
    vi.mocked(apiGetClient).mockImplementation(async (path) => {
      if (path === "/api/v1/me") return me as never;
      if (path === `/api/v1/competitors/${competitor.id}`) return competitor as never;
      if (path === `/api/v1/competitors/${competitor.id}/sources`) {
        sourceRequests += 1;
        return {
          items: sourceRequests === 1 ? [] : [source],
          next_cursor: null,
        } as never;
      }
      if (path.startsWith("/api/v1/findings?")) return { items: [], next_cursor: null } as never;
      if (path.startsWith("/api/v1/runs?")) {
        return { items: [run("failed", "Source discovery failed.")], next_cursor: null } as never;
      }
      if (path === `/api/v1/runs/${run("completed").id}`) return run("completed") as never;
      throw new Error(`unexpected GET ${path}`);
    });
    vi.mocked(apiMutate).mockResolvedValueOnce({ run_id: run("completed").id } as never);

    renderWithQuery(<CompetitorDetailView competitorId={competitor.id} />);
    await screen.findByRole("heading", { name: "Acme" });
    expect(screen.getByRole("button", { name: "Run now" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Retry source discovery" }));

    await waitFor(() =>
      expect(apiMutate).toHaveBeenCalledWith(
        `/api/v1/competitors/${competitor.id}/discover-sources`,
        expect.objectContaining({ csrfToken: "csrf", method: "POST" }),
        expect.anything(),
      ),
    );
    expect(await screen.findByText("Source discovery completed.")).toBeInTheDocument();
    expect(await screen.findByText("Pricing")).toBeInTheDocument();
  });

  it("approves sources and activates monitoring with the authenticated CSRF token", async () => {
    const suggestedSource = { ...source, approval_status: "suggested" };
    vi.mocked(apiGetClient).mockImplementation(async (path) => {
      if (path === "/api/v1/me") return me as never;
      if (path.endsWith("/sources"))
        return { items: [suggestedSource], next_cursor: null } as never;
      if (path.startsWith("/api/v1/findings?")) return { items: [], next_cursor: null } as never;
      if (path.startsWith("/api/v1/runs?")) return { items: [], next_cursor: null } as never;
      return competitor as never;
    });
    vi.mocked(apiMutate)
      .mockResolvedValueOnce(source as never)
      .mockResolvedValueOnce({ ...competitor, status: "active" } as never);
    renderWithQuery(<CompetitorDetailView competitorId={competitor.id} />);
    await screen.findByRole("heading", { name: "Acme" });
    expect(screen.getByRole("heading", { name: "Recent updates" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Recent scans" })).toBeInTheDocument();
    expect(screen.getByRole("form", { name: "Filter competitor updates" })).toHaveAttribute(
      "action",
      "/findings",
    );
    expect(screen.getByRole("button", { name: "Activate monitoring" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Approve Pricing" }));
    await waitFor(() =>
      expect(apiMutate).toHaveBeenCalledWith(
        `/api/v1/competitors/${competitor.id}/sources/${source.id}`,
        expect.objectContaining({
          body: { approval_status: "approved" },
          csrfToken: "csrf",
          method: "PATCH",
        }),
        expect.anything(),
      ),
    );
    expect(screen.getByRole("button", { name: "Activate monitoring" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Activate monitoring" }));
    await waitFor(() =>
      expect(apiMutate).toHaveBeenCalledWith(
        `/api/v1/competitors/${competitor.id}`,
        expect.objectContaining({ body: { status: "active" }, csrfToken: "csrf", method: "PATCH" }),
        expect.anything(),
      ),
    );
  });
});
