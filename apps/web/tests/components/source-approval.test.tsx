import { fireEvent, render, screen } from "@testing-library/react";

import { SourceApprovalList } from "@/components/SourceApprovalList";
import type { Source } from "@/lib/schemas";

const pricingSource: Source = {
  id: "8b4f03f8-2db9-4f7d-8c5e-3351846b842c",
  url: "https://acme.example/pricing",
  source_category: "pricing",
  title: "Pricing",
  discovery_reason: "Tracks packaging and plan changes.",
  approval_status: "suggested",
  created_at: "2026-08-21T08:00:00Z",
  updated_at: "2026-08-21T08:00:00Z",
};

const changelogSource: Source = {
  ...pricingSource,
  id: "de26990b-c5d5-48ab-bce7-e4d63d7fa94f",
  url: "https://acme.example/changelog",
  source_category: "changelog",
  title: "Changelog",
};

describe("SourceApprovalList", () => {
  it("calls the explicit approval decision for the selected source", () => {
    const onUpdate = vi.fn();
    render(<SourceApprovalList onUpdate={onUpdate} sources={[pricingSource]} />);

    fireEvent.click(screen.getByRole("button", { name: "Approve Pricing" }));

    expect(onUpdate).toHaveBeenCalledWith(pricingSource.id, "approved");
  });

  it("calls the explicit rejection decision for the selected source", () => {
    const onUpdate = vi.fn();
    render(<SourceApprovalList onUpdate={onUpdate} sources={[pricingSource]} />);

    fireEvent.click(screen.getByRole("button", { name: "Reject Pricing" }));

    expect(onUpdate).toHaveBeenCalledWith(pricingSource.id, "rejected");
  });

  it("disables only the pending source actions and announces its state", () => {
    render(
      <SourceApprovalList
        onUpdate={vi.fn()}
        pendingSourceId={pricingSource.id}
        sources={[pricingSource, changelogSource]}
      />,
    );

    expect(screen.getByRole("button", { name: "Approve Pricing" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Reject Pricing" })).toBeDisabled();
    expect(screen.getByText("Updating Pricing…")).toHaveAttribute("aria-live", "polite");
    expect(screen.getByRole("button", { name: "Approve Changelog" })).toBeEnabled();
  });

  it("disables all decisions when source editing is unavailable", () => {
    render(<SourceApprovalList disabled onUpdate={vi.fn()} sources={[pricingSource]} />);

    expect(screen.getByRole("button", { name: "Approve Pricing" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Reject Pricing" })).toBeDisabled();
  });

  it("explains the approval required for activation", () => {
    const { rerender } = render(
      <SourceApprovalList onUpdate={vi.fn()} sources={[pricingSource]} />,
    );

    expect(
      screen.getByText("Approve at least one source to activate daily monitoring."),
    ).toBeVisible();

    rerender(
      <SourceApprovalList
        onUpdate={vi.fn()}
        sources={[{ ...pricingSource, approval_status: "approved" }]}
      />,
    );
    expect(screen.getByText("Daily monitoring is active.")).toBeVisible();
  });
});
