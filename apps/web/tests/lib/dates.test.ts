import { formatUserDateTime, localDateBoundaryUtc } from "@/lib/dates";

describe("user timezone date helpers", () => {
  it("formats instants in the requested timezone", () => {
    expect(formatUserDateTime("2026-09-01T06:00:00Z", "Europe/Berlin")).toContain("8:00");
  });

  it("converts local date boundaries across a DST transition", () => {
    expect(localDateBoundaryUtc("2026-03-29", "Europe/Berlin", "start")).toBe(
      "2026-03-28T23:00:00.000Z",
    );
    expect(localDateBoundaryUtc("2026-03-29", "Europe/Berlin", "end")).toBe(
      "2026-03-29T21:59:59.999Z",
    );
  });
});
