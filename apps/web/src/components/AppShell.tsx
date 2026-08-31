import Link from "next/link";
import type { ReactNode } from "react";

const navigation = [
  { href: "/", label: "Dashboard" },
  { href: "/competitors", label: "Competitors" },
  { href: "/findings", label: "Findings" },
  { href: "/runs", label: "Runs" },
  { href: "/briefs", label: "Briefs" },
  { href: "/settings", label: "Settings" },
] as const;

type AppShellProps = {
  children: ReactNode;
};

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-950">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-6 py-5 lg:flex-row lg:items-center lg:justify-between">
          <Link className="text-lg font-semibold tracking-tight" href="/">
            Competitor Scout
          </Link>
          <nav aria-label="Primary navigation">
            <ul className="flex flex-wrap gap-x-5 gap-y-2 text-sm font-medium text-slate-600">
              {navigation.map((item) => (
                <li key={item.href}>
                  <Link className="transition-colors hover:text-slate-950" href={item.href}>
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        </div>
      </header>
      <main className="mx-auto w-full max-w-7xl px-6 py-8">{children}</main>
    </div>
  );
}
