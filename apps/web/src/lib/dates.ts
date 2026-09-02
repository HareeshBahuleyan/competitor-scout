type DateBoundary = "end" | "start";

const datePattern = /^(\d{4})-(\d{2})-(\d{2})$/;

export function formatUserDateTime(value: string, timeZone: string): string {
  return new Intl.DateTimeFormat("en-US", {
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    month: "short",
    timeZone,
    timeZoneName: "short",
    year: "numeric",
  }).format(new Date(value));
}

function localParts(timestamp: number, timeZone: string) {
  const values = Object.fromEntries(
    new Intl.DateTimeFormat("en-US", {
      day: "2-digit",
      hour: "2-digit",
      hourCycle: "h23",
      minute: "2-digit",
      month: "2-digit",
      second: "2-digit",
      timeZone,
      year: "numeric",
    })
      .formatToParts(new Date(timestamp))
      .filter((part) => part.type !== "literal")
      .map((part) => [part.type, Number(part.value)]),
  );
  return values as Record<"day" | "hour" | "minute" | "month" | "second" | "year", number>;
}

function localMidnightUtc(year: number, month: number, day: number, timeZone: string): number {
  const target = Date.UTC(year, month - 1, day);
  let candidate = target;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const parts = localParts(candidate, timeZone);
    const represented = Date.UTC(
      parts.year,
      parts.month - 1,
      parts.day,
      parts.hour,
      parts.minute,
      parts.second,
    );
    candidate += target - represented;
  }
  return candidate;
}

export function localDateBoundaryUtc(
  localDate: string,
  timeZone: string,
  boundary: DateBoundary,
): string {
  const match = datePattern.exec(localDate);
  if (!match) throw new TypeError("local date must use YYYY-MM-DD");
  const [, yearValue, monthValue, dayValue] = match;
  const year = Number(yearValue);
  const month = Number(monthValue);
  const day = Number(dayValue);
  const normalized = new Date(Date.UTC(year, month - 1, day));
  if (
    normalized.getUTCFullYear() !== year ||
    normalized.getUTCMonth() !== month - 1 ||
    normalized.getUTCDate() !== day
  ) {
    throw new TypeError("local date is invalid");
  }
  if (boundary === "start") {
    return new Date(localMidnightUtc(year, month, day, timeZone)).toISOString();
  }
  normalized.setUTCDate(normalized.getUTCDate() + 1);
  return new Date(
    localMidnightUtc(
      normalized.getUTCFullYear(),
      normalized.getUTCMonth() + 1,
      normalized.getUTCDate(),
      timeZone,
    ) - 1,
  ).toISOString();
}
