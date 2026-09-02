import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, vi } from "vitest";

import { LogoutButton } from "@/components/LogoutButton";
import { renderWithQuery } from "../query-test-utils";

const apiMocks = vi.hoisted(() => ({
  apiGetClient: vi.fn(),
  apiMutate: vi.fn(),
}));
const navigationMocks = vi.hoisted(() => ({
  replace: vi.fn(),
  useRouter: vi.fn(),
}));

vi.mock("@/lib/api", () => apiMocks);
vi.mock("next/navigation", () => navigationMocks);

describe("LogoutButton", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    navigationMocks.useRouter.mockReturnValue({ replace: navigationMocks.replace });
    apiMocks.apiGetClient.mockResolvedValue({
      avatar_url: null,
      csrf_token: "csrf-token",
      display_name: "Founder",
      email: "founder@example.com",
      id: "11111111-1111-4111-8111-111111111111",
      timezone: "Europe/Berlin",
    });
    apiMocks.apiMutate.mockResolvedValue(undefined);
  });

  it("posts the authenticated CSRF token to the logout endpoint", async () => {
    renderWithQuery(<LogoutButton />);

    const button = await screen.findByRole("button", { name: "Log out" });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);

    await waitFor(() =>
      expect(apiMocks.apiMutate).toHaveBeenCalledWith("/auth/logout", {
        csrfToken: "csrf-token",
        method: "POST",
      }),
    );
    await waitFor(() => expect(navigationMocks.replace).toHaveBeenCalledWith("/login"));
  });

  it("does not derive its initial disabled state from the current-user query", () => {
    apiMocks.apiGetClient.mockReturnValue(new Promise(() => undefined));

    renderWithQuery(<LogoutButton />);

    expect(screen.getByRole("button", { name: "Log out" })).toBeEnabled();
  });

  it("keeps an accessible name in compact mode", async () => {
    renderWithQuery(<LogoutButton compact />);

    expect(await screen.findByRole("button", { name: "Log out" })).toBeVisible();
  });
});
