import Link from "next/link";
import { Suspense, type ReactNode } from "react";

import { LogoutButton } from "@/components/LogoutButton";
import { PrimaryNavigation } from "@/components/PrimaryNavigation";

type AppShellProps = {
  children: ReactNode;
};

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="app-shell min-h-screen text-slate-950 lg:grid lg:grid-cols-[17rem_minmax(0,1fr)]">
      <aside className="app-sidebar sticky top-0 z-30 border-b border-slate-200 px-3 pt-3 lg:flex lg:h-screen lg:flex-col lg:border-r lg:border-b-0 lg:px-4 lg:py-5">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-1">
          <Link className="group flex shrink-0 items-center gap-3" href="/">
            <span aria-hidden="true" className="brand-mark">
              <svg fill="none" viewBox="0 0 24 24">
                <circle cx="12" cy="12" r="7.5" stroke="currentColor" strokeWidth="1.8" />
                <circle cx="12" cy="12" fill="currentColor" r="2.25" />
                <path
                  d="M12 2.5V5M21.5 12H19M12 19v2.5M5 12H2.5"
                  stroke="currentColor"
                  strokeLinecap="round"
                  strokeWidth="1.8"
                />
              </svg>
            </span>
            <span>
              <span className="block whitespace-nowrap text-[15px] font-semibold tracking-[-0.01em]">
                Competitor Scout
              </span>
              <span className="hidden whitespace-nowrap text-[11px] text-slate-500 lg:block">
                Market intelligence
              </span>
            </span>
          </Link>
          <div className="ml-auto flex shrink-0 items-center gap-2">
            <Link
              aria-label="Add competitor"
              className="icon-button"
              href="/competitors/new"
              title="Add competitor"
            >
              <svg aria-hidden="true" fill="none" viewBox="0 0 24 24">
                <path
                  d="M12 5v14M5 12h14"
                  stroke="currentColor"
                  strokeLinecap="round"
                  strokeWidth="2"
                />
              </svg>
            </Link>
            <div className="lg:hidden">
              <LogoutButton compact />
            </div>
          </div>
        </div>

        <Suspense fallback={null}>
          <PrimaryNavigation />
        </Suspense>

        <div className="mt-auto hidden px-3 pb-1 lg:block">
          <LogoutButton />
        </div>
      </aside>

      <main className="app-content min-w-0 px-5 py-7 sm:px-8 sm:py-9 lg:px-12 lg:py-12">
        <div className="mx-auto w-full max-w-[1120px]">{children}</div>
      </main>
    </div>
  );
}
