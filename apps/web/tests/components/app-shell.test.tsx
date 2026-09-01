import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { AppShell } from "@/components/AppShell";

const navigationMocks = vi.hoisted(() => ({ usePathname: vi.fn(() => "/findings/example") }));

vi.mock("next/navigation", () => navigationMocks);

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

  it("marks the current section and exposes the primary add action", () => {
    render(
      <AppShell>
        <p>Page content</p>
      </AppShell>,
    );

    expect(screen.getByRole("link", { name: "Findings" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Add competitor" })).toHaveAttribute(
      "href",
      "/competitors/new",
    );
  });
});
