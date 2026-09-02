import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { AppShell } from "@/components/AppShell";

const navigationMocks = vi.hoisted(() => ({ usePathname: vi.fn(() => "/findings/example") }));

vi.mock("next/navigation", () => navigationMocks);
vi.mock("@/components/LogoutButton", () => ({
  LogoutButton: () => <button type="button">Log out</button>,
}));

const expectedNavigation = [
  ["Dashboard", "/"],
  ["Competitors", "/competitors"],
  ["Updates", "/findings"],
  ["Weekly digest", "/briefs"],
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

    expect(screen.getByRole("link", { name: "Updates" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Add competitor" })).toHaveAttribute(
      "href",
      "/competitors/new",
    );
    expect(screen.getAllByRole("button", { name: "Log out" })).toHaveLength(2);
    expect(screen.getByText("Competitor Scout")).not.toHaveClass("truncate");
  });
});
