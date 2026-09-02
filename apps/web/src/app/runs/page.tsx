import { AppShell } from "@/components/AppShell";
import { RunsListView } from "@/components/pages/AuditViews";

export default async function RunsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const values = await searchParams;
  const competitorId =
    typeof values.competitor_id === "string" && values.competitor_id
      ? values.competitor_id
      : undefined;
  return (
    <AppShell>
      <RunsListView competitorId={competitorId} />
    </AppShell>
  );
}
