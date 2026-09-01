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

afterEach(() => vi.clearAllMocks());

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

  it("creates a competitor, starts discovery, polls, and shows discovered sources", async () => {
    vi.mocked(apiGetClient).mockImplementation(async (path) => {
      if (path === "/api/v1/me") return me as never;
      if (path.includes("/runs/")) return run("completed") as never;
      if (path.includes("/sources")) return { items: [source], next_cursor: null } as never;
      throw new Error(`unexpected GET ${path}`);
    });
    vi.mocked(apiMutate)
      .mockResolvedValueOnce(competitor as never)
      .mockResolvedValueOnce({ run_id: run("completed").id } as never);

    renderWithQuery(<NewCompetitorView pollIntervalMs={1} />);
    await screen.findByLabelText("Competitor name");
    fireEvent.change(screen.getByLabelText("Competitor name"), { target: { value: "Acme" } });
    fireEvent.change(screen.getByLabelText("Primary domain"), {
      target: { value: "acme.example" },
    });
    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Widgets" } });
    fireEvent.click(screen.getByRole("button", { name: "Save competitor" }));

    expect(await screen.findByText("Discovery completed.")).toBeInTheDocument();
    expect(await screen.findByText("Pricing")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Activate daily monitoring" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Activate daily monitoring" }));
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
        `/api/v1/competitors/${competitor.id}`,
        expect.objectContaining({ body: { status: "active" }, csrfToken: "csrf", method: "PATCH" }),
        expect.anything(),
      ),
    );
  });

  it("keeps a created competitor recoverable when discovery cannot be started", async () => {
    vi.mocked(apiGetClient).mockImplementation(async (path) => {
      if (path === "/api/v1/me") return me as never;
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
    fireEvent.click(screen.getByRole("button", { name: "Save competitor" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("discovery unavailable");
    expect(screen.queryByLabelText("Competitor name")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry source discovery" }));
    expect(await screen.findByText("Discovery completed.")).toBeInTheDocument();
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
    fireEvent.click(screen.getByRole("button", { name: "Save competitor" }));
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
    expect(screen.getByRole("heading", { name: "Recent findings" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Recent runs" })).toBeInTheDocument();
    expect(screen.getByRole("form", { name: "Filter competitor findings" })).toHaveAttribute(
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
