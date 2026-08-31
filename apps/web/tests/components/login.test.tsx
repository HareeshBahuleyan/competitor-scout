import { render, screen } from "@testing-library/react";

import LoginPage from "@/app/login/page";

describe("LoginPage", () => {
  it("links to the same-origin Google OAuth entry point", () => {
    render(<LoginPage />);

    expect(
      screen.getByRole("link", { name: /continue with google/i }),
    ).toHaveAttribute("href", "/auth/google/login");
  });

  it("explains that Google sign-up is capacity limited", () => {
    render(<LoginPage />);

    expect(screen.getByText(/google sign-up is limited to ten users/i)).toBeVisible();
  });
});
