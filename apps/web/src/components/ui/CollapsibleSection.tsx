"use client";

import { useState, type ReactNode } from "react";

type CollapsibleSectionProps = {
  children: ReactNode;
  defaultOpen?: boolean;
  id: string;
  title: string;
};

export function CollapsibleSection({
  children,
  defaultOpen = false,
  id,
  title,
}: CollapsibleSectionProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const headingId = `${id}-heading`;
  const contentId = `${id}-content`;

  return (
    <section aria-labelledby={headingId}>
      <h2 id={headingId}>
        <button
          aria-controls={contentId}
          aria-expanded={isOpen}
          className="inline-flex min-h-10 items-center gap-2 rounded-lg py-2 text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-accent)]"
          onClick={() => setIsOpen((open) => !open)}
          type="button"
        >
          <span
            aria-hidden="true"
            className={`text-xl font-semibold transition-transform ${isOpen ? "" : "-rotate-90"}`}
          >
            ⌄
          </span>
          <span className="text-xl font-semibold">{title}</span>
        </button>
      </h2>
      {isOpen ? (
        <div className="mt-4 space-y-4" id={contentId}>
          {children}
        </div>
      ) : null}
    </section>
  );
}
