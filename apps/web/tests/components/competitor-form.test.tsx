import { fireEvent, render, screen } from "@testing-library/react";

import { CompetitorForm } from "@/components/CompetitorForm";

describe("CompetitorForm", () => {
  it("shows accessible validation errors and does not submit invalid values", () => {
    const onSubmit = vi.fn();
    render(<CompetitorForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText("Competitor name"), {
      target: { value: "   " },
    });
    fireEvent.change(screen.getByLabelText("Primary domain"), {
      target: { value: "not a domain" },
    });
    fireEvent.submit(screen.getByRole("form", { name: "Competitor details" }));

    expect(screen.getByText("Competitor name is required.")).toBeVisible();
    expect(screen.getByText("Enter a valid domain or website URL.")).toBeVisible();
    expect(screen.getByLabelText("Competitor name")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Primary domain")).toHaveAttribute("aria-invalid", "true");
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("submits trimmed values and normalizes the local time to include seconds", () => {
    const onSubmit = vi.fn();
    render(<CompetitorForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText("Competitor name"), {
      target: { value: "  Acme Analytics  " },
    });
    fireEvent.change(screen.getByLabelText("Primary domain"), {
      target: { value: "  acme.example  " },
    });
    fireEvent.change(screen.getByLabelText("Description"), {
      target: { value: "  Product analytics platform.  " },
    });
    fireEvent.change(screen.getByLabelText("Daily run time"), {
      target: { value: "09:30" },
    });
    fireEvent.submit(screen.getByRole("form", { name: "Competitor details" }));

    expect(onSubmit).toHaveBeenCalledOnce();
    expect(onSubmit).toHaveBeenCalledWith({
      name: "Acme Analytics",
      primary_domain: "acme.example",
      description: "Product analytics platform.",
      daily_run_time_local: "09:30:00",
    });
  });

  it("accepts a website URL and submits its normalized hostname", () => {
    const onSubmit = vi.fn();
    render(<CompetitorForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText("Competitor name"), {
      target: { value: "Portkey AI" },
    });
    fireEvent.change(screen.getByLabelText("Primary domain"), {
      target: { value: "https://portkey.ai" },
    });
    fireEvent.submit(screen.getByRole("form", { name: "Competitor details" }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ primary_domain: "portkey.ai" }),
    );
  });

  it("disables every control and exposes pending text while submitting", () => {
    render(<CompetitorForm isSubmitting onSubmit={vi.fn()} />);

    expect(screen.getByLabelText("Competitor name")).toBeDisabled();
    expect(screen.getByLabelText("Primary domain")).toBeDisabled();
    expect(screen.getByLabelText("Description")).toBeDisabled();
    expect(screen.getByLabelText("Daily run time")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Saving competitor…" })).toBeDisabled();
  });
});
