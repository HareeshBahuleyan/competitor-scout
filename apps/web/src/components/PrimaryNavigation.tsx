"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

type IconName = "briefs" | "competitors" | "dashboard" | "findings" | "runs" | "settings";

const navigation: ReadonlyArray<{ href: string; icon: IconName; label: string }> = [
  { href: "/", icon: "dashboard", label: "Dashboard" },
  { href: "/competitors", icon: "competitors", label: "Competitors" },
  { href: "/findings", icon: "findings", label: "Findings" },
  { href: "/runs", icon: "runs", label: "Runs" },
  { href: "/briefs", icon: "briefs", label: "Briefs" },
  { href: "/settings", icon: "settings", label: "Settings" },
];

const iconPaths: Record<IconName, ReactNode> = {
  dashboard: (
    <>
      <rect height="6" rx="1.5" width="6" x="3" y="3" />
      <rect height="6" rx="1.5" width="6" x="15" y="3" />
      <rect height="6" rx="1.5" width="6" x="3" y="15" />
      <rect height="6" rx="1.5" width="6" x="15" y="15" />
    </>
  ),
  competitors: (
    <>
      <circle cx="9" cy="8" r="3" />
      <path d="M3.5 19a5.5 5.5 0 0 1 11 0" />
      <path d="M16 4.5a3 3 0 0 1 0 6M17 14a5 5 0 0 1 3.5 5" />
    </>
  ),
  findings: (
    <>
      <path d="m4 17 5-5 4 3 7-8" />
      <path d="M15 7h5v5" />
    </>
  ),
  runs: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </>
  ),
  briefs: (
    <>
      <path d="M6 3h9l3 3v15H6z" />
      <path d="M14 3v4h4M9 11h6M9 15h6" />
    </>
  ),
  settings: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.6v-.2h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z" />
    </>
  ),
};

function NavigationIcon({ name }: { name: IconName }) {
  return (
    <svg
      aria-hidden="true"
      className="size-[18px] shrink-0"
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.7"
      viewBox="0 0 24 24"
    >
      {iconPaths[name]}
    </svg>
  );
}

export function PrimaryNavigation() {
  const pathname = usePathname() ?? "";

  return (
    <nav aria-label="Primary navigation" className="min-w-0 lg:mt-7">
      <p className="mb-2 hidden px-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400 lg:block">
        Workspace
      </p>
      <ul className="flex gap-1 overflow-x-auto px-1 pb-3 lg:flex-col lg:overflow-visible lg:px-0 lg:pb-0">
        {navigation.map((item) => {
          const isActive = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);

          return (
            <li className="shrink-0" key={item.href}>
              <Link
                aria-current={isActive ? "page" : undefined}
                className="nav-link"
                href={item.href}
              >
                <NavigationIcon name={item.icon} />
                <span>{item.label}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
