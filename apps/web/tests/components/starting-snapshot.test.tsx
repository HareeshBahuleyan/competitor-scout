import { render, screen } from "@testing-library/react";

import { StartingSnapshot } from "@/components/StartingSnapshot";

const snapshot = {
  id: "11111111-1111-4111-8111-111111111111",
  competitor_id: "22222222-2222-4222-8222-222222222222",
  competitor_name: "Acme",
  scout_run_id: "33333333-3333-4333-8333-333333333333",
  executive_summary: "Acme serves product teams with analytics software.",
  sections: [
    {
      topic: "positioning" as const,
      narrative: "Acme positions the product for product teams.",
      references: [
        {
          evidence_id: "44444444-4444-4444-8444-444444444444",
          statement: "The homepage identifies product teams.",
          source_title: "Acme homepage",
          source_url: "https://acme.example/",
          quoted_text: "Analytics for product teams.",
          captured_at: "2026-08-21T08:00:00Z",
        },
      ],
    },
  ],
  coverage: {
    approved_source_count: 1,
    inspected_source_count: 1,
    uninspected_source_count: 0,
    inspected_source_categories: ["homepage" as const],
    coverage_complete: true,
  },
  published_at: "2026-08-21T08:00:00Z",
  created_at: "2026-08-21T08:00:00Z",
};

describe("StartingSnapshot", () => {
  it("renders grounded sections, source coverage, and safe evidence links", () => {
    render(<StartingSnapshot snapshot={snapshot} timeZone="Europe/Berlin" />);

    expect(
      screen.getByRole("heading", { name: "What Scout established about Acme" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Positioning" })).toBeInTheDocument();
    expect(screen.getByText("Source coverage complete")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Acme homepage" })).toHaveAttribute(
      "rel",
      "noopener noreferrer",
    );
    expect(screen.getByRole("link", { name: "Acme homepage" })).toHaveAttribute(
      "href",
      "https://acme.example/",
    );
  });
});
