"use client";

import { Header, Label, ListBox, ListBoxItem, ListBoxSection, Select } from "@heroui/react";
import { getTimeZones } from "@vvo/tzdb";
import { type ReactNode, useMemo, useState } from "react";

type TimezoneOption = { label: string; value: string };
type TimezoneRegion = { options: TimezoneOption[]; region: string };

// `@vvo/tzdb` leaves `continentName` empty for the UTC/Etc zones.
const UNIVERSAL_REGION = "Universal";

/**
 * The everyday list: one entry per business region rather than all 300+ IANA
 * zones. `city` is stated here because `mainCities[0]` is not always the city a
 * user looks for (`Asia/Karachi` leads with Lahore). Every zone is asserted
 * against the database in the unit tests, and "Show all timezones" still reaches
 * the complete list.
 */
const COMMON_ZONES: ReadonlyArray<{ city: string; region: string; zone: string }> = [
  { city: "UTC", region: UNIVERSAL_REGION, zone: "Etc/UTC" },
  { city: "Honolulu", region: "Americas", zone: "Pacific/Honolulu" },
  { city: "Anchorage", region: "Americas", zone: "America/Anchorage" },
  { city: "Los Angeles", region: "Americas", zone: "America/Los_Angeles" },
  { city: "Denver", region: "Americas", zone: "America/Denver" },
  { city: "Chicago", region: "Americas", zone: "America/Chicago" },
  { city: "New York", region: "Americas", zone: "America/New_York" },
  { city: "Mexico City", region: "Americas", zone: "America/Mexico_City" },
  { city: "Bogotá", region: "Americas", zone: "America/Bogota" },
  { city: "São Paulo", region: "Americas", zone: "America/Sao_Paulo" },
  { city: "Buenos Aires", region: "Americas", zone: "America/Argentina/Buenos_Aires" },
  { city: "London", region: "Europe", zone: "Europe/London" },
  { city: "Lisbon", region: "Europe", zone: "Europe/Lisbon" },
  { city: "Madrid", region: "Europe", zone: "Europe/Madrid" },
  { city: "Paris", region: "Europe", zone: "Europe/Paris" },
  { city: "Berlin", region: "Europe", zone: "Europe/Berlin" },
  { city: "Rome", region: "Europe", zone: "Europe/Rome" },
  { city: "Athens", region: "Europe", zone: "Europe/Athens" },
  { city: "Istanbul", region: "Europe", zone: "Europe/Istanbul" },
  { city: "Moscow", region: "Europe", zone: "Europe/Moscow" },
  { city: "Lagos", region: "Africa & Middle East", zone: "Africa/Lagos" },
  { city: "Cairo", region: "Africa & Middle East", zone: "Africa/Cairo" },
  { city: "Nairobi", region: "Africa & Middle East", zone: "Africa/Nairobi" },
  { city: "Johannesburg", region: "Africa & Middle East", zone: "Africa/Johannesburg" },
  { city: "Jerusalem", region: "Africa & Middle East", zone: "Asia/Jerusalem" },
  { city: "Dubai", region: "Africa & Middle East", zone: "Asia/Dubai" },
  { city: "Karachi", region: "Asia", zone: "Asia/Karachi" },
  { city: "Mumbai", region: "Asia", zone: "Asia/Kolkata" },
  { city: "Dhaka", region: "Asia", zone: "Asia/Dhaka" },
  { city: "Bangkok", region: "Asia", zone: "Asia/Bangkok" },
  { city: "Jakarta", region: "Asia", zone: "Asia/Jakarta" },
  { city: "Singapore", region: "Asia", zone: "Asia/Singapore" },
  { city: "Hong Kong", region: "Asia", zone: "Asia/Hong_Kong" },
  { city: "Shanghai", region: "Asia", zone: "Asia/Shanghai" },
  { city: "Seoul", region: "Asia", zone: "Asia/Seoul" },
  { city: "Tokyo", region: "Asia", zone: "Asia/Tokyo" },
  { city: "Perth", region: "Pacific", zone: "Australia/Perth" },
  { city: "Sydney", region: "Pacific", zone: "Australia/Sydney" },
  { city: "Auckland", region: "Pacific", zone: "Pacific/Auckland" },
];

const COMMON_REGION_ORDER = [
  UNIVERSAL_REGION,
  "Americas",
  "Europe",
  "Africa & Middle East",
  "Asia",
  "Pacific",
];

// `getTimeZones` recomputes current offsets for 300+ zones on every call, so the
// derived lookups are built once per page load.
let zoneCache: ReturnType<typeof getTimeZones> | null = null;

function zones() {
  zoneCache ??= getTimeZones({ includeUtc: true });
  return zoneCache;
}

function zoneByName(name: string) {
  return zones().find((zone) => zone.name === name);
}

function offsetLabel(minutes: number) {
  const sign = minutes < 0 ? "-" : "+";
  const absolute = Math.abs(minutes);
  const hours = String(Math.floor(absolute / 60)).padStart(2, "0");
  const rest = String(absolute % 60).padStart(2, "0");
  return `GMT${sign}${hours}:${rest}`;
}

function fullLabel(zone: ReturnType<typeof getTimeZones>[number]) {
  const cities = zone.mainCities.filter(Boolean).slice(0, 3).join(", ");
  const place = cities || zone.countryName || zone.name;
  const offset = offsetLabel(zone.currentTimeOffsetInMinutes);
  return zone.continentName
    ? `(${offset}) ${place} — ${zone.alternativeName}`
    : `(${offset}) ${zone.alternativeName}`;
}

function groupByRegion(
  entries: ReadonlyArray<TimezoneOption & { region: string }>,
  order?: readonly string[],
): TimezoneRegion[] {
  const byRegion = new Map<string, TimezoneOption[]>();
  for (const entry of entries) {
    const options = byRegion.get(entry.region) ?? [];
    options.push({ label: entry.label, value: entry.value });
    byRegion.set(entry.region, options);
  }
  const regions = [...byRegion.entries()].map(([region, options]) => ({ options, region }));
  if (!order) {
    return regions
      .sort((left, right) =>
        left.region === UNIVERSAL_REGION
          ? -1
          : right.region === UNIVERSAL_REGION
            ? 1
            : left.region.localeCompare(right.region),
      )
      .map((group) => ({
        ...group,
        options: group.options.sort((left, right) => left.label.localeCompare(right.label)),
      }));
  }
  return regions.sort((left, right) => order.indexOf(left.region) - order.indexOf(right.region));
}

/** The short list: a region and a city, ordered west to east within each region. */
export function commonTimezoneRegions(): TimezoneRegion[] {
  const entries = COMMON_ZONES.flatMap((entry) => {
    const zone = zoneByName(entry.zone);
    if (!zone) return [];
    const offset = offsetLabel(zone.currentTimeOffsetInMinutes);
    const label =
      entry.zone === "Etc/UTC"
        ? `(${offset}) ${zone.alternativeName}`
        : `(${offset}) ${entry.city} — ${zone.alternativeName}`;
    return [{ label, region: entry.region, value: entry.zone }];
  });
  return groupByRegion(entries, COMMON_REGION_ORDER);
}

/** Every IANA zone, grouped by continent, for the "show all" escape hatch. */
export function timezoneRegions(): TimezoneRegion[] {
  return groupByRegion(
    zones().map((zone) => ({
      label: fullLabel(zone),
      region: zone.continentName || UNIVERSAL_REGION,
      value: zone.name,
    })),
  );
}

let canonicalCache: Map<string, string> | null = null;

/**
 * Resolves a stored zone to the canonical name this select renders. Deprecated
 * aliases such as `Asia/Calcutta` or a bare `UTC` are listed under their
 * canonical zone's `group`, so they must be matched there too.
 */
export function canonicalTimezone(value: string): string | null {
  if (!value) return null;
  if (!canonicalCache) {
    canonicalCache = new Map();
    // Own names first: 100+ aliases are themselves selectable zones, and those
    // must resolve to their own option rather than to the group's canonical zone.
    for (const zone of zones()) canonicalCache.set(zone.name, zone.name);
    for (const zone of zones()) {
      for (const alias of zone.group) {
        if (!canonicalCache.has(alias)) canonicalCache.set(alias, zone.name);
      }
    }
  }
  return canonicalCache.get(value) ?? null;
}

export function browserTimezone(): string | null {
  try {
    return new Intl.DateTimeFormat().resolvedOptions().timeZone || null;
  } catch {
    return null;
  }
}

type TimezoneSelectProps = {
  /** Rendered in the footer row beside the list toggle, e.g. a "detect" button. */
  action?: ReactNode;
  description?: string;
  id?: string;
  label: string;
  onChange: (value: string) => void;
  value: string;
};

export function TimezoneSelect({
  action,
  description,
  id = "timezone",
  label,
  onChange,
  value,
}: TimezoneSelectProps) {
  const [showAll, setShowAll] = useState(false);
  const common = useMemo(() => commonTimezoneRegions(), []);
  const all = useMemo(() => (showAll ? timezoneRegions() : null), [showAll]);
  const canonical = useMemo(() => canonicalTimezone(value), [value]);

  // A zone the bundled tzdata does not know about must still round-trip rather
  // than silently resolving to whichever option the browser selects first.
  const unlisted = value && !canonical ? value : null;
  const inCommon = canonical
    ? COMMON_ZONES.some((entry) => entry.zone === canonical)
    : Boolean(unlisted);

  const regions = all ?? common;
  // A saved zone outside the short list keeps its own group so the control shows
  // what is actually stored without forcing the full list open.
  const currentGroup =
    !all && canonical && !inCommon
      ? {
          options: [{ label: fullLabel(zoneByName(canonical)!), value: canonical }],
          region: "Current selection",
        }
      : null;

  const groups = currentGroup ? [currentGroup, ...regions] : regions;

  return (
    <div className="space-y-1">
      <Select
        aria-describedby={description ? `${id}-help` : undefined}
        className="w-full"
        id={id}
        isRequired
        onSelectionChange={(key) => onChange(String(key))}
        placeholder="Select a region"
        selectedKey={unlisted ?? canonical ?? null}
      >
        <Label className="field-label">{label}</Label>
        <Select.Trigger className="w-full justify-between">
          <Select.Value />
          <Select.Indicator />
        </Select.Trigger>
        <Select.Popover className="max-h-80">
          <ListBox>
            {unlisted ? (
              <ListBoxItem
                id={unlisted}
                textValue={`${unlisted} (not in the current timezone database)`}
              >
                {unlisted} (not in the current timezone database)
              </ListBoxItem>
            ) : null}
            {groups.map((group) => (
              <ListBoxSection key={group.region}>
                <Header className="px-2 pb-1 pt-2 text-[0.7rem] font-bold uppercase tracking-[0.1em] text-slate-500">
                  {group.region}
                </Header>
                {group.options.map((option) => (
                  <ListBoxItem id={option.value} key={option.value} textValue={option.label}>
                    {option.label}
                  </ListBoxItem>
                ))}
              </ListBoxSection>
            ))}
          </ListBox>
        </Select.Popover>
      </Select>
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 pt-0.5">
        {description ? (
          <p className="text-sm text-slate-500" id={`${id}-help`}>
            {description}
          </p>
        ) : null}
        {action}
        <button className="section-link" onClick={() => setShowAll(!showAll)} type="button">
          {showAll ? "Show common timezones" : "Show all timezones"}
        </button>
      </div>
    </div>
  );
}
