import { AppShell } from "@/components/AppShell";
import { FindingDetailView } from "@/components/pages/FindingsViews";

export default async function FindingDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <AppShell>
      <FindingDetailView findingId={id} />
    </AppShell>
  );
}
