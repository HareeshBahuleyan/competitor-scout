import { fireEvent, render, screen } from "@testing-library/react";

import { CompetitorFavicon } from "@/components/CompetitorFavicon";

describe("CompetitorFavicon", () => {
  it("renders Google Favicon API image when domain is valid", () => {
    render(<CompetitorFavicon domain="stripe.com" name="Stripe" size="md" />);

    const img = screen.getByTestId("competitor-favicon-image");
    expect(img).toBeInTheDocument();
    expect(img).toHaveAttribute(
      "src",
      "https://www.google.com/s2/favicons?domain=stripe.com&sz=64",
    );
  });

  it("falls back to initial badge when domain is missing", () => {
    render(<CompetitorFavicon domain={null} name="Linear" size="sm" />);

    const fallback = screen.getByTestId("competitor-favicon-fallback");
    expect(fallback).toBeInTheDocument();
    expect(fallback).toHaveTextContent("L");
    expect(screen.queryByTestId("competitor-favicon-image")).not.toBeInTheDocument();
  });

  it("switches to initial badge on image load error", () => {
    render(<CompetitorFavicon domain="invalid-domain.local" name="Acme Corp" size="lg" />);

    const img = screen.getByTestId("competitor-favicon-image");
    fireEvent.error(img);

    const fallback = screen.getByTestId("competitor-favicon-fallback");
    expect(fallback).toBeInTheDocument();
    expect(fallback).toHaveTextContent("A");
    expect(screen.queryByTestId("competitor-favicon-image")).not.toBeInTheDocument();
  });
});
