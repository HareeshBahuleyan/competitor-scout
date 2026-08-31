import { AppShell } from "@/components/AppShell";
import { CompetitorDetailView } from "@/components/pages/CompetitorViews";

export default async function CompetitorDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <AppShell>
      <CompetitorDetailView competitorId={id} />
    </AppShell>
  );
}
