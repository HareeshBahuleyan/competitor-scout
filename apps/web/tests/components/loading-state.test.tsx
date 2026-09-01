import { render, screen } from "@testing-library/react";

import { LoadingState } from "@/components/ui/LoadingState";

describe("LoadingState", () => {
  it("announces the requested loading label", () => {
    render(<LoadingState label="Loading dashboard…" rows={3} />);

    expect(screen.getByRole("status")).toHaveTextContent("Loading dashboard…");
  });
});
