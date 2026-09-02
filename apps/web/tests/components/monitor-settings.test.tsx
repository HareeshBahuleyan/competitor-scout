import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { MonitorSettings } from "@/components/MonitorSettings";
import type { Competitor } from "@/lib/schemas";

const competitor: Competitor = {
  id: "11111111-1111-4111-8111-111111111111",
  name: "Acme",
  primary_domain: "acme.example",
  description: "Widgets",
  status: "paused",
  daily_run_time_local: "08:00:00",
  created_at: "2026-08-21T08:00:00Z",
  updated_at: "2026-08-21T08:00:00Z",
};

describe("MonitorSettings", () => {
  it("edits monitor details and resumes monitoring", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(undefined);
    const onStatusChange = vi.fn().mockResolvedValue(undefined);

    render(
      <MonitorSettings
        competitor={competitor}
        hasApprovedSource
        onArchive={vi.fn()}
        onSave={onSave}
        onStatusChange={onStatusChange}
      />,
    );

    await user.clear(screen.getByLabelText("Monitor name"));
    await user.type(screen.getByLabelText("Monitor name"), "Acme Inc.");
    await user.clear(screen.getByLabelText("Description"));
    await user.type(screen.getByLabelText("Description"), "Updated widgets");
    await user.clear(screen.getByLabelText("Daily scan time"));
    await user.type(screen.getByLabelText("Daily scan time"), "09:30");
    await user.click(screen.getByRole("button", { name: "Save monitor" }));
    await user.click(screen.getByRole("button", { name: "Resume monitoring" }));

    expect(onSave).toHaveBeenCalledWith({
      daily_run_time_local: "09:30:00",
      description: "Updated widgets",
      name: "Acme Inc.",
    });
    expect(onStatusChange).toHaveBeenCalledWith("active");
  });

  it("explains archive retention and requires confirmation", async () => {
    const user = userEvent.setup();
    const onArchive = vi.fn().mockResolvedValue(undefined);

    render(
      <MonitorSettings
        competitor={competitor}
        hasApprovedSource
        onArchive={onArchive}
        onSave={vi.fn()}
        onStatusChange={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Archive monitor" }));
    expect(screen.getByRole("alertdialog")).toHaveTextContent(
      "Existing updates and scan history will be retained",
    );
    expect(onArchive).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Archive Acme" }));

    expect(onArchive).toHaveBeenCalledOnce();
  });
});
