import { render, screen, act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { WorkingIndicator } from "@/components/ui/WorkingIndicator";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("WorkingIndicator", () => {
  it("announces a stable label while cycling playful messages and elapsed time", () => {
    render(
      <WorkingIndicator
        hint="This usually takes under a minute"
        label="Finding first-party sources…"
        messages={["Reading the changelog…", "Skipping the marketing fluff…"]}
        rotateEverySeconds={2}
      />,
    );

    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("Finding first-party sources…");
    expect(screen.getByText("Reading the changelog…")).toBeInTheDocument();
    expect(status).toHaveTextContent("This usually takes under a minute · 0s elapsed");

    act(() => vi.advanceTimersByTime(2_000));
    expect(screen.getByText("Skipping the marketing fluff…")).toBeInTheDocument();
    expect(status).toHaveTextContent("2s elapsed");

    act(() => vi.advanceTimersByTime(2_000));
    expect(screen.getByText("Reading the changelog…")).toBeInTheDocument();
  });
});
