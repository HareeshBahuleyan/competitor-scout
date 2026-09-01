import { AppShell } from "@/components/AppShell";
import { RunDetailView } from "@/components/pages/RunViews";

export default async function RunDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <AppShell>
      <RunDetailView runId={id} />
    </AppShell>
  );
}
