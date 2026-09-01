import { render, screen } from "@testing-library/react";

import { AppShell } from "@/components/AppShell";

const expectedNavigation = [
  ["Dashboard", "/"],
  ["Competitors", "/competitors"],
  ["Findings", "/findings"],
  ["Runs", "/runs"],
  ["Briefs", "/briefs"],
  ["Settings", "/settings"],
] as const;

describe("AppShell", () => {
  it.each(expectedNavigation)("links %s to %s", (name, href) => {
    render(
      <AppShell>
        <p>Page content</p>
      </AppShell>,
    );

    expect(screen.getByRole("link", { name })).toHaveAttribute("href", href);
  });

  it("renders page content within the application shell", () => {
    render(
      <AppShell>
        <h1>Latest intelligence</h1>
      </AppShell>,
    );

    expect(screen.getByRole("heading", { name: "Latest intelligence" })).toBeVisible();
  });
});
