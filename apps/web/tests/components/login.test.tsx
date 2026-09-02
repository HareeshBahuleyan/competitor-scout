import { render, screen } from "@testing-library/react";

import LoginPage from "@/app/login/page";

describe("LoginPage", () => {
  it("links to the same-origin Google OAuth entry point", () => {
    render(<LoginPage />);

    expect(
      screen.getByText(/calm, evidence-backed market intelligence for your team/i),
    ).toBeVisible();
    expect(screen.getByRole("link", { name: /continue with google/i })).toHaveAttribute(
      "href",
      "/auth/google/login",
    );
  });
});
