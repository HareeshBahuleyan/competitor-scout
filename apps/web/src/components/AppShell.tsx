import Link from "next/link";
import { Suspense, type ReactNode } from "react";

import { PrimaryNavigation } from "@/components/PrimaryNavigation";

type AppShellProps = {
  children: ReactNode;
};

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="app-shell min-h-screen text-slate-950 lg:grid lg:grid-cols-[15.5rem_minmax(0,1fr)]">
      <aside className="app-sidebar sticky top-0 z-30 border-b border-slate-200 px-3 pt-3 lg:flex lg:h-screen lg:flex-col lg:border-r lg:border-b-0 lg:px-4 lg:py-5">
        <div className="flex items-center justify-between gap-3 px-1 lg:px-2">
          <Link className="group flex min-w-0 items-center gap-3" href="/">
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
            <span className="min-w-0">
              <span className="block truncate text-[15px] font-semibold tracking-[-0.01em]">
                Competitor Scout
              </span>
              <span className="hidden truncate text-[11px] text-slate-500 lg:block">
                Market intelligence
              </span>
            </span>
          </Link>
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
        </div>

        <Suspense fallback={null}>
          <PrimaryNavigation />
        </Suspense>

        <div className="mt-auto hidden px-3 pb-1 lg:block">
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <span className="size-2 rounded-full bg-emerald-500 shadow-[0_0_0_3px_rgba(16,185,129,0.12)]" />
            Scout is ready
          </div>
        </div>
      </aside>

      <main className="app-content min-w-0 px-5 py-7 sm:px-8 sm:py-9 lg:px-12 lg:py-12">
        <div className="mx-auto w-full max-w-[1120px]">{children}</div>
      </main>
    </div>
  );
}
