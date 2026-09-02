import { render, screen, within } from "@testing-library/react";

import { EvidenceList, type EvidenceItem } from "@/components/EvidenceList";

const pricingEvidence: EvidenceItem = {
  id: "0f31ba1a-9eab-405e-8c53-19954734be1e",
  citation_order: 1,
  source_title: "Pricing page",
  source_url: "https://acme.example/pricing",
  quoted_text: "The Pro plan now costs $99 per month.",
  published_at: "2026-08-20T14:30:00Z",
  captured_at: "2026-08-21T08:00:00Z",
};

describe("EvidenceList", () => {
  it("renders each citation as a hyperlinked source title, ordered by citation order", () => {
    const secondEvidence: EvidenceItem = {
      ...pricingEvidence,
      id: "267c7cba-c905-481d-a066-2721e03946b8",
      citation_order: 2,
      source_title: "Changelog",
      source_url: "https://acme.example/changelog",
      published_at: null,
    };
    render(<EvidenceList evidence={[secondEvidence, pricingEvidence]} />);

    const citations = within(screen.getByRole("list", { name: "Finding citations" })).getAllByRole(
      "listitem",
    );
    expect(citations).toHaveLength(2);
    expect(within(citations[0]).getByRole("link", { name: /Pricing page/ })).toHaveAttribute(
      "href",
      "https://acme.example/pricing",
    );
    expect(within(citations[1]).getByRole("link", { name: /Changelog/ })).toHaveAttribute(
      "href",
      "https://acme.example/changelog",
    );
  });

  it("opens citation links safely in a new tab", () => {
    render(<EvidenceList evidence={[pricingEvidence]} />);

    const pricingLink = screen.getByRole("link", { name: /Pricing page/ });
    expect(pricingLink).toHaveAttribute("target", "_blank");
    expect(pricingLink).toHaveAttribute("rel", expect.stringContaining("noopener"));
    expect(pricingLink).toHaveAttribute("rel", expect.stringContaining("noreferrer"));
  });

  it("renders the same cited link only once", () => {
    render(
      <EvidenceList
        evidence={[
          {
            ...pricingEvidence,
            id: "267c7cba-c905-481d-a066-2721e03946b8",
            citation_order: 2,
            source_title: "Pricing page duplicate",
            quoted_text: "A second excerpt from the same page.",
          },
          pricingEvidence,
        ]}
      />,
    );

    expect(screen.getAllByRole("link", { name: /Pricing page/ })).toHaveLength(1);
    expect(screen.getByRole("link", { name: /Pricing page/ })).toHaveTextContent("Pricing page");
    expect(screen.queryByText("Pricing page duplicate")).not.toBeInTheDocument();
  });

  it("does not make a non-HTTPS source URL clickable", () => {
    render(
      <EvidenceList
        evidence={[
          {
            ...pricingEvidence,
            source_title: "Unsafe source",
            source_url: "javascript:alert('owned')",
          },
        ]}
      />,
    );

    expect(screen.queryByRole("link", { name: "Unsafe source" })).not.toBeInTheDocument();
    expect(screen.getByText("Unsafe source")).toBeVisible();
  });

  it("does not surface the child task number, even when provenance is available", () => {
    render(
      <EvidenceList
        evidence={[
          {
            ...pricingEvidence,
            agent_task_id: "77777777-7777-4777-8777-777777777777",
            scout_run_id: "33333333-3333-4333-8333-333333333333",
          },
        ]}
      />,
    );

    expect(screen.queryByText(/Child task/)).not.toBeInTheDocument();
  });
});
