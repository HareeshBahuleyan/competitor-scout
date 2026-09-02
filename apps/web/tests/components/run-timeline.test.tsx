import { render, screen, within } from "@testing-library/react";

import { RunTimeline } from "@/components/RunTimeline";

const outOfOrderSteps = [
  { state: "gathering" as const, occurred_at: "2026-08-21T08:02:00Z" },
  { state: "queued" as const, occurred_at: "2026-08-21T08:00:00Z" },
  { state: "planning" as const, occurred_at: "2026-08-21T08:01:00Z" },
];

describe("RunTimeline", () => {
  it("orders lifecycle events chronologically and exposes partial diagnostics", () => {
    render(
      <RunTimeline
        partial_reasons={["child_task_failed", "source_unavailable"]}
        retry_count={1}
        status="partial"
        steps={outOfOrderSteps}
        usage={{
          input_tokens: 120,
          output_tokens: 45,
          latency_ms: 1530,
          settled_cost_usd: "0.42",
        }}
      />,
    );

    const lifecycle = within(screen.getByRole("list", { name: "Run lifecycle" }));
    const steps = lifecycle.getAllByRole("listitem");
    expect(steps.map((step) => step.textContent)).toEqual([
      expect.stringContaining("Queued"),
      expect.stringContaining("Planning"),
      expect.stringContaining("Gathering"),
    ]);
    expect(screen.getByText("Partial")).toBeVisible();
    expect(screen.getByText("Usage details").closest("details")).toBeInTheDocument();
    expect(screen.getByText("Child task failed")).toBeVisible();
    expect(screen.getByText("Source unavailable")).toBeVisible();
    expect(screen.getByText("Retries")).toHaveTextContent("1");
    expect(screen.getByText("Input tokens")).toHaveTextContent("120");
    expect(screen.getByText("Output tokens")).toHaveTextContent("45");
    expect(screen.getByText("Latency")).toHaveTextContent("1,530 ms");
    expect(screen.getByText("Settled cost")).toHaveTextContent("$0.42");
  });

  it("prefers the backend summary over the raw partial reason code", () => {
    render(
      <RunTimeline
        partial_reasons={["child_task_failed"]}
        partial_summaries={["Some research tasks could not complete."]}
        retry_count={0}
        status="partial"
        steps={outOfOrderSteps}
      />,
    );

    expect(screen.getByText("Some research tasks could not complete.")).toBeVisible();
    expect(screen.queryByText("Child task failed")).not.toBeInTheDocument();
  });

  it("shows a failed reason and unknown usage without inventing totals", () => {
    render(
      <RunTimeline
        failure_reason="otari_authentication_error"
        retry_count={0}
        status="failed"
        steps={outOfOrderSteps.slice(0, 1)}
      />,
    );

    expect(screen.getByText("Failed")).toBeVisible();
    expect(screen.getByText("Otari authentication error")).toBeVisible();
    expect(screen.getByText("Input tokens")).toHaveTextContent("Unknown");
    expect(screen.getByText("Output tokens")).toHaveTextContent("Unknown");
    expect(screen.getByText("Latency")).toHaveTextContent("Unknown");
    expect(screen.getByText("Settled cost")).toHaveTextContent("Unknown");
  });

  it("ignores prompt, raw-response, and credential fields even when passed at runtime", () => {
    const unsafeProps = {
      status: "failed" as const,
      steps: [
        {
          state: "queued" as const,
          occurred_at: "2026-08-21T08:00:00Z",
          prompt: "PROMPT MUST NOT RENDER",
          raw_response: "RAW RESPONSE MUST NOT RENDER",
        },
      ],
      retry_count: 0,
      prompt: "TOP LEVEL PROMPT MUST NOT RENDER",
      raw_response: "TOP LEVEL RAW RESPONSE MUST NOT RENDER",
      credentials: "SECRET CREDENTIAL MUST NOT RENDER",
    };

    render(<RunTimeline {...unsafeProps} />);

    expect(screen.queryByText(/prompt must not render/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/raw response must not render/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/secret credential must not render/i)).not.toBeInTheDocument();
  });
});
