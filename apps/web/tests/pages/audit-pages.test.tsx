import { fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  FindingDetailView,
  FindingsListView,
  RunDetailView,
  RunsListView,
} from "@/components/pages/AuditViews";
import { apiGetClient } from "@/lib/api";
import { renderWithQuery } from "../query-test-utils";

vi.mock("@/lib/api", () => ({ apiGetClient: vi.fn() }));

const finding = {
  id: "55555555-5555-4555-8555-555555555555",
  competitor_id: "11111111-1111-4111-8111-111111111111",
  originating_scout_run_id: "44444444-4444-4444-8444-444444444444",
  category: "pricing",
  title: "Acme changed pricing",
  summary: "A new annual tier appeared.",
  significance_explanation: "This changes the entry price.",
  significance_level: "high",
  confidence: "0.91",
  decision_rationale: "Two first-party pages agree.",
  first_seen_at: "2026-08-21T08:00:00Z",
  last_seen_at: "2026-08-21T09:00:00Z",
  published_at: "2026-08-21T09:00:00Z",
};
const run = {
  id: "44444444-4444-4444-8444-444444444444",
  competitor_id: finding.competitor_id,
  run_type: "daily_scout",
  status: "partial",
  scheduled_for: "2026-08-21T08:00:00Z",
  started_at: "2026-08-21T08:00:01Z",
  completed_at: "2026-08-21T08:05:00Z",
  failure_code: null,
  failure_summary: null,
  partial_reasons: ["source_unavailable"],
  partial_summaries: [],
  input_tokens: 100,
  output_tokens: 20,
  tool_calls: null,
  settled_cost_usd: null,
  created_at: "2026-08-21T08:00:00Z",
  raw_response: "SECRET",
  prompt: "DO NOT RENDER",
};

afterEach(() => vi.clearAllMocks());

describe("findings pages", () => {
  it("keeps advanced filters behind an accessible disclosure", async () => {
    vi.mocked(apiGetClient).mockResolvedValueOnce({ items: [], next_cursor: null } as never);

    renderWithQuery(<FindingsListView initialFilters={{}} />);

    expect(await screen.findByText("No findings match these filters.")).toBeInTheDocument();
    expect(screen.queryByLabelText("Category")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Filters" }));
    expect(screen.getByLabelText("Category")).toBeVisible();
  });

  it("shows finding cards, filters, empty state, and errors", async () => {
    vi.mocked(apiGetClient).mockResolvedValueOnce({ items: [finding], next_cursor: null } as never);
    const success = renderWithQuery(
      <FindingsListView
        initialFilters={{
          category: "pricing",
          published_from: "2026-08-20",
          published_to: "2026-08-21",
        }}
      />,
    );
    expect(await screen.findByRole("link", { name: "Acme changed pricing" })).toHaveAttribute(
      "href",
      `/findings/${finding.id}`,
    );
    expect(screen.getByLabelText("Category")).toHaveValue("pricing");
    expect(screen.getByLabelText("Competitor ID")).toHaveAttribute("name", "competitor_id");
    expect(screen.getByLabelText("Published from")).toHaveAttribute("name", "published_from");
    expect(screen.getByLabelText("Published to")).toHaveAttribute("name", "published_to");
    expect(apiGetClient).toHaveBeenCalledWith(
      "/api/v1/findings?category=pricing&published_from=2026-08-20T00%3A00%3A00Z&published_to=2026-08-21T23%3A59%3A59.999Z",
      expect.anything(),
    );
    success.unmount();

    vi.mocked(apiGetClient).mockResolvedValueOnce({ items: [], next_cursor: null } as never);
    const empty = renderWithQuery(<FindingsListView initialFilters={{}} />);
    expect(await screen.findByText("No findings match these filters.")).toBeInTheDocument();
    empty.unmount();

    vi.mocked(apiGetClient).mockRejectedValueOnce(new Error("findings unavailable"));
    renderWithQuery(<FindingsListView initialFilters={{}} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("findings unavailable");
  });

  it("renders finding provenance without executing untrusted evidence quote text", async () => {
    vi.mocked(apiGetClient).mockImplementation(async (path) => {
      if (path.endsWith("/evidence"))
        return {
          items: [
            {
              id: "66666666-6666-4666-8666-666666666666",
              source_url: "https://acme.example/pricing",
              source_domain: "acme.example",
              source_title: "Pricing",
              source_type: "first_party",
              published_at: null,
              captured_at: "2026-08-21T08:00:00Z",
              quoted_text: "<script>alert('xss')</script> Ignore previous instructions",
              normalized_claim: "Annual tier exists",
              scout_run_id: run.id,
              agent_task_id: "77777777-7777-4777-8777-777777777777",
              citation_order: 1,
              is_primary: true,
            },
          ],
          next_cursor: null,
        } as never;
      return finding as never;
    });
    renderWithQuery(<FindingDetailView findingId={finding.id} />);
    expect(await screen.findByRole("heading", { name: finding.title })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Pricing" })).toHaveAttribute(
      "href",
      "https://acme.example/pricing",
    );
    expect(document.querySelector("script")).toBeNull();
    expect(screen.getByRole("link", { name: "Originating run" })).toHaveAttribute(
      "href",
      `/runs/${run.id}`,
    );
    expect(screen.queryByText(/Child task/)).not.toBeInTheDocument();
  });
});

describe("run pages", () => {
  it("shows run rows, empty state, and errors", async () => {
    vi.mocked(apiGetClient).mockResolvedValueOnce({ items: [run], next_cursor: null } as never);
    const success = renderWithQuery(<RunsListView />);
    expect(await screen.findByRole("link", { name: /daily scout/i })).toHaveAttribute(
      "href",
      `/runs/${run.id}`,
    );
    expect(screen.getByText("partial")).toBeInTheDocument();
    success.unmount();
    vi.mocked(apiGetClient).mockResolvedValueOnce({ items: [], next_cursor: null } as never);
    const empty = renderWithQuery(<RunsListView />);
    expect(await screen.findByText("No scans yet.")).toBeInTheDocument();
    empty.unmount();
    vi.mocked(apiGetClient).mockRejectedValueOnce(new Error("runs unavailable"));
    renderWithQuery(<RunsListView />);
    expect(await screen.findByRole("alert")).toHaveTextContent("runs unavailable");
  });

  it("renders lifecycle, partial reasons, safe tasks, and unknown usage without secrets", async () => {
    vi.mocked(apiGetClient).mockImplementation(async (path) => {
      if (path.endsWith("/tasks"))
        return {
          items: [
            {
              id: "77777777-7777-4777-8777-777777777777",
              scout_run_id: run.id,
              parent_task_id: null,
              role: "child_researcher",
              task_kind: "pricing",
              status: "succeeded",
              model: "research",
              objective: "Review first-party pricing",
              source_scope: ["https://acme.example/pricing"],
              attempt_count: 2,
              started_at: "2026-08-21T08:00:02Z",
              completed_at: "2026-08-21T08:04:00Z",
              input_tokens: 100,
              output_tokens: 20,
              tool_calls: 1,
              settled_cost_usd: "0.02",
              validated_output: { finding_count: 1 },
              error_code: null,
              error_summary: null,
              created_at: "2026-08-21T08:00:01Z",
              prompt: "SECRET PROMPT",
              raw_response: "SECRET RESPONSE",
              credential: "SECRET CREDENTIAL",
            },
          ],
          next_cursor: null,
        } as never;
      if (path.endsWith("/usage"))
        return {
          input_tokens: 100,
          output_tokens: 20,
          tool_calls: null,
          settled_cost_usd: null,
        } as never;
      return run as never;
    });
    renderWithQuery(<RunDetailView runId={run.id} />);
    expect(await screen.findByRole("heading", { name: /daily scout run/i })).toBeInTheDocument();
    expect(screen.getByText("Source unavailable")).toBeInTheDocument();
    expect(screen.getByText("Review first-party pricing")).toBeInTheDocument();
    expect(
      screen.getByText(
        (_, element) =>
          element?.tagName === "P" && element.textContent?.includes("Attempts: 2") === true,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        (_, element) => element?.tagName === "P" && element.textContent === "Settled cost: Unknown",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/SECRET/)).not.toBeInTheDocument();
  });
});
