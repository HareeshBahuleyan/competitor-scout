import { Suspense } from "react";

import { AppShell } from "@/components/AppShell";
import { NewCompetitorView } from "@/components/pages/CompetitorViews";
import { LoadingState } from "@/components/ui/LoadingState";

export default function NewCompetitorPage() {
  return (
    <AppShell>
      <Suspense fallback={<LoadingState label="Loading setup…" rows={3} />}>
        <NewCompetitorView />
      </Suspense>
    </AppShell>
  );
}
