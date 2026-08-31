import { AppShell } from "@/components/AppShell";
import { FindingsListView, type FindingFilters } from "@/components/pages/AuditViews";

const filterKeys = [
  "category",
  "competitor_id",
  "confidence_min",
  "published_from",
  "published_to",
  "significance",
] as const;

export default async function FindingsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const values = await searchParams;
  const filters: FindingFilters = {};
  for (const key of filterKeys) {
    const value = values[key];
    if (typeof value === "string" && value) filters[key] = value;
  }
  return (
    <AppShell>
      <FindingsListView initialFilters={filters} />
    </AppShell>
  );
}
