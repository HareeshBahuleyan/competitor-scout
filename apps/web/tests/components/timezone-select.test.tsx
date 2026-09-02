import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import {
  canonicalTimezone,
  commonTimezoneRegions,
  TimezoneSelect,
  timezoneRegions,
} from "@/components/ui/TimezoneSelect";

function validIanaTimezone(value: string) {
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: value }).format();
    return true;
  } catch {
    return false;
  }
}

describe("timezone mapping", () => {
  it("resolves deprecated aliases and a bare UTC to canonical zones", () => {
    expect(canonicalTimezone("Asia/Calcutta")).toBe("Asia/Kolkata");
    expect(canonicalTimezone("UTC")).toBe("Etc/UTC");
    expect(canonicalTimezone("Europe/Berlin")).toBe("Europe/Berlin");
  });

  it("keeps aliases that are selectable zones of their own", () => {
    expect(canonicalTimezone("America/Cayman")).toBe("America/Cayman");
  });

  it("returns null for zones the database does not know", () => {
    expect(canonicalTimezone("Mars/Olympus")).toBeNull();
    expect(canonicalTimezone("")).toBeNull();
  });

  it("groups every zone under a region and offers no duplicate values", () => {
    const regions = timezoneRegions();
    const values = regions.flatMap((region) => region.options.map((option) => option.value));
    expect(regions.map((region) => region.region)).toEqual(
      expect.arrayContaining(["Universal", "Africa", "Asia", "Europe", "North America"]),
    );
    expect(values.length).toBeGreaterThan(300);
    expect(new Set(values).size).toBe(values.length);
    expect(regions[0].region).toBe("Universal");
  });
});

describe("common timezone list", () => {
  const regions = commonTimezoneRegions();
  const values = regions.flatMap((region) => region.options.map((option) => option.value));

  it("stays short, ordered west to east, and free of duplicates", () => {
    expect(values.length).toBeLessThan(50);
    expect(new Set(values).size).toBe(values.length);
    expect(regions.map((region) => region.region)).toEqual([
      "Universal",
      "Americas",
      "Europe",
      "Africa & Middle East",
      "Asia",
      "Pacific",
    ]);
  });

  it("only names zones the timezone database still recognises", () => {
    for (const value of values) {
      expect(validIanaTimezone(value), value).toBe(true);
      expect(canonicalTimezone(value), value).toBe(value);
    }
  });

  it("labels each entry with its offset, city, and zone name", () => {
    const europe = regions.find((region) => region.region === "Europe");
    expect(europe?.options.map((option) => option.label)).toEqual(
      expect.arrayContaining([expect.stringContaining("Berlin — Central European Time")]),
    );
  });
});

describe("TimezoneSelect", () => {
  const trigger = () => screen.getByRole("button", { name: /Timezone/ });

  it("shows the canonical zone for an aliased value and reports the picked zone", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<TimezoneSelect label="Timezone" onChange={onChange} value="Asia/Calcutta" />);

    expect(trigger()).toHaveTextContent("Mumbai — India Time");

    await user.click(trigger());
    await user.click(screen.getByRole("option", { name: /Berlin — Central European Time/ }));
    expect(onChange).toHaveBeenCalledWith("Europe/Berlin");
  });

  it("keeps an unlisted stored zone visible instead of silently reassigning it", async () => {
    const user = userEvent.setup();
    render(<TimezoneSelect label="Timezone" onChange={vi.fn()} value="Mars/Olympus" />);

    expect(trigger()).toHaveTextContent("Mars/Olympus (not in the current timezone database)");

    await user.click(trigger());
    expect(
      screen.getByRole("option", { name: "Mars/Olympus (not in the current timezone database)" }),
    ).toBeInTheDocument();
  });

  it("keeps a stored zone outside the short list in its own group", async () => {
    const user = userEvent.setup();
    render(<TimezoneSelect label="Timezone" onChange={vi.fn()} value="Asia/Colombo" />);

    expect(trigger()).toHaveTextContent("Colombo");

    await user.click(trigger());
    expect(screen.getByRole("group", { name: "Current selection" })).toBeInTheDocument();
  });

  it("reveals the whole database on demand and collapses back", async () => {
    const user = userEvent.setup();
    render(<TimezoneSelect label="Timezone" onChange={vi.fn()} value="Europe/Berlin" />);

    await user.click(trigger());
    expect(screen.getAllByRole("option").length).toBeLessThan(50);
    await user.keyboard("{Escape}");

    await user.click(screen.getByRole("button", { name: "Show all timezones" }));
    await user.click(trigger());
    expect(screen.getAllByRole("option").length).toBeGreaterThan(300);
    await user.keyboard("{Escape}");

    await user.click(screen.getByRole("button", { name: "Show common timezones" }));
    await user.click(trigger());
    expect(screen.getAllByRole("option").length).toBeLessThan(50);
  });

  it("prompts for a choice when nothing is stored yet", () => {
    render(<TimezoneSelect label="Timezone" onChange={vi.fn()} value="" />);

    expect(trigger()).toHaveTextContent("Select a region");
  });
});
