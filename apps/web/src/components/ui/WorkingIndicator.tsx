"use client";

import { useEffect, useState } from "react";

type WorkingIndicatorProps = {
  hint?: string;
  label: string;
  messages: string[];
  rotateEverySeconds?: number;
};

export function WorkingIndicator({
  hint,
  label,
  messages,
  rotateEverySeconds = 4,
}: WorkingIndicatorProps) {
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => setElapsedSeconds((current) => current + 1), 1_000);
    return () => clearInterval(timer);
  }, []);

  const message =
    messages[Math.floor(elapsedSeconds / rotateEverySeconds) % messages.length] ?? label;

  return (
    <div
      aria-live="polite"
      className="surface flex items-start gap-3 p-4"
      data-testid="working-indicator"
      role="status"
    >
      <span
        aria-hidden="true"
        className="mt-0.5 size-4 shrink-0 animate-spin rounded-full border-2 border-slate-300 border-t-[#d34d50] motion-reduce:animate-none"
      />
      <div className="min-w-0">
        <span className="sr-only">{label}</span>
        <p aria-hidden="true" className="font-medium text-slate-900">
          {message}
        </p>
        <p className="mt-1 text-sm text-slate-500">
          {hint ? `${hint} · ` : null}
          {elapsedSeconds}s elapsed
        </p>
      </div>
    </div>
  );
}
