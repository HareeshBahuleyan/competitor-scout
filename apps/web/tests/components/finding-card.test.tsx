import { render, screen } from "@testing-library/react";

import { FindingCard } from "@/components/FindingCard";
import type { Finding } from "@/lib/schemas";

const finding: Finding = {
  id: "55555555-5555-4555-8555-555555555555",
  competitor_id: "11111111-1111-4111-8111-111111111111",
  originating_scout_run_id: "44444444-4444-4444-8444-444444444444",
  category: "pricing",
  title: "Critical pricing change",
  summary: "A material pricing change was detected.",
  significance_explanation: "The change affects every plan.",
  significance_level: "critical",
  confidence: 0.97,
  decision_rationale: "Confirmed by first-party evidence.",
  first_seen_at: "2026-08-21T08:00:00Z",
  last_seen_at: "2026-08-21T09:00:00Z",
  published_at: "2026-08-21T09:00:00Z",
};

describe("FindingCard", () => {
  it("exposes one detail link and a visible affordance for the clickable card", () => {
    render(<FindingCard finding={finding} />);

    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAccessibleName(finding.title);
    expect(links[0]).toHaveAttribute("href", `/findings/${finding.id}`);
    expect(screen.getByText("View update")).toBeInTheDocument();
  });

  it("uses the danger indicator for critical findings", () => {
    render(<FindingCard finding={finding} />);

    const indicator = screen.getByRole("article").querySelector('[aria-hidden="true"]');
    expect(indicator).toHaveClass("bg-[var(--color-danger)]");
  });
});
