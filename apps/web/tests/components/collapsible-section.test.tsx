import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { CollapsibleSection } from "@/components/ui/CollapsibleSection";

describe("CollapsibleSection", () => {
  it("is closed by default and expands from its heading", async () => {
    const user = userEvent.setup();
    render(
      <CollapsibleSection id="sources" title="Sources">
        <p>Source controls</p>
      </CollapsibleSection>,
    );

    const disclosure = screen.getByRole("button", { name: "Sources" });
    expect(disclosure).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Source controls")).not.toBeInTheDocument();

    await user.click(disclosure);

    expect(disclosure).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Source controls")).toBeVisible();
  });

  it("honors defaultOpen", () => {
    render(
      <CollapsibleSection defaultOpen id="updates" title="Recent updates">
        <p>Update list</p>
      </CollapsibleSection>,
    );

    expect(screen.getByRole("button", { name: "Recent updates" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(screen.getByText("Update list")).toBeVisible();
  });
});
