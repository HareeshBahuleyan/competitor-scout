import { fireEvent, render, screen } from "@testing-library/react";

import { SourceManagementList } from "@/components/SourceManagementList";
import type { Source } from "@/lib/schemas";

const pricingSource: Source = {
  id: "8b4f03f8-2db9-4f7d-8c5e-3351846b842c",
  url: "https://acme.example/pricing",
  source_category: "pricing",
  title: "Pricing",
  discovery_reason: "Tracks packaging and plan changes.",
  approval_status: "approved",
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

describe("SourceManagementList", () => {
  it("removes an already monitored source from future scans", () => {
    const onUpdate = vi.fn();
    render(<SourceManagementList onUpdate={onUpdate} sources={[pricingSource]} />);

    expect(screen.queryByRole("button", { name: "Monitor Pricing" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Stop monitoring Pricing" }));

    expect(onUpdate).toHaveBeenCalledWith(pricingSource.id, "rejected");
  });

  it("restores a source that is not monitored", () => {
    const onUpdate = vi.fn();
    render(
      <SourceManagementList
        onUpdate={onUpdate}
        sources={[{ ...pricingSource, approval_status: "rejected" }]}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Monitor Pricing" }));

    expect(onUpdate).toHaveBeenCalledWith(pricingSource.id, "approved");
  });

  it("offers both decisions for a source awaiting review", () => {
    const onUpdate = vi.fn();
    render(
      <SourceManagementList
        onUpdate={onUpdate}
        sources={[{ ...pricingSource, approval_status: "suggested" }]}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Monitor Pricing" }));
    fireEvent.click(screen.getByRole("button", { name: "Dismiss Pricing" }));

    expect(onUpdate).toHaveBeenNthCalledWith(1, pricingSource.id, "approved");
    expect(onUpdate).toHaveBeenNthCalledWith(2, pricingSource.id, "rejected");
  });

  it("groups sources by whether scans use them", () => {
    render(
      <SourceManagementList
        onUpdate={vi.fn()}
        sources={[pricingSource, { ...changelogSource, approval_status: "rejected" }]}
      />,
    );

    expect(screen.getByRole("heading", { name: "Monitored sources" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Not monitored" })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Awaiting review" })).not.toBeInTheDocument();
    expect(
      screen.getByRole("list", { name: "Monitored sources" }).querySelectorAll("li"),
    ).toHaveLength(1);
  });

  it("labels each source status in text as well as color", () => {
    render(
      <SourceManagementList
        onUpdate={vi.fn()}
        sources={[pricingSource, { ...changelogSource, approval_status: "suggested" }]}
      />,
    );

    expect(screen.getByText("Monitored")).toBeVisible();
    expect(screen.getByText("Awaiting review", { selector: "span" })).toBeVisible();
  });

  it("disables only the pending source actions and announces its state", () => {
    render(
      <SourceManagementList
        onUpdate={vi.fn()}
        pendingSourceId={pricingSource.id}
        sources={[pricingSource, changelogSource]}
      />,
    );

    expect(screen.getByRole("button", { name: "Stop monitoring Pricing" })).toBeDisabled();
    expect(screen.getByText("Updating Pricing…")).toHaveAttribute("aria-live", "polite");
    expect(screen.getByRole("button", { name: "Stop monitoring Changelog" })).toBeEnabled();
  });

  it("disables all decisions when source editing is unavailable", () => {
    render(<SourceManagementList disabled onUpdate={vi.fn()} sources={[pricingSource]} />);

    expect(screen.getByRole("button", { name: "Stop monitoring Pricing" })).toBeDisabled();
  });

  it("explains that monitoring a source and activating monitoring are separate", () => {
    const { rerender } = render(
      <SourceManagementList
        onUpdate={vi.fn()}
        sources={[{ ...pricingSource, approval_status: "suggested" }]}
      />,
    );

    expect(
      screen.getByText("Monitor at least one trusted source before activating monitoring."),
    ).toBeVisible();

    rerender(<SourceManagementList onUpdate={vi.fn()} sources={[pricingSource]} />);
    expect(screen.getByText("Scans use 1 monitored source.")).toBeVisible();
  });
});
