import { AppShell } from "@/components/AppShell";
import { BriefDetailView } from "@/components/pages/BriefViews";

export default async function BriefDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <AppShell>
      <BriefDetailView briefId={id} />
    </AppShell>
  );
}
